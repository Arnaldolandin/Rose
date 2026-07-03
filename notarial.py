"""
Módulo Notarial: verifica una copia notarial electrónica por su CVE (Código de
Verificación Electrónica) en el repositorio de registros notariales de Chile.

A diferencia de los otros módulos de verificación, este es HTTP puro (sin Chrome
ni CDP): el portal ajs.cl/validacion.php, para documentos notariales (radio
"NOTA"), consulta un REST GET sin captcha:

    GET https://repositorio.registrosnotariales.cl:8181/rest/api/verificar/{cve}

Respuesta JSON:
    - válido:  {"error": false, "url": "...pdf", "datosDocumento": {...}, "cadenaCertificacion": [...]}
    - inválido:{"error": true,  "mensaje": "No existe documento con código ..."}
"""

import logging

import requests

log = logging.getLogger("notarial")

VERIF_URL = "https://repositorio.registrosnotariales.cl:8181/rest/api/verificar/"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": "https://ajs.cl/validacion.php",
    "Accept": "application/json, text/plain, */*",
}


def verificar_cve(cve: str, intentos: int = 2) -> dict:
    """Verifica un CVE notarial. Con reintento ante fallos de red transitorios.

    Returns dict con: success, cve, valido, mensaje, url, notaria, materia,
    repertorio, fecha, error.
    """
    result = {
        "success": False,
        "cve": cve,
        "valido": None,
        "mensaje": None,
        "url": None,
        "notaria": None,
        "materia": None,
        "repertorio": None,
        "fecha": None,
        "error": None,
    }
    if not cve:
        return {**result, "error": "CVE vacío"}

    url = VERIF_URL + cve.strip()
    for intento in range(1, intentos + 1):
        try:
            r = requests.get(url, headers=_HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
            result["success"] = True
            if data.get("error"):
                result["valido"] = False
                result["mensaje"] = data.get("mensaje") or "Documento no encontrado"
                log.info("CVE %s: NO válido — %s", cve, result["mensaje"])
            else:
                d = data.get("datosDocumento") or {}
                result["valido"] = True
                result["url"] = data.get("url")
                result["notaria"] = d.get("notaria")
                result["materia"] = d.get("materia")
                result["repertorio"] = d.get("repertorio")
                result["fecha"] = d.get("fechaRepertorio")
                result["mensaje"] = "Documento verificado"
                log.info("CVE %s: VÁLIDO — notaría=%s materia=%s repertorio=%s",
                         cve, result["notaria"], result["materia"], result["repertorio"])
            return result
        except Exception as e:
            result["error"] = str(e)
            if intento < intentos:
                log.warning("CVE intento %s/%s falló (%s); reintentando...",
                            intento, intentos, e)
    log.warning("CVE %s: verificación no disponible (%s)", cve, result["error"])
    return result


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    import sys
    codigo = sys.argv[1] if len(sys.argv) > 1 else "076-2026062612154388"
    res = verificar_cve(codigo)
    print("\n=== RESULTADO CVE ===")
    for k, v in res.items():
        print(f"  {k}: {v}")
