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
from datetime import datetime, date
import json
import logging
import os
import re
import sys
import tempfile
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

    # Si hay % similitud >= 90, inferir VIGENTE
    if result["similitud_pct"] is not None and result["similitud_pct"] >= 90.0:
        result["vigente"] = True
        result["no_vigente"] = False
    elif result["similitud_pct"] is not None and result["similitud_pct"] < 90.0:
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
        # Si no hay texto, intentar extraer imágenes embebidas y OCR
        if not text.strip():
            log.info("  PDF sin texto, extrayendo imágenes para OCR...")
            text = _ocr_pdf_images(reader)
        return text
    except Exception as e:
        log.warning("  Error en %s: %s", path.name, e)
        return ""


def _ocr_pdf_images(reader) -> str:
    """Extrae imágenes embebidas de cada página del PDF y las OCR con Tesseract."""
    texts = []
    for i, page in enumerate(reader.pages):
        try:
            raw = page.get('/Resources')
            if raw is None:
                continue
            # raw puede ser IndirectObject → resolver con get_object()
            resources = raw.get_object() if hasattr(raw, 'get_object') else raw
            xobjects = resources.get('/XObject', {})
            for xname in xobjects:
                xobj = xobjects[xname].get_object()
                if xobj.get('/Subtype') != '/Image':
                    continue
                data = xobj.get_data()
                if not data:
                    continue
                # Verificar si es JPEG (DCTDecode) u otro formato
                if data[:2] == b'\xff\xd8':  # JPEG
                    ext = "jpg"
                else:
                    ext = "png"
                fd, img_path_str = tempfile.mkstemp(suffix=f".{ext}")
                img_path = Path(img_path_str)
                try:
                    os.close(fd)
                except Exception:
                    pass
                try:
                    img_path.write_bytes(data)
                    if pytesseract:
                        ocr_t = ocr_image(img_path)
                        if ocr_t.strip():
                            texts.append(ocr_t)
                finally:
                    try:
                        img_path.unlink()
                    except Exception:
                        pass
        except Exception as e:
            log.warning("  Error extrayendo imagen página %s: %s", i, e)
    combined = "\n".join(texts)
    if combined:
        log.info("  OCR de imágenes: %s chars", len(combined))
    return combined


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


FECHA_EMISION_RE = re.compile(
    r"(?:fecha\s*(?:de\s+)?)?emisi[oó]n\s*[:\s]*(\d{1,2})[/-](\d{1,2})[/-](\d{4})",
    re.I,
)
FECHA_GENERICA_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b")


def find_fecha_emision(text: str) -> Optional[date]:
    """Busca fecha de emisión en el texto del PDF.
    Primero busca con palabra clave 'emisión', luego cae a cualquier fecha.
    """
    m = FECHA_EMISION_RE.search(text)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    m = FECHA_GENERICA_RE.search(text)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    return None


RAZON_SOCIAL_RE = re.compile(
    r"(?:raz[oó]n\s*(?:social|de\s+la\s+sociedad)|nombre\s+o\s+raz[oó]n\s+social)\s*:\s*(.+?)(?:\n|$)",
    re.I,
)


def find_razon_social(text: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for m in RAZON_SOCIAL_RE.finditer(text):
        raw = m.group(1).strip().rstrip(".")
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
    p.add_argument(
        "--batch", "-b", type=Path, default=None,
        help="Archivo .txt con lista de tickets (uno por linea) para procesamiento por lotes",
    )
    return p.parse_args(argv)


def procesar_ticket(
    session: requests.Session,
    desk: int,
    out_dir: Path,
    *,
    check_servipag: bool = False,
    empresa_servipag: str = "Pago Total TAG",
) -> dict:
    """Procesa un ticket completo y devuelve dict con resultados."""
    from servipag import consultar_deudas

    result: dict = {
        "desk": desk,
        "rut": "",
        "nombre": "",
        "patente": "",
        "email": "",
        "status": "",
        "motivos": [],
        "rechazado": False,
        "deudas": None,
        "tiene_deudas": False,
        "total_deuda": 0,
    }

    rsc = fetch_desk_rsc(session, desk)
    if not rsc:
        result["status"] = "ERROR"
        result["motivos"] = ["No se pudo obtener datos del ticket"]
        return result

    ticket = parse_ticket(rsc)
    files = extract_file_urls(rsc)
    pdfs = [f for f in files if f["tipo"] == "pdf"]
    imgs = [f for f in files if f["tipo"] == "img"]

    # Datos del ticket
    nombre_ticket = (ticket or {}).get("fullName", "")
    rut_ticket = (ticket or {}).get("rut", "")
    patente_ticket = (ticket or {}).get("patente", "")
    email_ticket = (ticket or {}).get("email", "")
    direccion_ticket = (ticket or {}).get("direccion", "")
    telefono_ticket = (ticket or {}).get("telefono", "")

    result["rut"] = rut_ticket
    result["nombre"] = nombre_ticket
    result["patente"] = patente_ticket
    result["email"] = email_ticket

    # Procesar PDFs
    all_ruts_encontrados: list[str] = []
    all_razones_encontradas: list[str] = []
    status_global = {"vigente": None, "rechazado": False, "no_vigente": False, "similitud_pct": None}
    fecha_emision = None

    for i, file in enumerate(pdfs, 1):
        p = download_pdf(session, file["url"], out_dir, i)
        if not p:
            continue
        text = extract_text(p)
        if not text:
            continue
        ruts = find_ruts(text)
        if ruts:
            all_ruts_encontrados.extend(ruts)
        razones = find_razon_social(text)
        if razones:
            all_razones_encontradas.extend(razones)
        vo = check_vigente_optimo(text)
        if vo["vigente"] is False:
            status_global["vigente"] = False
        elif vo["vigente"] is True and status_global["vigente"] is None:
            status_global["vigente"] = True
        if vo["rechazado"]:
            status_global["rechazado"] = True
        if vo["no_vigente"]:
            status_global["no_vigente"] = True
        if vo.get("similitud_pct") is not None:
            status_global["similitud_pct"] = vo["similitud_pct"]
        fe = find_fecha_emision(text)
        if fe and (fecha_emision is None or fe < fecha_emision):
            fecha_emision = fe

    # OCR imágenes
    for i, file in enumerate(imgs, 1):
        p = download_img(session, file["url"], out_dir, i)
        if not p:
            continue
        text = ocr_image(p)
        if not text:
            continue
        vo = check_vigente_optimo(text)
        if vo["vigente"] is False:
            status_global["vigente"] = False
        elif vo["vigente"] is True and status_global["vigente"] is None:
            status_global["vigente"] = True
        if vo["rechazado"]:
            status_global["rechazado"] = True
        if vo["no_vigente"]:
            status_global["no_vigente"] = True
        if vo.get("similitud_pct") is not None and status_global["similitud_pct"] is None:
            status_global["similitud_pct"] = vo["similitud_pct"]

    # Status
    ruts_set = set(r.replace(".", "").replace("-", "") for r in all_ruts_encontrados if r)
    razones_set = set(r.upper().strip() for r in all_razones_encontradas if r)
    motivos: list[str] = []
    if len(ruts_set) > 1:
        motivos.append("RUT inconsistente")
    if len(razones_set) > 1:
        motivos.append("Razón social inconsistente")
    if status_global["rechazado"]:
        motivos.append("RECHAZADO")
    if status_global["no_vigente"] or status_global["vigente"] is False:
        motivos.append("NO VIGENTE")
    sim = status_global["similitud_pct"]
    if sim is not None and sim < 90:
        motivos.append(f"{sim:.2f}% similitud")
    hoy = date.today()
    if fecha_emision:
        dias = (hoy - fecha_emision).days
        if dias > 30:
            motivos.append(f"Documento vencido ({dias} días)")

    # SII verification (documentos tributarios verificables en SII)
    sii_resultado = None
    if rut_ticket and validar_rut(rut_ticket):
        try:
            from sii import consultar_sii
            log.info("Consultando SII para RUT %s...", rut_ticket)
            sii_resultado = consultar_sii(rut_ticket)
            if sii_resultado.get("success"):
                log.info("SII: razon_social=%s vigente=%s inicio=%s registrado=%s",
                         sii_resultado.get("razon_social"),
                         sii_resultado.get("vigente"),
                         sii_resultado.get("inicio_actividades"),
                         sii_resultado.get("registrado"))
                if sii_resultado.get("registrado") is False:
                    motivos.append("RUT no registrado en SII")
                if sii_resultado.get("vigente") is False:
                    motivos.append("NO VIGENTE en SII")
                # Verificar consistencia de razón social
                sii_name = sii_resultado.get("razon_social")
                if sii_name and razones_set:
                    sii_norm = re.sub(r'[^\w\s]', '', sii_name.upper()).strip()
                    docs_norm = [re.sub(r'[^\w\s]', '', r) for r in razones_set]
                    if not any(sii_norm in d or d in sii_norm for d in docs_norm):
                        motivos.append("Razón social no coincide con SII")
                        log.info("R.S. SII='%s' no coincide con documentos: %s",
                                 sii_name, " | ".join(razones_set))
            else:
                log.warning("SII no disponible: %s", sii_resultado.get("error"))
        except Exception as e:
            log.warning("Error consultando SII: %s", e)

    result["sii"] = sii_resultado

    # RVM verification (Certificado de Inscripción R.V.M. en Registro Civil)
    rvm_resultado = None
    try:
        for pdf_path in out_dir.glob("*.pdf"):
            text_rvm = extract_text(pdf_path)
            if not text_rvm:
                continue
            if "R.V.M." in text_rvm or "RVM" in text_rvm or "INSCRIPCION" in text_rvm.upper():
                from rvm import extraer_datos_rvm, verificar_rvm
                extraccion = extraer_datos_rvm(text_rvm)
                if extraccion["encontrado"]:
                    log.info("RVM extraído: folio=%s codigo=%s",
                             extraccion["folio"], extraccion["codigo_verificacion"])
                    rvm_resultado = verificar_rvm(
                        extraccion["folio"], extraccion["codigo_verificacion"]
                    )
                    if rvm_resultado.get("success"):
                        if rvm_resultado.get("valido") is True:
                            log.info("RVM: CERTIFICADO VÁLIDO ✓")
                        else:
                            motivos.append("Certificado RVM no válido")
                            log.info("RVM: certificado no válido")
                    else:
                        log.warning("RVM no disponible: %s", rvm_resultado.get("error"))
                    break  # Solo procesar el primer RVM encontrado
    except Exception as e:
        log.warning("Error verificando RVM: %s", e)

    result["rvm"] = rvm_resultado

    rechazado = bool(motivos)
    if rechazado:
        status_text = "RECHAZADO (" + ", ".join(motivos) + ")"
    elif sim is not None and sim >= 90:
        status_text = "APROBADO"
    else:
        status_text = "PENDIENTE"

    result["status"] = status_text
    result["motivos"] = motivos
    result["rechazado"] = rechazado

    # Servipag si aprobado
    if check_servipag and status_text == "APROBADO" and rut_ticket:
        try:
            deudas_res = consultar_deudas(rut_ticket, empresa_servipag)
            result["deudas"] = deudas_res
            if deudas_res.get("success") and not deudas_res.get("sin_deudas") and deudas_res.get("deudas"):
                total_deuda = sum(d.get("monto", 0) for d in deudas_res["deudas"])
                result["total_deuda"] = total_deuda
                if total_deuda >= 1_000_000:
                    result["tiene_deudas"] = True
        except Exception as e:
            log.warning("Error consultando Servipag para ticket %s: %s", desk, e)

    return result


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

    # --- Batch o single ---
    if args.batch:
        tickets_raw = args.batch.read_text(encoding="utf-8").strip()
        tickets = []
        for line in tickets_raw.splitlines():
            line = line.strip()
            if line and line.isdigit():
                tickets.append(int(line))
        if not tickets:
            log.error("No se encontraron tickets validos en %s", args.batch)
            return 1
        log.info("Procesando %s tickets en modo batch...", len(tickets))
        args.out.mkdir(parents=True, exist_ok=True)
        resultados: list[dict] = []
        for idx, tid in enumerate(tickets, 1):
            print(f"\n{'='*60}")
            print(f"TICKET #{tid} ({idx}/{len(tickets)})")
            print(f"{'='*60}")
            r = procesar_ticket(session, tid, args.out, check_servipag=True)
            resultados.append(r)
            # Limpiar carpeta entre tickets
            for f in args.out.iterdir():
                try:
                    f.unlink()
                except Exception:
                    pass
        # Reporte final
        print(f"\n\n{'='*60}")
        print("REPORTE FINAL — BATCH")
        print(f"{'='*60}")
        print()
        aprobados = [r for r in resultados if r["status"] == "APROBADO" and not r["tiene_deudas"]]
        no_aprobados = [r for r in resultados if r["status"] != "APROBADO" or r["tiene_deudas"]]
        print(f"Total procesados: {len(resultados)}")
        print(f"Aprobados sin deudas: {len(aprobados)}")
        print(f"No aprobados: {len(no_aprobados)}")
        print()
        if aprobados:
            print("--- APROBADOS SIN DEUDAS ---")
            for r in aprobados:
                print(f"  #{r['desk']}  {r['nombre'] or '?'}  RUT: {r['rut'] or '?'}")
        print()
        if no_aprobados:
            print("--- NO APROBADOS ---")
            for r in no_aprobados:
                if r["tiene_deudas"]:
                    razon = f"Deuda TAG: ${r['total_deuda']:,.0f}"
                elif r["motivos"]:
                    razon = ", ".join(r["motivos"])
                else:
                    razon = r["status"]
                deuda = f" [${r['total_deuda']:,.0f}]" if r["total_deuda"] else ""
                print(f"  #{r['desk']}  {r['nombre'] or '?'}  RUT: {r['rut'] or '?'}  → {razon}{deuda}")
        print()
        return 0

    # --- Modo single ticket ---
    r = procesar_ticket(session, desk, args.out)
    print(f"\n=== TICKET #{desk} ===")
    print(f"  Nombre:     {r['nombre'] or '(no encontrado)'}")
    print(f"  RUT:        {r['rut'] or '(no encontrado)'}")
    print(f"  Patente:    {r['patente'] or '(no encontrado)'}")
    print(f"  Email:      {r['email'] or '(sin email)'}")
    print(f"  Solicitud:  {desk}")
    print(f"  STATUS:     {r['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
