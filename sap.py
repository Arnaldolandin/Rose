"""
Módulo SAP: login + llenado de formulario en SAP CRM WebClient UI.
"""

import asyncio
import json
import logging
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Optional

from cdp_common import CHROME_PATH, find_free_port, launch_chrome, wait_for_cdp

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None

log = logging.getLogger("sap")


def _sap_creds() -> tuple[Optional[str], Optional[str]]:
    """Lee usuario/clave de SAP desde config.json (junto al .exe o al fuente)."""
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    try:
        cfg = json.loads((base / "config.json").read_text(encoding="utf-8"))
        return cfg.get("sap_user"), cfg.get("sap_password")
    except Exception as e:
        log.warning("No se pudo leer credenciales SAP de config.json: %s", e)
        return None, None

SAP_URL = (
    "https://chppas01.autopase.cl:1443/sap(bD1lcyZjPTQwMCZkPW1pbg==)/"
    "bc/bsp/sap/crm_ui_start/default.htm?sap-client=400&sap-language=ES"
)


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
    usuario: Optional[str] = None,
    password: Optional[str] = None,
    datos: Optional[dict] = None,
) -> dict:
    if async_playwright is None:
        return {"success": False, "error": "Playwright no instalado"}

    # Credenciales desde config.json si no se pasan explícitas
    if not usuario or not password:
        cfg_user, cfg_pass = _sap_creds()
        usuario = usuario or cfg_user
        password = password or cfg_pass
    if not usuario or not password:
        return {"success": False, "error": "Faltan credenciales SAP (config.json: sap_user/sap_password)"}

    result = {"success": False, "error": None, "url_final": "", "desconectado_mora": None}

    if not CHROME_PATH:
        return {**result, "error": "Chrome no encontrado"}

    debug_dir = Path(tempfile.mkdtemp(prefix="sap_"))
    debug_port = find_free_port()
    proc = None

    try:
        proc = launch_chrome(
            debug_port, debug_dir,
            window_size="1400,900", extra_args=["--ignore-certificate-errors"],
        )
        log.info("Chrome PID=%s", proc.pid)
        wait_for_cdp(debug_port)

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

            # --- LLENAR SOLO EL RUT + BUSCAR CUENTA ---
            # SAP CRM usa iframes anidados; el campo puede estar en cualquiera,
            # así que se prueba en TODOS los frames de la página.
            # RUT sin puntos y CON guion antes del DV (ej. 16333784-3), reconstruido
            # venga como venga el origen.
            _rc = (datos or {}).get("rut", "").replace(".", "").replace("-", "").strip().upper()
            rut = (_rc[:-1] + "-" + _rc[-1]) if len(_rc) > 1 else _rc

            if rut:
                log.info("Ingresando RUT en SAP: %s", rut)

                fill_js = """(rut) => {
                    let input = null;
                    const labels = Array.from(document.querySelectorAll('label, span, div.urTxtLbl, td, th'));
                    const label = labels.find(l => ((l.innerText||'').trim().toUpperCase().replace(/[:.]/g,'')) === 'RUT')
                               || labels.find(l => (l.innerText||'').toUpperCase().includes('RUT'));
                    if (label) {
                        const forId = label.getAttribute('for');
                        if (forId) input = document.getElementById(forId);
                        if (!input) {
                            let el = label.nextElementSibling;
                            while (el && !input) {
                                if (el.tagName === 'INPUT') input = el;
                                else if (el.querySelector) input = el.querySelector('input');
                                el = el.nextElementSibling;
                            }
                        }
                        if (!input && label.parentElement) input = label.parentElement.querySelector('input');
                    }
                    if (!input) input = document.querySelector('input[placeholder*="RUT" i], input[id*="rut" i], input[name*="rut" i]');
                    if (input) {
                        input.focus();
                        input.value = rut;
                        input.dispatchEvent(new Event('input', {bubbles:true}));
                        input.dispatchEvent(new Event('change', {bubbles:true}));
                        return 'ok:' + (input.id || input.name || 'sin-id');
                    }
                    return 'no';
                }"""

                # El formulario de cuenta carga en un frame anidado que tarda en
                # aparecer: reintentar en TODOS los frames hasta ~40s.
                rut_frame = None
                for _ in range(20):
                    for fr in page.frames:
                        try:
                            res = await fr.evaluate(fill_js, rut)
                        except Exception:
                            continue
                        if res and res.startswith('ok'):
                            rut_frame = fr
                            log.info("Campo RUT OK en frame %s -> %s", (fr.url or '')[:60], res)
                            break
                    if rut_frame:
                        break
                    await page.wait_for_timeout(2000)

                if rut_frame:
                    # Enter en el campo RUT para disparar la búsqueda de cuenta.
                    # locator.press() manda un KeyboardEvent nativo (Frame no expone
                    # .keyboard). El input de SAP tiene "zztaxnum" en el id (número
                    # de identificación tributaria = RUT).
                    try:
                        await rut_frame.locator('input[id*="zztaxnum"]').first.press("Enter")
                        await page.wait_for_timeout(1000)
                        log.info("Enter presionado en campo RUT — búsqueda disparada")
                    except Exception as e:
                        log.warning("Error presionando Enter (locator): %s — fallback JS", e)
                        try:
                            await rut_frame.evaluate("""() => {
                                const el = document.activeElement || document.querySelector('input[id*="zztaxnum"]');
                                if (el) ['keydown','keypress','keyup'].forEach(t =>
                                    el.dispatchEvent(new KeyboardEvent(t, {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true})));
                            }""")
                            await page.wait_for_timeout(1000)
                            log.info("Enter (fallback JS) enviado al campo RUT")
                        except Exception as e2:
                            log.warning("Fallback Enter también falló: %s", e2)
                else:
                    log.warning("Campo RUT no encontrado tras esperar — dump de inputs visibles:")
                    for fr in page.frames:
                        try:
                            info = await fr.evaluate(
                                """() => Array.from(document.querySelectorAll('input,select,textarea'))
                                    .filter(el => el.offsetParent !== null)
                                    .slice(0,40)
                                    .map(el => (el.tagName+' id='+el.id+' name='+el.name+' ph='+(el.placeholder||'')+' type='+(el.type||'')))"""
                            )
                        except Exception:
                            continue
                        if info:
                            log.info("  frame %s:", (fr.url or '')[:70])
                            for it in info:
                                log.info("    %s", it)

                # --- Leer "Desconectado por mora" (Sí/No) ---
                # Tras el Enter abre "Identificar cuenta"; el campo está en el menú
                # izquierdo "Hoja informativa de cuenta". Se clickea ese menú y se lee
                # el valor de la caja de texto al lado del rótulo.
                await page.wait_for_timeout(8000)
                for fr in page.frames:
                    try:
                        r = await fr.evaluate("""() => {
                            const norm = s => (s||'').replace(/\\s+/g,' ').trim().toLowerCase();
                            const el = Array.from(document.querySelectorAll('a,td,span,div'))
                                .find(x => norm(x.innerText) === 'hoja informativa de cuenta');
                            if (el) { (el.closest('a') || el).click(); return true; }
                            return false;
                        }""")
                    except Exception:
                        continue
                    if r:
                        log.info("Click en 'Hoja informativa de cuenta'")
                        break
                await page.wait_for_timeout(8000)

                mora_js = """() => {
                    const norm = s => (s||'').replace(/\\s+/g,' ').trim();
                    const valOf = el => { const i = el && el.querySelector ? el.querySelector('input,textarea,select') : null;
                                          return i ? (i.value||'') : (el ? norm(el.innerText) : ''); };
                    for (const el of Array.from(document.querySelectorAll('td,span,label,div'))) {
                        const t = norm(el.innerText || '');
                        if (!t || t.length > 60) continue;
                        if (!t.toLowerCase().includes('desconectado por mora')) continue;
                        let val = '';
                        const td = el.closest('td');
                        if (td && td.nextElementSibling) val = valOf(td.nextElementSibling);
                        if (!val && el.nextElementSibling) val = valOf(el.nextElementSibling);
                        if (!val && td && td.parentElement) { const inp = td.parentElement.querySelector('input,textarea'); if (inp) val = inp.value || ''; }
                        if (val) return norm(val);
                    }
                    return null;
                }"""
                for fr in page.frames:
                    try:
                        val = await fr.evaluate(mora_js)
                    except Exception:
                        continue
                    if val:
                        result["desconectado_mora"] = val
                        log.info("SAP: Desconectado por mora = %s", val)
                        break
                if result.get("desconectado_mora") is None:
                    log.warning("No se pudo leer 'Desconectado por mora'")
            else:
                log.info("Sin RUT para ingresar en SAP")

            result["success"] = True
            log.info("Proceso SAP completado — Chrome abierto 5 min")
            await asyncio.sleep(300)

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
    usuario: Optional[str] = None,
    password: Optional[str] = None,
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
