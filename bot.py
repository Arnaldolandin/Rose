#!/usr/bin/env python3
"""
Bot: tag-admin.integrocorp.cl → descarga PDFs de un desk → extrae RUT y patente.

Flujo:
  1. Login Laravel Sanctum (tag-back.integrocorp.cl)
  2. GET /admin/desk/{id} → extrae RSC data embebido (Next.js)
  3. Parse ticket data y URLs de archivos (S3)
  4. Descarga PDFs desde S3 (sin auth)
  5. Extrae texto con PyPDF2 y busca RUT + patente chilena

Uso:
    python bot.py
    python bot.py --desk 498978
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("integro")

FRONTEND = "https://tag-admin.integrocorp.cl"
BACKEND = "https://tag-back.integrocorp.cl"

RUT_RE = re.compile(r"\b\d{1,2}(?:\.?\d{3}){2}[-]?[\dKk]\b")

# Patentes chilenas: new (BBBB·12), old (BB·1234), interno (PYKS20-4)
PATENTE_RE = re.compile(
    r"\b(?:"
    r"[A-Za-z]{4}[-·.\s]?\d{2}(?:[-][\dKk])?"     # nueva 4L2N + opcional guion digito
    r"|[A-Za-z]{2}[-·.\s]?\d{3,4}"                 # antigua 2L3-4N
    r")\b"
)

# Nombre completo: Don/Doña + 2+ palabras, o linea tras "Cliente"
NOMBRE_RE = re.compile(
    r"(?:"
    r"Cliente\s*\n\s*([A-ZÁÉÍÓÚÜÑa-záéíóúüñ]+(?:\s+[A-ZÁÉÍÓÚÜÑa-záéíóúüñ]+){2,})"
    r"|"
    r"(?:Don|Doña)\s+([A-ZÁÉÍÓÚÜÑa-záéíóúüñ]+(?:\s+[A-ZÁÉÍÓÚÜÑa-záéíóúüñ]+){2,})"
    r")",
    re.MULTILINE,
)

PDF_URL_RE = re.compile(r'(https?://[^"\'\\]*\.pdf[^"\'\\]*(?:[&\'\" ]|$))', re.I)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def sanctum_login(session: requests.Session, user: str, password: str) -> bool:
    log.info("1/3 — GET %s/sanctum/csrf-cookie", BACKEND)
    r = session.get(f"{BACKEND}/sanctum/csrf-cookie", timeout=30)
    r.raise_for_status()

    xsrf = None
    for k, v in r.raw.headers.items():
        if k.lower() == "set-cookie":
            m = re.search(r"XSRF-TOKEN=([^;]+)", v)
            if m:
                xsrf = unquote(m.group(1))
                break
    if not xsrf:
        xsrf = session.cookies.get("XSRF-TOKEN")
    if not xsrf:
        log.error("No se recibio cookie XSRF-TOKEN")
        return False

    log.info("2/3 — POST %s/login", BACKEND)
    r2 = session.post(
        f"{BACKEND}/login",
        json={"username": user, "password": password},
        headers={
            "X-XSRF-TOKEN": xsrf, "Accept": "application/json",
            "Content-Type": "application/json", "Origin": FRONTEND,
            "Referer": f"{FRONTEND}/auth/login",
        },
        timeout=30,
    )
    if r2.status_code >= 400:
        log.error("Login fallido (%s): %s", r2.status_code, r2.text[:200])
        return False

    log.info("3/3 — GET %s/api/user", BACKEND)
    r3 = session.get(
        f"{BACKEND}/api/user",
        headers={"Accept": "application/json", "Referer": f"{FRONTEND}/"},
        timeout=30,
    )
    if r3.status_code == 200:
        log.info("  Sesion OK — %s", r3.text[:100])
        return True
    log.error("Sesion NO verificada (%s)", r3.status_code)
    return False


# ---------------------------------------------------------------------------
# Extraccion de datos desde RSC
# ---------------------------------------------------------------------------


def fetch_desk_rsc(session: requests.Session, desk_id: int) -> str:
    """Obtiene el HTML del desk y extrae los scripts __next_f.push."""
    url = f"{FRONTEND}/admin/desk/{desk_id}"
    log.info("GET %s", url)
    r = session.get(url, timeout=30)
    r.raise_for_status()

    # Extraer scripts con __next_f.push
    chunks = []
    for m in re.finditer(r"self\.__next_f\.push\(\[([\s\S]*?)\]\)", r.text):
        raw = m.group(1)
        # Decodificar el string JSON que esta como segundo elemento del array
        # Formato: 1,"6:..."  o  [1,"6:..."]
        inner = re.sub(r'^\[?[^"]*', '', raw).strip()
        if inner.startswith('"'):
            try:
                decoded = json.loads(inner.rstrip(','))
                chunks.append(decoded)
            except json.JSONDecodeError:
                chunks.append(inner.strip('"'))
        else:
            chunks.append(raw)

    if not chunks:
        log.warning("No se encontraron scripts __next_f.push")
        return ""

    rsc_text = "\n".join(chunks)
    log.info("RSC extraido: %s chunks, %s chars", len(chunks), len(rsc_text))
    return rsc_text


def parse_ticket(rsc_text: str) -> Optional[dict]:
    """Busca el JSON 'ticket:{...}' en el RSC y parsea reemplazando \u0026."""
    # El RSC tiene el formato: "ticket":{...}}  (con comillas escapadas)
    m = re.search(r'"ticket"\s*:\s*(\{.+\})\s*\}', rsc_text, re.DOTALL)
    if not m:
        log.warning("No se encontro ticket en RSC")
        return None
    raw = m.group(1) + "}"
    # Reemplazar \u0026 por & y otros escapes
    raw = raw.replace('\\"', '"').replace('\\n', ' ')
    raw = raw.replace('\\u0026', '&').replace('\\u002F', '/')
    raw = re.sub(r'\\x[0-9a-fA-F]{2}', ' ', raw)
    # Reconstruir JSON valido
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        log.warning("Error parseando ticket JSON: %s", e)
        # Fallback por regex
        ticket = {}
        for key in ["id", "rut", "fullName", "patente", "autopista",
                      "precioServicio", "tipoTramite", "tipoVehiculo",
                      "fechaCreacion", "email", "telefono"]:
            m2 = re.search(rf'"{key}"\s*:\s*"([^"]*)"', raw)
            if m2:
                ticket[key] = m2.group(1).replace('\\u0026', '&')
        return ticket


def extract_file_urls(rsc_text: str) -> list[dict]:
    """Extrae URLs de S3, normalizando \u0026 a &."""
    files = []
    for m in re.finditer(
        r'"url"\s*:\s*"(https?://[^"]*)"', rsc_text
    ):
        url = m.group(1).replace('\\u0026', '&')
        ext = url.split("?")[0].rsplit(".", 1)[-1].lower() if "." in url else ""
        tipo = "pdf" if ext == "pdf" else "img" if ext in ("jpg", "jpeg", "png", "gif") else "otro"
        files.append({"url": url, "tipo": tipo})
    return files


# ---------------------------------------------------------------------------
# Descarga de PDFs
# ---------------------------------------------------------------------------


def download_pdf(session: requests.Session, url: str, dest: Path, idx: int) -> Optional[Path]:
    log.info("Descargando PDF %s: %s", idx, url[:80])
    try:
        r = session.get(url, timeout=60, stream=True)
        r.raise_for_status()
    except Exception as e:
        log.warning("  Error descargando: %s", e)
        return None

    ct = r.headers.get("Content-Type", "").lower()
    if "application/pdf" not in ct and r.content[:4] not in (b"%PDF",):
        log.warning("  No es PDF (Content-Type: %s)", ct)
        return None

    # Nombre desde Content-Disposition o URL
    fname = _filename(r, url, idx)
    path = dest / fname
    path.write_bytes(r.content)
    log.info("  -> %s (%s bytes)", path.name, len(r.content))
    return path


def _filename(resp: requests.Response, url: str, idx: int) -> str:
    cd = resp.headers.get("Content-Disposition", "")
    m = re.search(r'filename[^;=\n]*=["\']?([^"\';\n]*)', cd)
    if m:
        name = m.group(1).strip()
        if name.lower().endswith(".pdf"):
            return name
    name = url.rstrip("/").split("/")[-1].split("?")[0]
    if not name.lower().endswith(".pdf"):
        name = f"documento_{idx}.pdf"
    return name


# ---------------------------------------------------------------------------
# Texto + RUT
# ---------------------------------------------------------------------------


def extract_text(path: Path) -> str:
    if PyPDF2 is None:
        log.error("pip install PyPDF2")
        return ""
    try:
        with path.open("rb") as f:
            reader = PyPDF2.PdfReader(f)
            text = "\n".join(p.extract_text() or "" for p in reader.pages)
        log.info("  Texto: %s chars, %s paginas", len(text), len(reader.pages))
        return text
    except Exception as e:
        log.warning("  Error en %s: %s", path.name, e)
        return ""


def find_ruts(text: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in RUT_RE.findall(text):
        norm = _normalize(raw)
        if norm and norm not in seen:
            seen.add(norm)
            result.append(norm)
    return result


# Frases comunes que parecen nombres pero no lo son
_STOP_NAMES: set[str] = {
    "Servicio Monto Total",
    "Declaracion Jurada Simple",
    "Verificacion de identidad",
    "Verificacion del documento de identidad",
    "Resumen del proceso",
    "Obtu Tu Tag",
    "Codigo de verificacion",
    "Numero de solicitud",
}


def find_nombres(text: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for m in NOMBRE_RE.finditer(text):
        raw = m.group(1) or m.group(2) or m.group(0)
        raw = raw.strip()
        if not raw or raw in seen:
            continue
        # Filtrar frases genericas
        key = raw.replace("\n", " ").replace("  ", " ").strip()
        if key in _STOP_NAMES:
            continue
        seen.add(raw)
        result.append(key)
    return result


def find_patentes(text: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in PATENTE_RE.findall(text):
        raw = raw.strip().upper()
        if raw and raw not in seen:
            seen.add(raw)
            result.append(raw)
    return result


def _normalize(raw: str) -> Optional[str]:
    c = raw.replace(".", "").replace("-", "")
    if not c or not c[:-1].isdigit():
        return None
    dv = c[-1].upper()
    if dv not in "0123456789K":
        return None
    cuerpo = c[:-1]
    if len(cuerpo) <= 3:
        return f"{cuerpo}-{dv}"
    if len(cuerpo) <= 6:
        return f"{cuerpo[:-3]}.{cuerpo[-3:]}-{dv}"
    return f"{cuerpo[:-6]}.{cuerpo[-6:-3]}.{cuerpo[-3:]}-{dv}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Descarga PDFs de desk en tag-admin.integrocorp.cl y extrae RUTs."
    )
    p.add_argument("--user", "-u", default=None)
    p.add_argument("--password", "-p", default=None)
    p.add_argument("--desk", "-d", type=int, default=None)
    p.add_argument(
        "--config", "-c", type=Path, default=Path("./config.json"),
        help="JSON con user/password/desk (default config.json)",
    )
    p.add_argument("--out", "-o", type=Path, default=Path("./pdfs"))
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        log.setLevel(logging.DEBUG)

    args.out.mkdir(parents=True, exist_ok=True)

    cfg = {}
    if not args.user or not args.password or args.desk is None:
        cfg_path = args.config if args.config.exists() else Path("./config.json")
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            log.info("Config cargada desde %s", cfg_path)
    user = args.user or cfg.get("user")
    password = args.password or cfg.get("password")
    desk = args.desk if args.desk is not None else cfg.get("desk", 498978)
    if not user or not password:
        log.error("Se necesita --user y --password (o config.json)")
        return 1

    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )

    if not sanctum_login(session, user, password):
        return 1

    # --- Obtener datos del desk ---
    rsc = fetch_desk_rsc(session, desk)
    if not rsc:
        log.error("No se pudieron extraer datos RSC del desk %s", desk)
        return 1

    # --- Parsear ticket ---
    ticket = parse_ticket(rsc)
    if ticket:
        print(f"\n=== TICKET #{desk} ===")
        for k, v in ticket.items():
            if v:
                print(f"  {k}: {v}")
    else:
        print(f"\n=== TICKET #{desk} ===")
        print("  (no se pudo parsear JSON completo)")

    # --- Extraer URLs de archivos ---
    files = extract_file_urls(rsc)
    pdfs = [f for f in files if f["tipo"] == "pdf"]
    imgs = [f for f in files if f["tipo"] == "img"]

    print(f"\nArchivos encontrados: {len(pdfs)} PDF(s), {len(imgs)} imagen(es)")

    if not pdfs:
        log.warning("No se encontraron PDFs adjuntos")
        if imgs:
            log.info("(hay %s imagenes, pero el bot solo procesa PDFs)", len(imgs))
        return 0

    # --- Descargar PDFs ---
    found_names: dict[str, list[str]] = {}
    found_ruts: dict[str, list[str]] = {}
    found_patentes: dict[str, list[str]] = {}
    for i, file in enumerate(pdfs, 1):
        p = download_pdf(session, file["url"], args.out, i)
        if not p:
            continue
        text = extract_text(p)
        if not text:
            continue
        nombres = find_nombres(text)
        if nombres:
            found_names[p.name] = nombres
            log.info("  Nombres: %s", " | ".join(nombres))
        ruts = find_ruts(text)
        if ruts:
            found_ruts[p.name] = ruts
            log.info("  RUTs: %s", ", ".join(ruts))
        patentes = find_patentes(text)
        if patentes:
            found_patentes[p.name] = patentes
            log.info("  Patentes: %s", ", ".join(patentes))
        if not ruts and not patentes:
            log.info("  Sin RUTs ni patentes en este PDF")

    # --- Consolidar resultados ---
    all_names = list(dict.fromkeys([n for ns in found_names.values() for n in ns]))
    all_ruts = list(dict.fromkeys([r for rs in found_ruts.values() for r in rs]))
    all_pats = list(dict.fromkeys([p for ps in found_patentes.values() for p in ps]))

    print("\n" + "=" * 60)
    print("RESULTADO")
    print("=" * 60)
    print(f"  Nombre:     {all_names[0] if all_names else '(no encontrado)'}")
    print(f"  RUT:        {all_ruts[0] if all_ruts else '(no encontrado)'}")
    print(f"  Patente:    {all_pats[0] if all_pats else '(no encontrado)'}")
    if ticket:
        print(f"  Email:      {ticket.get('email','') or '(sin email)'}")
        print(f"  Solicitud:  #{desk}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
