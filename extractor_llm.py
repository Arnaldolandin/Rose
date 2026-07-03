"""
Prototipo: extracción de compraventa de vehículo con un LLM (Claude).

Módulo APARTE — no está enganchado al pipeline. Sirve para comparar la extracción
con LLM contra los regex actuales (`bot.extraer_datos_transferencia`) sobre los
mismos documentos.

Idea: en vez de anclar regex al layout de cada notaría, se le pasa el documento a
Claude y devuelve los campos como JSON estructurado. Se puede pasar el PDF directo
(Claude hace OCR + extracción en un paso, sin Tesseract) o texto ya extraído.

La verificación (CVE en ajs.cl, SII, RVM) y la validación (dígito verificador,
formato de patente) siguen siendo del pipeline — el LLM solo extrae.

Requisitos:
    pip install anthropic
    ANTHROPIC_API_KEY en el entorno (o `ant auth login`).

Uso:
    python extractor_llm.py ruta/al/documento.pdf
"""

import base64
import logging
from pathlib import Path
from typing import Optional

try:
    import anthropic
    from pydantic import BaseModel, Field
except ImportError:
    anthropic = None
    BaseModel = object  # para que el archivo importe aunque falte la dependencia

log = logging.getLogger("extractor_llm")

# Opus 4.8 por defecto (más capaz). Para producción a volumen, Claude Sonnet 5
# ("claude-sonnet-5") da mejor costo/latencia con calidad muy cercana en extracción.
MODELO = "claude-opus-4-8"

_SYSTEM = """\
Eres un extractor de datos de documentos chilenos de compraventa de vehículos.
Recibes una "Solicitud de Transferencia" del Registro Civil (formulario con
secciones ACTUAL PROPIETARIO / ADQUIRENTE / SOLICITANTE) o una certificación
notarial electrónica de "COMPRAVENTA DE VEHÍCULOS" (portada con CVE + notaría, y
el contrato en prosa con Vendedor/Comprador).

Extrae los campos al esquema entregado. Reglas:
- rut_comprador = el ADQUIRENTE / COMPRADOR (nuevo dueño). rut_vendedor = el
  ACTUAL PROPIETARIO / VENDEDOR. Formato RUT chileno con guion (ej. 16.066.831-8).
- patente = la PPU/placa en su forma canónica SIN el dígito verificador final
  (ej. de "ZB.5004-3" -> "ZB5004"; de "LKPK16-7" -> "LKPK16").
- cve = el Código de Verificación Electrónica si el documento es notarial (ej.
  "076-2026062612154388"), si no, null.
- tipo = "transferencia_rc" para el formulario del Registro Civil, "notarial"
  para la certificación notarial.
- Si un campo no aparece, devuélvelo como null. No inventes datos.
- es_compraventa = false si el documento NO es una compraventa de vehículo."""

_INSTRUCCION = "Extrae los datos de compraventa de este documento."


if anthropic is not None:

    class CompraventaExtraida(BaseModel):
        es_compraventa: bool = Field(description="¿Es una compraventa de vehículo?")
        tipo: Optional[str] = Field(None, description="transferencia_rc | notarial")
        rut_comprador: Optional[str] = Field(None, description="RUT del adquirente/comprador (nuevo dueño)")
        rut_vendedor: Optional[str] = Field(None, description="RUT del propietario/vendedor")
        patente: Optional[str] = Field(None, description="PPU canónica sin dígito verificador")
        cve: Optional[str] = Field(None, description="Código de Verificación Electrónica (notarial)")
        notaria: Optional[str] = Field(None, description="Nombre de la notaría")
        fecha: Optional[str] = Field(None, description="Fecha del documento (DD-MM-AAAA)")


def extraer_con_llm(pdf_path: Optional[Path] = None, texto: Optional[str] = None,
                    modelo: str = MODELO) -> dict:
    """Extrae los datos de una compraventa con Claude y devuelve un dict.

    Pasar `pdf_path` (Claude OCR-ea el PDF escaneado directamente) o `texto`
    (OCR ya extraído). Devuelve el dict de campos, o {"error": ...} si falla.
    """
    if anthropic is None:
        return {"error": "Falta dependencia: pip install anthropic pydantic"}

    if not pdf_path and not texto:
        return {"error": "Pasar pdf_path o texto"}

    # Contenido del mensaje: PDF como bloque document (base64) o texto plano.
    contenido: list = []
    if pdf_path:
        data = base64.standard_b64encode(Path(pdf_path).read_bytes()).decode("utf-8")
        contenido.append({
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": data},
        })
        contenido.append({"type": "text", "text": _INSTRUCCION})
    else:
        contenido.append({"type": "text", "text": _INSTRUCCION + "\n\n" + texto})

    try:
        client = anthropic.Anthropic()
        resp = client.messages.parse(
            model=modelo,
            max_tokens=2048,
            system=_SYSTEM,
            messages=[{"role": "user", "content": contenido}],
            output_format=CompraventaExtraida,
        )
        if resp.stop_reason == "refusal":
            return {"error": "El modelo rechazó la solicitud (refusal)"}
        return resp.parsed_output.model_dump()
    except Exception as e:
        log.warning("Error extracción LLM: %s", e)
        return {"error": str(e)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    import sys
    if len(sys.argv) < 2:
        print("uso: python extractor_llm.py ruta/al/documento.pdf")
        sys.exit(1)

    pdf = Path(sys.argv[1])

    print("\n=== EXTRACCIÓN LLM (Claude, desde el PDF) ===")
    res_llm = extraer_con_llm(pdf_path=pdf)
    for k, v in res_llm.items():
        print(f"  {k}: {v}")

    # Comparación lado a lado con los regex actuales del pipeline
    try:
        from bot import extract_text, extraer_datos_transferencia
        print("\n=== EXTRACCIÓN REGEX (pipeline actual, desde OCR) ===")
        texto = extract_text(pdf, force_ocr_images=True)
        res_rx = extraer_datos_transferencia(texto)
        for k, v in res_rx.items():
            print(f"  {k}: {v}")
    except Exception as e:
        print(f"(no se pudo comparar con regex: {e})")
