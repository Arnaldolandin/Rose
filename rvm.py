"""
Módulo RVM: verificación de Certificados de Inscripción R.V.M. en Registro Civil.

Flujo:
  1. Extrae Folio y Código de Verificación del texto de un PDF RVM
  2. Consulta la página de verificación del Registro Civil via Chrome CDP
  3. Retorna si el certificado es válido o no
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

log = logging.getLogger("rvm")

VERIFY_URL = "https://www.registrocivil.cl/OficinaInternet/verificacion/verificacioncertificado.srcei"

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


# ---------------------------------------------------------------------------
# Extracción de datos desde texto de PDF
# ---------------------------------------------------------------------------

FOLIO_RE = re.compile(
    r"FOLIO[:\s]*(\d+)",
    re.I,
)
CODIGO_VERIF_RE = re.compile(
    r"(?:C[oó]digo\s+)?[Vv]erificaci[oó]n[:\s]*([A-Za-z0-9]+)",
    re.I,
)


def extraer_datos_rvm(texto: str) -> dict:
    """
    Extrae Folio (solo dígitos) y Código de Verificación del texto de un PDF RVM.

    Formatos conocidos:
      "FOLIO:500643609125\nCódigo Verificación: 4946ff571c13"
      "FOLIO:\n54680cc82727Código Verificación:500703512182"

    Returns:
        dict con folio, codigo_verificacion, encontrado
    """
    result = {"folio": None, "codigo_verificacion": None, "encontrado": False}

    # Prioridad 1: formato con FOLIO y Código Verificación intercambiados por PyPDF2:
    #   "FOLIO:\n{codigo}Código Verificación:{folio}"
    #   (común cuando el layout PDF tiene ambos campos en la misma línea)
    m_mangled = re.search(
        r"FOLIO[:\s]*([A-Za-z0-9]+)"
        r"(?:C[oó]digo\s+)?[Vv]erificaci[oó]n[:\s]*(\d{6,})",
        texto, re.I
    )
    if m_mangled:
        cod_candidate = m_mangled.group(1).strip()
        folio_candidate = m_mangled.group(2).strip()
        # Si el primer grupo no es todo dígitos → es el código de verificación
        # y el segundo grupo (solo dígitos) → es el folio
        if not cod_candidate.isdigit() and folio_candidate.isdigit():
            result["folio"] = folio_candidate
            result["codigo_verificacion"] = cod_candidate

    # Prioridad 2: formato normal (folio numérico tras FOLIO:)
    if not result["folio"]:
        m_folio = FOLIO_RE.search(texto)
        if m_folio:
            result["folio"] = m_folio.group(1).strip()

    # Prioridad 3: código de verificación tras "Verificación:"
    if not result["codigo_verificacion"]:
        m_cod = CODIGO_VERIF_RE.search(texto)
        if m_cod:
            raw_cod = m_cod.group(1).strip()
            if raw_cod.isdigit() and result["folio"] and raw_cod == result["folio"]:
                pass  # mismo valor, probable duplicado
            else:
                result["codigo_verificacion"] = raw_cod

    # Prioridad 4: formato combinado antiguo
    #   "FOLIO:\n{digitos_folio}{codigo}Código Verificación:{folios_num}"
    if not result["folio"] or not result["codigo_verificacion"]:
        m_combined = re.search(
            r"FOLIO[:\s]*(\d+)([A-Za-z0-9]+)"
            r"(?:C[oó]digo\s+)?[Vv]erificaci[oó]n[:\s]*(\d+)",
            texto, re.I
        )
        if m_combined:
            if not result["folio"]:
                result["folio"] = m_combined.group(1) + m_combined.group(3)
            if not result["codigo_verificacion"] or (result["codigo_verificacion"] and
                                                     result["codigo_verificacion"].isdigit()):
                result["codigo_verificacion"] = m_combined.group(2) + m_combined.group(3)

    # Si falta el código de verificación, buscar código alfanumérico cercano al folio
    if not result["codigo_verificacion"] and result["folio"]:
        # Buscar "FOLIO:{digitos}({codigo})" donde el código sigue al folio sin espacio
        m_near = re.search(
            rf"FOLIO[:\s]*{re.escape(result['folio'])}([A-Za-z0-9]{{6,20}})",
            texto, re.I
        )
        if m_near:
            candidate = m_near.group(1).strip()
            # El candidato no debe ser todo dígitos (folio repetido)
            if not candidate.isdigit():
                result["codigo_verificacion"] = candidate

    # Buscar códigos de verificación en el texto con formato "COD:XXXX" o "VERIF:XXXX"
    if not result["codigo_verificacion"]:
        m_alt = re.search(
            r"(?:COD[.:]\s*|[Vv]erif[.:]\s*|[Cc]ódigo[:\s]*)([A-Za-z0-9]{6,20})",
            texto
        )
        if m_alt:
            candidate = m_alt.group(1).strip()
            if not candidate.isdigit() or (candidate.isdigit() and candidate != result.get("folio")):
                result["codigo_verificacion"] = candidate

    # Validar que el folio sea solo dígitos (Requisito del formulario)
    if result["folio"] and not result["folio"].isdigit():
        nums = re.match(r"(\d+)", result["folio"])
        if nums:
            result["folio"] = nums.group(1)
        else:
            result["folio"] = None

    if result["folio"] and result["codigo_verificacion"]:
        result["encontrado"] = True
        log.info("RVM extraído: folio=%s codigo=%s",
                 result["folio"], result["codigo_verificacion"])
    elif result["folio"] and not result["codigo_verificacion"]:
        result["encontrado"] = True  # Al menos tenemos folio
        log.info("RVM extraído (sin código): folio=%s", result["folio"])

    return result


# ---------------------------------------------------------------------------
# Verificación en Registro Civil
# ---------------------------------------------------------------------------


async def verificar_rvm_async(
    folio: str,
    codigo: str | None,
    keep_open: bool = False,
) -> dict:
    """
    Verifica un certificado RVM en el Registro Civil.

    Args:
        folio: número de folio del certificado
        codigo: código de verificación (None si no se pudo leer)
        keep_open: True para dejar Chrome abierto (debug)

    Returns:
        dict con success, valido, mensaje, error
    """
    if async_playwright is None:
        return {"success": False, "valido": None, "mensaje": None,
                "error": "Playwright no instalado"}

    result = {
        "success": False,
        "folio": folio,
        "codigo": codigo,
        "valido": None,
        "mensaje": None,
        "error": None,
    }

    if not codigo:
        return {**result, "success": True, "valido": None,
                "mensaje": "Folio encontrado, pero no se pudo leer el código de verificación (foto no lo capturó). Verificar manualmente en registrocivil.cl"}

    if not CHROME_PATH:
        return {**result, "error": "Chrome no encontrado"}

    debug_dir = Path(tempfile.mkdtemp(prefix="rvm_"))
    debug_port = _find_free_port()
    proc = None

    try:
        chrome_args = [
            CHROME_PATH,
            f"--user-data-dir={debug_dir}",
            f"--remote-debugging-port={debug_port}",
            "--no-first-run", "--no-default-browser-check",
            "--disable-search-engine-choice-screen",
            "--window-size=1000,700",
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
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()

            log.info("Navegando a Registro Civil...")
            await page.goto(VERIFY_URL, wait_until="load", timeout=60000)
            await page.wait_for_timeout(3000)

            # Llenar folio
            folio_input = await page.query_selector("#ver_inputFolio")
            if not folio_input:
                result["error"] = "No se encontró campo Folio"
                return result

            await folio_input.click()
            await folio_input.fill("")
            await folio_input.type(folio, delay=20)
            log.info("Folio ingresado: %s", folio)

            # Llenar código de verificación
            cod_input = await page.query_selector("#ver_inputCodVerificador")
            if not cod_input:
                result["error"] = "No se encontró campo Código de Verificación"
                return result

            await cod_input.click()
            await cod_input.fill("")
            await cod_input.type(codigo, delay=20)
            log.info("Código ingresado: %s", codigo)

            await page.wait_for_timeout(500)

            # Click botón Consultar
            btn = await page.query_selector("#ver_btnConsultar")
            if btn:
                await btn.click()
                log.info("Click en Consultar")
            else:
                await page.keyboard.press("Enter")

            # Esperar resultado
            await page.wait_for_timeout(5000)

            # Tomar screenshot
            await page.screenshot(path=debug_dir / "rvm_resultado.png")

            # Verificar si el modal de éxito apareció
            body_text = await page.inner_text("body")
            log.info("Body text (%d chars)", len(body_text))

            if "El certificado es v" in body_text or "certificado es v" in body_text.lower():
                result["valido"] = True
                result["mensaje"] = "Certificado válido"
                result["success"] = True
                log.info("RVM: CERTIFICADO VÁLIDO")
            elif "error" in body_text.lower() and ("folio" in body_text.lower() or "código" in body_text.lower()):
                # Buscar mensaje de error
                m = re.search(r"error[^.]*\.", body_text, re.I)
                result["valido"] = False
                result["mensaje"] = m.group(0) if m else "Error de verificación"
                result["success"] = True
                log.info("RVM: %s", result["mensaje"])
            else:
                # Esperar más tiempo
                await page.wait_for_timeout(5000)
                body_text2 = await page.inner_text("body")
                if "El certificado es v" in body_text2:
                    result["valido"] = True
                    result["mensaje"] = "Certificado válido"
                    result["success"] = True
                else:
                    result["valido"] = False
                    result["mensaje"] = "No se pudo determinar"
                    result["success"] = True

            if keep_open:
                log.info("Chrome mantenido abierto 60s...")
                await asyncio.sleep(60)

    except Exception as e:
        log.error("Error RVM: %s", e)
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


def verificar_rvm(folio: str, codigo: str, keep_open: bool = False) -> dict:
    return asyncio.run(verificar_rvm_async(folio, codigo, keep_open=keep_open))


# ---------------------------------------------------------------------------
# Helper: extraer datos del texto y verificar en un solo paso
# ---------------------------------------------------------------------------


def extraer_y_verificar(texto_pdf: str, keep_open: bool = False) -> dict:
    """
    Extrae Folio/Código del texto de un PDF RVM y verifica en Registro Civil.

    Returns:
        dict con los resultados de extracción y verificación
    """
    extraccion = extraer_datos_rvm(texto_pdf)
    if not extraccion["encontrado"]:
        return {
            "success": False,
            "extraido": False,
            "folio": None,
            "codigo": None,
            "valido": None,
            "mensaje": "No se encontraron Folio/Código en el PDF",
        }

    verificacion = verificar_rvm(
        extraccion["folio"],
        extraccion["codigo_verificacion"],
        keep_open=keep_open,
    )

    return {
        "success": verificacion.get("success", False),
        "extraido": True,
        "folio": extraccion["folio"],
        "codigo": extraccion["codigo_verificacion"],
        "valido": verificacion.get("valido"),
        "mensaje": verificacion.get("mensaje") or verificacion.get("error"),
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    import sys
    if len(sys.argv) >= 3:
        folio = sys.argv[1]
        codigo = sys.argv[2]
        res = verificar_rvm(folio, codigo, keep_open=True)
    else:
        # Test con datos de ejemplo (posiblemente inválidos)
        res = verificar_rvm("54680", "cc82727")
    print("\n=== RESULTADO RVM ===")
    for k, v in res.items():
        print(f"  {k}: {v}")
