"""
Módulo SII: consulta de datos tributarios (RUT, razón social, vigencia) en SII Chile.
"""

import asyncio
import logging
import re
import shutil
import tempfile
import time
from pathlib import Path

from cdp_common import CHROME_PATH, find_free_port, launch_chrome, wait_for_cdp

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None

log = logging.getLogger("sii")

SII_URL = "https://www2.sii.cl/stc/noauthz"


def _formatear_rut(rut: str) -> str:
    """Convierte 19609495-4 -> 19.609.495-4"""
    rut = rut.replace(".", "").strip()
    m = re.match(r'^(\d+)-?([\dkK])$', rut)
    if not m:
        return rut
    nums, dv = m.group(1), m.group(2)
    nums_fmt = []
    for i, ch in enumerate(reversed(nums)):
        if i > 0 and i % 3 == 0:
            nums_fmt.insert(0, '.')
        nums_fmt.insert(0, ch)
    return ''.join(nums_fmt) + '-' + dv


async def _esperar_fuera_de_cola(page, timeout=120):
    """Espera a que salga de la sala de espera Queue-it y el SPA cargue."""
    inicio = time.time()
    while time.time() - inicio < timeout:
        url = page.url
        if "salaespera.sii.cl" not in url:
            # Ya salió de la cola, esperar render SPA
            for _ in range(30):
                has_rut = await page.evaluate(
                    "document.querySelector('input.rut-form') !== null"
                )
                if has_rut:
                    return True
                await page.wait_for_timeout(1000)
            return False
        await page.wait_for_timeout(2000)
    return False


async def consultar_sii_async(rut: str, keep_open: bool = False) -> dict:
    if async_playwright is None:
        return {"success": False, "error": "Playwright no instalado"}

    rut_fmt = _formatear_rut(rut)
    rut_limpio = rut.replace(".", "").strip()

    result = {
        "success": False,
        "rut": rut_limpio,
        "razon_social": None,
        "vigente": None,
        "inicio_actividades": None,
        "registrado": None,
        "fecha_consulta": None,
        "error": None,
    }

    if not CHROME_PATH:
        return {**result, "error": "Chrome no encontrado"}

    debug_dir = Path(tempfile.mkdtemp(prefix="sii_"))
    debug_port = find_free_port()
    proc = None

    try:
        proc = launch_chrome(debug_port, debug_dir, window_size="1000,800")
        log.info("Chrome PID=%s", proc.pid)
        wait_for_cdp(debug_port)

        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(
                f"http://127.0.0.1:{debug_port}"
            )
            ctx = browser.contexts[0]
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()

            log.info("Navegando a SII...")
            await page.goto(SII_URL, wait_until="load", timeout=60000)

            log.info("Esperando salir de cola Queue-it...")
            ok = await _esperar_fuera_de_cola(page, timeout=120)
            if not ok:
                result["error"] = "SII en cola - tiempo excedido"
                await page.screenshot(path=debug_dir / "sii_cola.png")
                return result

            log.info("Fuera de cola, SPA renderizado")

            rut_input = await page.query_selector("input.rut-form")
            if not rut_input:
                result["error"] = "No se encontró campo RUT en SII"
                await page.screenshot(path=debug_dir / "sii_no_rut.png")
                return result

            await rut_input.click()
            await rut_input.fill("")
            await rut_input.type(rut_fmt, delay=30)
            log.info("RUT ingresado: %s", rut_fmt)
            await page.wait_for_timeout(500)

            btn = await page.query_selector("input.button-azul")
            if not btn:
                btn = await page.query_selector(
                    "input[type=button][value*='Consultar'], button:has-text('Consultar')"
                )

            if btn:
                await btn.click()
                log.info("Click en Consultar")
            else:
                log.warning("Botón no encontrado, Enter")
                await page.keyboard.press("Enter")

            # Esperar que cargue la vista de resultados
            log.info("Esperando resultados...")
            await page.wait_for_timeout(12000)

            # Esperar que desaparezca el loading overlay
            try:
                await page.wait_for_function(
                    "() => { const o = document.querySelector('.vld-overlay'); "
                    "return !o || o.style.display === 'none' || "
                    "o.classList.contains('is-active') === false; }",
                    timeout=15000
                )
            except Exception:
                log.warning("Timeout loading overlay")

            await page.wait_for_timeout(2000)

            await page.screenshot(path=debug_dir / "sii_resultado.png")

            # Extraer datos
            body_text = await page.inner_text("body")
            log.info("Body text (%d chars)", len(body_text))

            razon = None
            for pat in [
                r"(?:Raz[oó]n Social|Nombre o Raz[oó]n Social)[:\s]*([^\n]{3,80})",
                r"(?:Nombre)[:\s]*([^\n]{3,80})",
            ]:
                m = re.search(pat, body_text, re.I)
                if m:
                    razon = m.group(1).strip()
                    break

            vigente = None
            if re.search(r"(?:NO\s+)?VIGENTE", body_text, re.I):
                vigente = bool(re.search(r"\bVIGENTE\b", body_text, re.I)
                              and not re.search(r"NO\s+VIGENTE", body_text, re.I))

            inicio = None
            m = re.search(
                r"Inicio de Actividades[:\s]*(\d{2}[/-]\d{2}[/-]\d{4})",
                body_text, re.I
            )
            if m:
                inicio = m.group(1)

            registrado = None
            if "NO REGISTRA" in body_text.upper() or "NO REGISTRADO" in body_text.upper():
                registrado = False
            else:
                registrado = True

            fecha_consulta = None
            m = re.search(
                r"Fecha de Consulta[:\s]*(\d{2}[/-]\d{2}[/-]\d{4})",
                body_text, re.I
            )
            if m:
                fecha_consulta = m.group(1)

            # Extraer datos de la tabla de resultados via DOM
            accordion_data = await page.evaluate("""
                () => {
                    const result = {};
                    const labels = document.querySelectorAll('.accordion-body label, '
                        + '.card-body label, .col-form-label, strong');
                    labels.forEach(l => {
                        const text = (l.innerText || '').trim();
                        const next = l.nextElementSibling;
                        if (next) {
                            result[text] = (next.innerText || '').trim();
                        }
                    });
                    return result;
                }
            """)
            if accordion_data:
                log.info("Datos del DOM: %s", accordion_data)

            result["razon_social"] = razon
            result["vigente"] = vigente
            result["inicio_actividades"] = inicio
            result["registrado"] = registrado
            result["fecha_consulta"] = fecha_consulta
            if razon or registrado:
                result["success"] = True
            else:
                result["error"] = "No se pudieron extraer datos del SII"

            log.info("SII resultado: razon=%s vigente=%s inicio=%s",
                     razon, vigente, inicio)

            if keep_open:
                log.info("Chrome mantenido abierto 60s...")
                await asyncio.sleep(60)

    except Exception as e:
        log.error("Error SII: %s", e)
        result["error"] = str(e)
    finally:
        if proc and not keep_open:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass
        shutil.rmtree(debug_dir, ignore_errors=True)

    return result


def _fallo_reintentable(res: dict) -> bool:
    """True si el resultado SII parece un fallo transitorio (vale reintentar).

    Reintenta ante cualquier `success=False` (cola Queue-it excedida, campo RUT
    no encontrado, datos no extraídos, excepciones). NO reintenta ante errores de
    configuración (Chrome/Playwright ausente).
    """
    err = (res.get("error") or "").lower()
    if any(x in err for x in ("chrome no encontrado", "playwright no instalado")):
        return False
    return not res.get("success")


def consultar_sii(rut: str, keep_open: bool = False, intentos: int = 2) -> dict:
    """Consulta SII con reintento automático ante fallos transitorios.

    En modo `keep_open` (debug) no reintenta: deja el primer Chrome abierto.
    """
    if keep_open:
        return asyncio.run(consultar_sii_async(rut, keep_open=True))
    res: dict = {}
    for intento in range(1, intentos + 1):
        res = asyncio.run(consultar_sii_async(rut, keep_open=False))
        if not _fallo_reintentable(res):
            return res
        if intento < intentos:
            log.warning("SII intento %s/%s no concluyente (%s); reintentando...",
                        intento, intentos, res.get("error") or "sin datos")
    return res


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    import sys
    rut = sys.argv[1] if len(sys.argv) > 1 else "19609495-4"
    res = consultar_sii(rut)
    print("\n=== RESULTADO SII ===")
    for k, v in res.items():
        print(f"  {k}: {v}")
