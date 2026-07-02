"""
Utilidades compartidas para los módulos de verificación vía Chrome CDP
(servipag, sii, rvm, robos, sap).

Se lanza Chrome real por `subprocess` con `--remote-debugging-port` y luego se
conecta con `playwright.chromium.connect_over_cdp(...)`. Esto es deliberado:
lanzar Chrome directamente (en vez del navegador de Playwright) evade la
detección de bots de Cloudflare Turnstile. NO reemplazar por
`playwright.chromium.launch()`.

Este módulo sólo centraliza el boilerplate idéntico que estaba duplicado en cada
uno de esos archivos (descubrimiento de Chrome, puerto libre, lanzamiento y
espera de arranque). La lógica específica de cada portal sigue en su módulo.
"""

import socket
import subprocess
import shutil
import time
import urllib.request
from pathlib import Path

_CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def _discover_chrome() -> str | None:
    for p in _CHROME_CANDIDATES:
        if Path(p).exists():
            return p
    return shutil.which("chrome") or shutil.which("google-chrome")


CHROME_PATH = _discover_chrome()


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def launch_chrome(
    debug_port: int,
    debug_dir: Path,
    *,
    window_size: str = "1000,800",
    extra_args: list[str] | None = None,
    url: str | None = None,
    headless: bool = False,
) -> subprocess.Popen:
    """Lanza Chrome con el puerto de debug y devuelve el proceso.

    Los flags base son los mismos que usaban todos los módulos; `extra_args`
    permite las variaciones por portal (ej. `--ignore-certificate-errors` en SAP).
    """
    args = [
        CHROME_PATH,
        f"--user-data-dir={debug_dir}",
        f"--remote-debugging-port={debug_port}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-search-engine-choice-screen",
        f"--window-size={window_size}",
    ]
    if headless:
        args.append("--headless=new")
    if extra_args:
        args.extend(extra_args)
    if url:
        args.append(url)
    return subprocess.Popen(
        args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def wait_for_cdp(port: int, timeout: float = 20.0) -> bool:
    """Sondea el endpoint DevTools hasta que Chrome esté listo.

    Reemplaza el `time.sleep(6..8)` fijo: conecta apenas el puerto responde
    (normalmente 1-2s) en vez de esperar el peor caso.
    """
    endpoint = f"http://127.0.0.1:{port}/json/version"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(endpoint, timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.25)
    return False
