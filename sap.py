"""
Módulo SAP: login + llenado de formulario en SAP CRM WebClient UI.
"""

import asyncio
import logging
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

log = logging.getLogger("sap")

SAP_URL = (
    "https://chppas01.autopase.cl:1443/sap(bD1lcyZjPTQwMCZkPW1pbg==)/"
    "bc/bsp/sap/crm_ui_start/default.htm?sap-client=400&sap-language=ES"
)

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


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


async def _llenar_input_js(page, selector: str, valor: str) -> bool:
    """Llena un input vía JavaScript, evitando problemas de actionability."""
    ok = await page.evaluate(
        """({selector, valor}) => {
            const el = document.querySelector(selector);
            if (!el) return false;
            el.value = valor;
            el.dispatchEvent(new Event('focus', {bubbles: true}));
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            el.dispatchEvent(new Event('blur', {bubbles: true}));
            return true;
        }""",
        {"selector": selector, "valor": valor},
    )
    return ok


async def sap_llenar_async(
    usuario: str = "CGUERRA",
    password: str = "Inte.elias*26",
    datos: Optional[dict] = None,
) -> dict:
    if async_playwright is None:
        return {"success": False, "error": "Playwright no instalado"}

    result = {"success": False, "error": None, "url_final": ""}

    if not CHROME_PATH:
        return {**result, "error": "Chrome no encontrado"}

    debug_dir = Path(tempfile.mkdtemp(prefix="sap_"))
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
            "--window-size=1400,900",
            "--ignore-certificate-errors",
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
            pages = browser.contexts[0].pages if browser.contexts else []
            page = pages[0] if pages else await browser.contexts[0].new_page()

            log.info("Navegando a SAP...")
            await page.goto(SAP_URL, wait_until="load", timeout=60000)
            await page.wait_for_timeout(5000)

            # Dump estructura
            try:
                inputs_info = await page.evaluate("""
                    Array.from(document.querySelectorAll('input, select, textarea')).map(el => ({
                        tag: el.tagName,
                        type: el.type || '',
                        name: el.name || '',
                        id: el.id || '',
                        placeholder: el.placeholder || '',
                        className: el.className || '',
                        disabled: el.disabled,
                        readonly: el.readOnly,
                        rect: el.getBoundingClientRect().x + ',' + el.getBoundingClientRect().y
                    }))
                """)
                log.info("Inputs en pagina (%d):", len(inputs_info))
                for inp in inputs_info[:20]:
                    log.info("  %s", inp)
            except Exception as e:
                log.warning("Error dump inputs: %s", e)

            # Screenshot
            try:
                await page.screenshot(path=debug_dir / "sap_pagina.png")
                log.info("Screenshot guardado")
            except Exception:
                pass

            # --- LOGIN SAP ---
            log.info("Haciendo login SAP...")

            # Estrategia con JavaScript: buscar inputs y llenar directamente
            inputs_log = await page.evaluate("""
                () => {
                    const all = document.querySelectorAll('input');
                    const result = [];
                    all.forEach(el => {
                        result.push({
                            name: el.name,
                            id: el.id,
                            type: el.type,
                            placeholder: el.placeholder,
                            visible: el.offsetParent !== null,
                            rect: el.getBoundingClientRect().width + 'x' + el.getBoundingClientRect().height
                        });
                    });
                    return result;
                }
            """)
            log.info("Inputs encontrados: %s", len(inputs_log))
            for inp in inputs_log:
                log.info("  name=%-20s id=%-20s type=%-10s visible=%s rect=%s",
                         inp["name"][:20], inp["id"][:20], inp["type"], inp["visible"],
                         inp["rect"])

            # Llenar usuario por JS directo
            user_set = await page.evaluate(
                """(val) => {
                    const el = document.querySelector('input[name="usrname"], input[name="USR03"], input[id*="usr"], input[name*="user"]');
                    if (!el) return 'no encontrado';
                    el.value = val;
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    return 'ok: ' + el.name + '=' + el.value;
                }""",
                usuario,
            )
            log.info("Usuario JS: %s", user_set)

            pass_set = await page.evaluate(
                """(val) => {
                    const el = document.querySelector('input[type="password"], input[name="password"], input[id*="pass"]');
                    if (!el) return 'no encontrado';
                    el.value = val;
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    return 'ok: ' + el.name + '=' + el.value;
                }""",
                password,
            )
            log.info("Password JS: %s", pass_set)

            # Click submit — usando selector CSS estándar
            submit_ok = await page.evaluate("""
                () => {
                    // Buscar botón submit de SAP
                    const btn = document.querySelector('input[type="submit"], button[type="submit"], .lsLogin__button, [class*="logon"], [id*="logon"], button:not([type])');
                    if (btn) {
                        btn.click();
                        return 'click: ' + (btn.id || btn.name || btn.className || btn.tagName);
                    }
                    // Fallback: submit el formulario
                    const form = document.querySelector('form');
                    if (form) {
                        form.submit();
                        return 'form.submit()';
                    }
                    return 'no encontrado';
                }
            """)
            log.info("Submit: %s", submit_ok)

            await page.wait_for_timeout(8000)

            url_actual = page.url
            result["url_final"] = url_actual
            log.info("URL después de login: %s", url_actual)

            # Dump frames info
            log.info("Frames después de login: %s", len(page.frames))
            target_frame = page
            for fi, frame in enumerate(page.frames):
                try:
                    f_url = (frame.url or "")[:120]
                    log.info("  Frame[%d]: %s", fi, f_url)
                    # Check for visible non-hidden inputs
                    has_inputs = await frame.evaluate("() => document.querySelector('input:not([type=hidden])') !== null")
                    if has_inputs:
                        # Get count
                        count = await frame.evaluate("() => document.querySelectorAll('input:not([type=hidden])').length")
                        log.info("    Inputs visibles: %d", count)
                        # If this has many inputs, it's likely the work area
                        if count > 5:
                            target_frame = frame
                except Exception as e:
                    log.warning("  Frame[%d] error: %s", fi, str(e)[:80])

            log.info("Frame seleccionado para llenar: [%d] %s",
                     [i for i, f in enumerate(page.frames) if f == target_frame][0] if target_frame != page else 0,
                     (target_frame.url or "")[:80])

            # --- LLENAR FORMULARIO ---
            if datos:
                log.info("Intentando llenar formulario...")
                await target_frame.wait_for_timeout(2000)

                # Llenar un campo a la vez para evitar errores de serialización
                for campo, valor in datos.items():
                    if not valor:
                        continue
                    try:
                        ok = await target_frame.evaluate(
                            """({campo, valor}) => {
                                const labels = Array.from(document.querySelectorAll('label, span, div.urTxtLbl'));
                                let input = null;
                                // 1. Buscar por label que contenga el texto
                                const label = labels.find(l => l.innerText.toLowerCase().includes(campo));
                                if (label) {
                                    const forId = label.getAttribute('for');
                                    if (forId) input = document.getElementById(forId);
                                    if (!input) {
                                        let el = label.nextElementSibling;
                                        while (el) {
                                            if (el.tagName==='INPUT' || el.tagName==='SELECT' || el.tagName==='TEXTAREA') {
                                                input = el; break;
                                            }
                                            el = el.nextElementSibling;
                                        }
                                    }
                                    if (!input) {
                                        const parent = label.parentElement;
                                        if (parent) input = parent.querySelector('input, select, textarea');
                                    }
                                }
                                // 2. Buscar por placeholder
                                if (!input) {
                                    input = document.querySelector('input[placeholder*="' + campo + '"], textarea[placeholder*="' + campo + '"]');
                                }
                                // 3. Buscar por name/id genérico
                                if (!input) {
                                    input = document.querySelector('input[id*="' + campo + '"], input[name*="' + campo + '"]');
                                }
                                if (input) {
                                    input.value = valor;
                                    input.dispatchEvent(new Event('input', {bubbles: true}));
                                    input.dispatchEvent(new Event('change', {bubbles: true}));
                                    return true;
                                }
                                return false;
                            }""",
                            {"campo": campo, "valor": str(valor)}
                        )
                        if ok:
                            log.info("Campo '%s' llenado", campo)
                        else:
                            log.info("Campo '%s' no encontrado", campo)
                    except Exception as e:
                        log.warning("Error llenando campo '%s': %s", campo, str(e)[:80])

            result["success"] = True
            log.info("Proceso SAP completado — Chrome abierto 30s")
            await asyncio.sleep(30)

    except Exception as e:
        log.error("Error SAP: %s", e)
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


def sap_llenar(
    usuario: str = "CGUERRA",
    password: str = "Inte.elias*26",
    datos: Optional[dict] = None,
) -> dict:
    return asyncio.run(sap_llenar_async(usuario, password, datos))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    res = sap_llenar()
    print("\n=== RESULTADO ===")
    for k, v in res.items():
        print(f"  {k}: {v}")
