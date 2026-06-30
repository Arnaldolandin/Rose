"""
Módulo Servipag: consulta de deudas TAG/autopistas usando Chrome CDP.

Arquitectura:
  1. Lanza Chrome directamente (sin Playwright) para evitar detección de bots
  2. Conecta via Playwright CDP (chrome.debugger)
  3. Interactúa con la SPA de Servipag
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
from typing import Optional

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None

log = logging.getLogger("servipag")

SERVIPAG_URL = "https://portal.servipag.com/paymentexpress/category/autopistas"

# Buscar Chrome en rutas comunes
_CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"chrome.exe",
]
CHROME_PATH = None
for p in _CHROME_CANDIDATES:
    if Path(p).exists() or p == "chrome.exe":
        CHROME_PATH = p
        break

EMPRESAS = {
    "Pago Total TAG": "130",
    "RUTA NAHUEBUTA": "181",
    "Autopista Central": "333",
    "Autopista Costa Arauco": "659",
    "Autopista Costanera Norte": "677",
    "Autopista Puente Industrial": "536",
    "Autopista Ruta 5 Sur (RutaSur)": "804",
    "Autopista Ruta 5 Sur (Survias)": "291",
    "Autopista Ruta del Maipo": "795",
    "Autopista Valles del Biobio": "836",
    "Autopista Vespucio Norte": "139",
    "Autopista Vespucio Oriente (AVO1)": "625",
    "Autopista Vespucio Sur": "127",
    "Nogales Puchuncavi (Canopsa)": "352",
    "Ruta 78/Ruta 66/Ruta68": "152",
}


def _limpiar_rut(rut: str) -> str:
    return rut.replace(".", "").strip()


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


async def consultar_deudas_async(
    rut: str,
    empresa: str = "Pago Total TAG",
    headless: bool = False,
) -> dict:
    """
    Navega a Servipag, selecciona empresa, ingresa RUT y consulta deudas.

    Args:
        rut: RUT chileno (con o sin puntos/guión)
        empresa: Nombre de la empresa a consultar
        headless: True intenta headless (puede fallar con Cloudflare)

    Returns:
        dict con: success, deudas, total, sin_deudas, error, empresa, raw_text
    """
    if async_playwright is None:
        return {"success": False, "error": "Playwright no instalado. pip install playwright && playwright install chromium"}

    rut_limpio = _limpiar_rut(rut)
    empresa_val = EMPRESAS.get(empresa)
    if not empresa_val:
        return {"success": False, "error": f"Empresa desconocida: {empresa}"}

    log.info("Servipag: RUT=%s, empresa=%s", rut_limpio, empresa)

    result = {
        "success": False, "deudas": [], "total": None,
        "sin_deudas": False, "error": None, "empresa": empresa,
        "raw_text": "",
    }

    if not CHROME_PATH:
        return {**result, "error": "Chrome no encontrado en rutas habituales"}

    debug_dir = Path(tempfile.mkdtemp(prefix="servipag_"))
    debug_port = _find_free_port()
    proc = None

    try:
        chrome_args = [
            CHROME_PATH,
            f"--user-data-dir={debug_dir}",
            f"--remote-debugging-port={debug_port}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-search-engine-choice-screen",
            "--window-size=1280,800",
        ]
        if headless:
            chrome_args.append("--headless=new")

        chrome_args.append(SERVIPAG_URL)

        proc = subprocess.Popen(
            chrome_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        log.info("Chrome PID=%s", proc.pid)
        time.sleep(8)

        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(
                f"http://127.0.0.1:{debug_port}"
            )
            pages = browser.contexts[0].pages if browser.contexts else []
            page = pages[0] if pages else await browser.contexts[0].new_page()

            current_url = page.url
            log.info("URL: %s", current_url)

            if "servipag.com" not in current_url:
                await page.goto(SERVIPAG_URL, wait_until="load", timeout=30000)
                await page.wait_for_timeout(3000)

            body_text = await page.inner_text("body")
            if "cloudflare" in body_text.lower() or "verificaci" in body_text.lower():
                result["raw_text"] = body_text[:500]
                log.warning("Cloudflare bloqueó")
                return result

            sel = await page.query_selector("#card-lib-selectCompany-change")
            if sel:
                await sel.select_option(empresa_val)
                await page.wait_for_timeout(1000)

            rut_input = await page.query_selector("#card-lib-rut-change")
            if not rut_input:
                result["error"] = "No se encontró campo RUT"
                return result
            await rut_input.click()
            await rut_input.fill("")
            await page.wait_for_timeout(300)
            await rut_input.type(rut_limpio, delay=30)
            log.info("RUT ingresado")

            await page.wait_for_timeout(500)

            btn = await page.query_selector("button:has-text('Continuar')")
            if btn:
                await btn.click()
            else:
                await page.keyboard.press("Enter")
            log.info("Continuar clicked")

            await page.wait_for_timeout(5000)

            result_text = await page.inner_text("body")
            result["raw_text"] = result_text[:10000]

            try:
                await page.screenshot(path=debug_dir / "resultado.png")
            except Exception:
                pass

            result["deudas"] = _extraer_deudas(result_text)
            result["total"] = _extraer_total(result_text)

            txt_lower = result_text.lower()
            if re.search(r'(?:pagar|total)\s*:?\s*\$?\s*0\b', result_text, re.I):
                if not result["deudas"]:
                    result["sin_deudas"] = True
            for p in ["no presenta", "sin deuda", "sin registro",
                      "no se encontraron", "no hay deudas", "no posee",
                      "sin obligaciones", "al día", "sin resultados"]:
                if p in txt_lower:
                    result["sin_deudas"] = True
                    break

            if result["sin_deudas"]:
                result["deudas"] = []

            result["success"] = True
            log.info("Completado: %s deudas, sin_deudas=%s",
                     len(result["deudas"]), result["sin_deudas"])

    except Exception as e:
        log.error("Error: %s", e)
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


def _extraer_deudas(text: str) -> list[dict]:
    skip_re = re.compile(r'(?:pagar|total)\s*:?\s*\$', re.I)
    monto_re = r"\$\s*[\d]{1,3}(?:\.?\d{3})*(?:[.,]\d{2})?"
    deudas = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or skip_re.match(line):
            continue
        m = re.search(monto_re, line)
        if m:
            raw = m.group().replace("$", "").replace(".", "").replace(",", ".")
            try:
                monto = float(raw)
            except ValueError:
                continue
            if monto == 0:
                continue
            deudas.append({"descripcion": line[:150], "monto_raw": m.group(), "monto": monto})
    return deudas


def _extraer_total(text: str) -> Optional[float]:
    for pat in [
        r"Total\s*\$[\s]*([\d]{1,3}(?:\.?\d{3})*(?:[.,]\d{2})?)",
        r"Pagar[:\s]*\$[\s]*([\d]{1,3}(?:\.?\d{3})*(?:[.,]\d{2})?)",
    ]:
        m = re.search(pat, text, re.I)
        if m:
            raw = m.group(1).replace(".", "").replace(",", ".")
            try:
                return float(raw)
            except ValueError:
                pass
    return None


def consultar_deudas(rut: str, empresa: str = "Pago Total TAG", headless: bool = False) -> dict:
    return asyncio.run(consultar_deudas_async(rut, empresa, headless=headless))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    import sys
    rut = sys.argv[1] if len(sys.argv) > 1 else "19609495-4"
    empresa = sys.argv[2] if len(sys.argv) > 2 else "Pago Total TAG"
    res = consultar_deudas(rut, empresa)
    print("\n=== RESULTADO ===")
    for k, v in res.items():
        if k == "raw_text" and v:
            print(f"  {k}: {v[:300]}...")
        else:
            print(f"  {k}: {v}")
