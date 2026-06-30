#!/usr/bin/env python3
"""
Bot: tag-admin.integrocorp.cl → descarga PDFs + imágenes de un desk
     → extrae RUT, patente, verifica vigencia/optimidad.

Flujo:
  1. Login Laravel Sanctum (tag-back.integrocorp.cl)
  2. GET /admin/desk/{id} → extrae RSC data embebido (Next.js)
  3. Parse ticket data y URLs de archivos (S3)
  4. Descarga PDFs e imágenes desde S3 (sin auth)
  5. Extrae texto con PyPDF2 (PDFs) + Tesseract OCR (imágenes)
  6. Busca RUT, patente, vigencia y optimidad

Uso:
    python bot.py
    python bot.py --desk 498978
"""

import argparse
import json
import logging
import re
import sys
from io import BytesIO
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

try:
    import pytesseract.pytesseract as pytesseract_impl
    import pytesseract
    from PIL import Image
    import os
    pytesseract_impl.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    # Asegurar que TESSDATA_PREFIX apunte a una carpeta con spa.traineddata
    if not os.environ.get("TESSDATA_PREFIX"):
        _td = Path.home() / ".tessdata"
        _td.mkdir(exist_ok=True)
        _lang = _td / "spa.traineddata"
        if not _lang.exists():
            import urllib.request
            print("[BOT] Descargando spa.traineddata...")
            urllib.request.urlretrieve(
                "https://github.com/tesseract-ocr/tessdata/raw/main/spa.traineddata",
                str(_lang)
            )
        os.environ["TESSDATA_PREFIX"] = str(_td)
except ImportError:
    pytesseract = None
    pytesseract_impl = None
    Image = None

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
                      "fechaCreacion", "email", "telefono", "direccion"]:
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


def download_img(session: requests.Session, url: str, dest: Path, idx: int) -> Optional[Path]:
    """Descarga imagen (jpg/png) desde S3."""
    log.info("Descargando imagen %s: %s", idx, url[:80])
    try:
        r = session.get(url, timeout=60, stream=True)
        r.raise_for_status()
    except Exception as e:
        log.warning("  Error descargando: %s", e)
        return None

    ct = r.headers.get("Content-Type", "").lower()
    raw = r.content
    if "image" not in ct and raw[:4] not in (b"\xff\xd8\xff\xe0", b"\x89PNG"):
        log.warning("  No es imagen (Content-Type: %s)", ct)
        return None

    # Nombre desde URL
    fname = url.rstrip("/").split("/")[-1].split("?")[0]
    if not fname.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
        fname = f"image_{idx}.png"
    path = dest / fname
    path.write_bytes(raw)
    log.info("  -> %s (%s bytes)", path.name, len(raw))
    return path


def ocr_image(path: Path) -> str:
    if pytesseract is None:
        log.error("pip install pytesseract")
        return ""
    try:
        img = Image.open(path)
        text = pytesseract.image_to_string(img, lang="spa")
        log.info("  OCR: %s chars", len(text))
        return text
    except Exception as e:
        log.warning("  Error OCR en %s: %s", path.name, e)
        return ""


SIMILITUD_RE = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s*%\s*similitud", re.IGNORECASE)


def check_vigente_optimo(text: str) -> dict:
    """Busca en el texto (PDF/OCR) estado de verificación y % similitud."""
    result = {
        "vigente": None,
        "optimo": None,
        "rechazado": False,
        "no_vigente": False,
        "similitud_pct": None,
    }

    # Similitud porcentual
    sm = SIMILITUD_RE.search(text)
    if sm:
        try:
            result["similitud_pct"] = float(sm.group(1).replace(",", "."))
        except ValueError:
            pass

    # NO VIGENTE explícito
    if re.search(r"NO\s*VIGENTE", text, re.IGNORECASE):
        result["no_vigente"] = True
        result["vigente"] = False

    # "VIGENTE" suelto sin "NO" antes
    vig = re.search(r"(?<!\bNO\s)VIGENTE\b", text, re.IGNORECASE)
    if vig and not re.search(r"NO\s+VIGENTE", text[max(0, vig.start() - 10):vig.end()], re.IGNORECASE):
        result["vigente"] = True

    # Si hay % similitud >= 50 y no hay NO VIGENTE, inferir VIGENTE
    if result["similitud_pct"] is not None and result["no_vigente"] is False:
        if result["similitud_pct"] >= 50.0:
            result["vigente"] = True
        else:
            result["vigente"] = False

    # ÓPTIMO inferido si similitud >= 95
    if result["similitud_pct"] is not None and result["similitud_pct"] >= 95.0:
        result["optimo"] = True

    # "OPTIMO" explícito
    if re.search(r"OPTIM[OA]", text, re.IGNORECASE):
        result["optimo"] = True

    # Rechazado
    if re.search(r"RECHAZADO", text, re.IGNORECASE):
        result["rechazado"] = True
        result["vigente"] = False

    return result


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
# Telefono chileno: +56 2 XXX XXXX o +56 9 XXXX XXXX
TELEFONO_RE = re.compile(r"\+56\s*\d\s*\d{3,4}\s*\d{3,4}")

# Direccion: texto entre "domicilio es" y la proxima coma/punto
DIRECCION_RE = re.compile(
    r"domicilio es\s+(.+?)(?:,|oblig[áa]ndose|\.)",
    re.IGNORECASE,
)

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


def validar_rut(rut: str) -> bool:
    limpio = rut.replace(".", "").replace("-", "").strip()
    if not limpio or limpio[-1].upper() not in "0123456789K":
        return False
    cuerpo = limpio[:-1]
    dv = limpio[-1].upper()
    if not cuerpo.isdigit():
        return False
    suma = 0
    multiplo = 2
    for d in reversed(cuerpo):
        suma += int(d) * multiplo
        multiplo = 2 if multiplo == 7 else multiplo + 1
    resto = suma % 11
    dv_calc = 11 - resto
    if dv_calc == 11:
        dv_calc = "0"
    elif dv_calc == 10:
        dv_calc = "K"
    else:
        dv_calc = str(dv_calc)
    return dv == dv_calc


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


def find_telefono(text: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in TELEFONO_RE.findall(text):
        raw = raw.strip()
        if raw and raw not in seen:
            seen.add(raw)
            result.append(raw)
    return result


def find_direccion(text: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for m in DIRECCION_RE.finditer(text):
        raw = m.group(1).strip()
        raw = re.sub(r"\s+", " ", raw)
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

    # --- Descargar PDFs ---
    found_names: dict[str, list[str]] = {}
    found_ruts: dict[str, list[str]] = {}
    found_patentes: dict[str, list[str]] = {}
    vigente_optimo: dict[str, dict] = {}

    for i, file in enumerate(pdfs, 1):
        p = download_pdf(session, file["url"], args.out, i)
        if not p:
            continue
        text = extract_text(p)
        if not text:
            log.info("  PDF sin texto extraible (escaneado?) — %s", p.name)
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
        vo = check_vigente_optimo(text)
        if vo["vigente"] is not None or vo["optimo"] is not None or vo["rechazado"] or vo.get("similitud_pct") is not None:
            vigente_optimo[p.name] = vo
            log.info("  Estados: vigente=%s optimo=%s rechazado=%s similitud=%s",
                     vo["vigente"], vo["optimo"], vo["rechazado"], vo.get("similitud_pct"))
        if not ruts and not patentes:
            log.info("  Sin RUTs ni patentes en este PDF")

    # --- Descargar imágenes y OCR ---
    for i, file in enumerate(imgs, 1):
        p = download_img(session, file["url"], args.out, i)
        if not p:
            continue
        text = ocr_image(p)
        if not text:
            continue
        log.info("  OCR: %s chars", len(text))
        ruts = find_ruts(text)
        if ruts:
            found_ruts[p.name] = ruts
            log.info("  RUTs: %s", ", ".join(ruts))
        vo = check_vigente_optimo(text)
        if vo["vigente"] is not None or vo["optimo"] is not None or vo["rechazado"] or vo.get("similitud_pct") is not None:
            vigente_optimo[p.name] = vo
            log.info("  Estados OCR: vigente=%s optimo=%s rechazado=%s similitud=%s",
                     vo["vigente"], vo["optimo"], vo["rechazado"], vo.get("similitud_pct"))
        nombres = find_nombres(text)
        if nombres:
            found_names[p.name] = nombres
            log.info("  Nombres OCR: %s", " | ".join(nombres))

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
        print(f"  Solicitud:  {desk}")

    # --- Validación de RUT coincidente ---
    print("\n" + "-" * 60)
    print("VALIDACION")
    print("-" * 60)

    ticket_rut = ticket.get("rut", "") if ticket else ""
    rut_ticket_normalized = _normalize(ticket_rut) if ticket_rut else None

    if all_ruts:
        if len(all_ruts) == 1:
            print(f"  [OK] RUT unico en todos los docs: {all_ruts[0]}")
        else:
            print(f"  [WARN] RUTs multiples: {', '.join(all_ruts)}")
        if rut_ticket_normalized and rut_ticket_normalized in all_ruts:
            print(f"  [OK] RUT del ticket coincide con docs")
        elif rut_ticket_normalized:
            print(f"  [WARN] RUT ticket ({rut_ticket_normalized}) NO esta en docs")
    else:
        print(f"  [WARN] No se encontraron RUTs en ningun documento")

    # --- Validación vigente/optimo + % similitud ---
    vo_global = {"vigente": None, "optimo": None, "rechazado": False, "no_vigente": False, "similitud_pct": None}
    for fname, vo in vigente_optimo.items():
        if not vo_global["no_vigente"] and vo.get("no_vigente"):
            vo_global["no_vigente"] = True
        if not vo_global["rechazado"] and vo.get("rechazado"):
            vo_global["rechazado"] = True
        if vo["vigente"] is False:
            vo_global["vigente"] = False
        elif vo["vigente"] is True and vo_global["vigente"] is None:
            vo_global["vigente"] = True
        if vo["optimo"] is True:
            vo_global["optimo"] = True
        if vo.get("similitud_pct") is not None:
            vo_global["similitud_pct"] = vo["similitud_pct"]

    print(f"  Verificacion identidad:", end="")
    if vo_global["similitud_pct"] is not None:
        print(f" % similitud: {vo_global['similitud_pct']:.2f}%", end="")
    if vo_global["vigente"] is True:
        print(" VIGENTE", end="")
    elif vo_global["vigente"] is False:
        print(" NO VIGENTE", end="")
    if vo_global["optimo"] is True:
        print(" OPTIMO", end="")
    if vo_global["rechazado"]:
        print(" RECHAZADO", end="")
    if vo_global["no_vigente"]:
        print(" (no_vigente)", end="")
    print()

    print()

    # --- STATUS FINAL ---
    rut_ok = len(all_ruts) <= 1 or (rut_ticket_normalized and rut_ticket_normalized in all_ruts)
    doc_rechazado = vo_global["vigente"] is False or vo_global["rechazado"] or vo_global["no_vigente"]

    if doc_rechazado:
        print("  STATUS: RECHAZADO")
    elif rut_ok:
        print("  STATUS: APROBADO")
    else:
        print("  STATUS: RUT INCONSISTENTE")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
