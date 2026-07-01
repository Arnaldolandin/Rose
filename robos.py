"""
Módulo Robos: consulta si una patente tiene encargo por robo (Auto Seguro).

Usa Chrome CDP + Playwright para consultar autoseguro.gob.cl
"""
import asyncio
import logging
import re
import shutil
import subprocess
import socket
import tempfile
import time
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None

log = logging.getLogger("robos")

AUTOSEGURO_URL = "https://www.autoseguro.gob.cl/"

_CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]
CHROME_PATH = None
for p in _CHROME_CANDIDATES:
    if Path(p).exists():
        CHROME_PATH = p
        break
if not CHROME_PATH:
    CHROME_PATH = shutil.which("chrome") or shutil.which("google-chrome")


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


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
    debug_port = _find_free_port()
    proc = None

    try:
        chrome_args = [
            CHROME_PATH,
            f"--user-data-dir={debug_dir}",
            f"--remote-debugging-port={debug_port}",
            "--no-first-run", "--no-default-browser-check",
            "--disable-search-engine-choice-screen",
            "--window-size=1000,800",
        ]

        proc = subprocess.Popen(
            chrome_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        log.info("Chrome PID=%s", proc.pid)
        time.sleep(6)

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


def consultar_robo(patente: str) -> dict:
    return asyncio.run(consultar_robo_async(patente))
