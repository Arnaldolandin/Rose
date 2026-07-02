"""
Módulo Robos: consulta si una patente tiene encargo por robo (Auto Seguro).

Usa Chrome CDP + Playwright para consultar autoseguro.gob.cl
"""
import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

from cdp_common import CHROME_PATH, find_free_port, launch_chrome, wait_for_cdp

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None

log = logging.getLogger("robos")

AUTOSEGURO_URL = "https://www.autoseguro.gob.cl/"


async def consultar_robo_async(patente: str) -> dict:
    """
    Consulta si una patente tiene encargo por robo en Auto Seguro.

    Bypass reCAPTCHA: usa Object.defineProperty para atrapar
    window.__bypassCaptchaValidation y forzarlo a false siempre.
    El inline script de la página hace:
      window.__bypassCaptchaValidation = true;
    Y luego Inicio.js evalúa:
      var bypassCaptchaValidation = window.__bypassCaptchaValidation === false;
    Con el trap: setter ignora la escritura, getter devuelve false →
    bypassCaptchaValidation = true → se salta el captcha.
    """
    result = {
        "success": False,
        "patente": patente,
        "robado": None,
        "detalle": None,
        "error": None,
    }

    if async_playwright is None:
        return {**result, "error": "Playwright no instalado"}

    if not CHROME_PATH:
        return {**result, "error": "Chrome no encontrado"}

    debug_dir = Path(tempfile.mkdtemp(prefix="robos_"))
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

            # By Pass reCAPTCHA: atrapa la propiedad para que siempre lea false
            await ctx.add_init_script("""
                Object.defineProperty(window, '__bypassCaptchaValidation', {
                    get() { return false; },
                    set(v) {},
                    configurable: true,
                    enumerable: true
                });
            """)

            page = ctx.pages[0] if ctx.pages else await ctx.new_page()

            log.info("Navegando a Auto Seguro...")
            await page.goto(AUTOSEGURO_URL, wait_until="load", timeout=60000)
            await page.wait_for_timeout(3000)

            # Llenar patente
            await page.fill("#txt_placa_patente", patente)
            log.info("Patente ingresada: %s", patente)

            # Click botón de búsqueda (imagen)
            await page.evaluate("clickPpu()")
            log.info("Click en buscar patente")

            await page.wait_for_timeout(5000)

            # Esperar a que aparezca el modal
            try:
                await page.wait_for_selector("#exampleModalCenter:visible, .modal-content", timeout=10000)
            except Exception:
                pass
            await page.wait_for_timeout(2000)

            # Revisar el modal de resultado
            body_text = await page.inner_text("#exampleModalCenter") if await page.query_selector("#exampleModalCenter") else await page.inner_text("body")
            log.info("Resultado (%d chars): %s", len(body_text), body_text[:400])

            body_lower = body_text.lower()

            # --- Detectar si tiene encargo por robo ---
            # Safe: frases que indican que NO tiene encargo
            safe_keywords = ["no mantiene", "sin encargo", "el vehículo no"]
            es_seguro = any(kw in body_lower for kw in safe_keywords)

            # Robo: frases que indican que SÍ tiene encargo
            robo_keywords = ["sustraído", "sustraída", "robado", "encargo vigente"]

            tiene_robo = not es_seguro and any(kw in body_lower for kw in robo_keywords)

            # Fallback: icono de alerta rojo parpadeante
            if not es_seguro and not tiene_robo:
                icon_alerta = await page.query_selector("#ico_alerta")
                if icon_alerta:
                    cls = await icon_alerta.get_attribute("class") or ""
                    if "parpadea" in cls:
                        tiene_robo = True
                        log.info("Robo detectado por icono alerta")

            result["robado"] = tiene_robo
            result["success"] = True

            # Extraer detalle del label lbl_Vehiculo
            lbl_veh = await page.text_content("#lbl_Vehiculo") if await page.query_selector("#lbl_Vehiculo") else ""
            if lbl_veh:
                result["detalle"] = lbl_veh.strip()

            if tiene_robo:
                log.warning("PATENTE %s — TIENE ENCARGO POR ROBO", patente)
            else:
                log.info("Patente %s — SIN encargo por robo", patente)

            await page.screenshot(path=debug_dir / "robos_resultado.png")

    except Exception as e:
        log.error("Error consulta robo: %s", e)
        result["error"] = str(e)
    finally:
        if proc:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass
        shutil.rmtree(debug_dir, ignore_errors=True)

    return result


def _fallo_reintentable(res: dict) -> bool:
    """True si el resultado de robo parece un fallo transitorio (vale reintentar).

    Reintenta ante cualquier `success=False` (modal no leído, excepciones). NO
    reintenta ante errores de configuración (Chrome/Playwright ausente) ni ante un
    veredicto definitivo (robado True/False).
    """
    err = (res.get("error") or "").lower()
    if any(x in err for x in ("chrome no encontrado", "playwright no instalado")):
        return False
    return not res.get("success")


def consultar_robo(patente: str, intentos: int = 2) -> dict:
    """Consulta encargo por robo con reintento automático ante fallos transitorios."""
    res: dict = {}
    for intento in range(1, intentos + 1):
        res = asyncio.run(consultar_robo_async(patente))
        if not _fallo_reintentable(res):
            return res
        if intento < intentos:
            log.warning("Robo intento %s/%s no concluyente (%s); reintentando...",
                        intento, intentos, res.get("error") or "sin resultado")
    return res
