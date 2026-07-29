"""
Módulo Autofact: recupera los documentos de una transferencia de vehículo desde
docs.transferencias.autofact.cl.

El adjunto que llega en el ticket ("Documentos Adicionales") NO es un archivo: es
un link al visor SPA de Autofact — 364 bytes de HTML que cargan React. Los PDFs
reales están detrás de un API que la SPA consulta al arrancar:

    GET .../transference/document/tag/{token}/token/all

El `token` es el último segmento del path de la URL del visor. La respuesta es
JSON sin autenticación, y los `path` que devuelve son URLs directas a PDFs que se
descargan con `requests` como cualquier otro adjunto — por eso este módulo es HTTP
puro, sin Chrome ni CDP (igual que `notarial.py`).

Respuesta:
    {"status": "OK", "data": [
        {"path": "https://s3.amazonaws.com/.../TRxxxx.pdf",
         "documentModification": "2025-11-15 20:30:50",
         "transfer_documents": [{"transfer_document_type": {"name": "CONTRATO"}}]},
        ...]}

Los 5 documentos habituales son CONTRATO, CAV, CÉDULA DEL COMPRADOR, SOLICITUD
TRANSFERENCIA y COMPROBANTE TRANSFERENCIA DE VEHÍCULO — justo lo que necesita el
flujo de compraventa (`es_transferencia_compraventa` / `extraer_datos_transferencia`).
Sin este módulo esos tickets llegaban al pipeline sin un solo documento que
analizar: medido sobre 20 tickets al azar, era el 30% de ellos.
"""

import logging
import re
from typing import Optional

import requests

log = logging.getLogger("autofact")

AUTOFACT_HOST = "docs.transferencias.autofact.cl"

API_URL = (
    "https://xoyx149gh7.execute-api.us-east-1.amazonaws.com/latest/v2/transference/"
    "gateway/retail-api-transference/transference-wizard/v1/transference/"
    "document/tag/{}/token/all"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": f"https://{AUTOFACT_HOST}/",
    "Accept": "application/json, text/plain, */*",
}

# El token es un nanoid: alfanumérico con guiones, y puede empezar con "-"
# (visto en vivo: "-86XQlyQkKewO9FnUIpBK").
_TOKEN_RE = re.compile(rf"{re.escape(AUTOFACT_HOST)}/([A-Za-z0-9_-]+)")


def es_url_autofact(url: str) -> bool:
    return AUTOFACT_HOST in (url or "")


def extraer_token(url: str) -> Optional[str]:
    """Saca el token del path del visor: https://<host>/<token>"""
    m = _TOKEN_RE.search(url or "")
    return m.group(1) if m else None


def _parsear(payload: dict) -> list[dict]:
    docs: list[dict] = []
    for d in payload.get("data") or []:
        path = d.get("path")
        if not path:
            continue
        nombre = ""
        tipos = d.get("transfer_documents") or []
        if tipos:
            nombre = ((tipos[0] or {}).get("transfer_document_type") or {}).get("name") or ""
        docs.append({
            "url": path,
            "nombre": nombre or "documento",
            "fecha": d.get("documentModification") or "",
        })
    return docs


def listar_documentos(url_o_token: str, intentos: int = 2) -> list[dict]:
    """Devuelve [{url, nombre, fecha}] con los PDFs de la transferencia.

    Acepta la URL del visor o el token pelado. Ante cualquier fallo devuelve una
    lista vacía: el llamador debe seguir tratando el adjunto como no procesable,
    nunca asumir que el ticket no tiene documentos.
    """
    token = extraer_token(url_o_token) or (url_o_token or "").strip()
    if not token:
        log.warning("No se pudo extraer el token de: %s", (url_o_token or "")[:80])
        return []

    for intento in range(1, intentos + 1):
        try:
            r = requests.get(API_URL.format(token), headers=_HEADERS, timeout=30)
            if r.status_code == 200:
                docs = _parsear(r.json())
                if docs:
                    return docs
                log.warning("Autofact respondió 200 pero sin documentos (token %s)", token)
                return []
            log.warning("Autofact HTTP %s (token %s)", r.status_code, token)
        except Exception as e:
            log.warning("Autofact intento %s/%s falló: %s", intento, intentos, e)
    return []


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    import sys
    arg = sys.argv[1] if len(sys.argv) > 1 else "FQyshmMmEEz9xMBQZkBwv"
    for d in listar_documentos(arg):
        print(f"  {d['nombre']:38} {d['fecha']:20} {d['url']}")
