# Rose — tag-admin.integrocorp.cl

Bot que extrae RUT, patente y nombre completo desde PDFs de un desk en tag-admin.integrocorp.cl (Laravel Sanctum + Next.js).

## Uso
```bash
pip install -r requirements.txt
python bot.py                  # CLI, usa config.json (desk 498978)
python bot.py --desk 498981    # otro ticket
python gui.py                  # GUI con input de ticket + foto + log
.\dist\Rose.exe                # standalone (no requiere Python)
```

## Dependencias
- `requests`, `beautifulsoup4`, `PyPDF2`, `Pillow`

## Arquitectura
- `bot.py` — login Sanctum, fetch RSC desde Next.js, parse ticket + URLs S3, descarga PDFs, extrae RUT/patente/nombre con regex
- `gui.py` — tkinter: input ticket, resultados (Nombre/RUT/Patente/Email/Solicitud), foto con navegacion, log toggle, copiar por campo

## Sesiones

> **Nota**: "conmitea" = commit + push + guardar AGENTS.md en un solo paso.

### 2026-06-30 — OCR + Status (APROBADO / RECHAZADO)
- **OCR con Tesseract**: descarga imágenes (JPG/PNG), extrae texto con `tesseract-ocr` + `spa.traineddata` (descargado automáticamente a `~/.tessdata/`)
- **check_vigente_optimo()**: busca en texto de PDFs e imágenes:
  - `% similitud` (regex `(\d+[.,]?\d*)\s*%\s*similitud`)
  - "NO VIGENTE" / "VIGENTE" / "RECHAZADO" / "OPTIMO"
  - Si `% similitud >= 80` y no hay "NO VIGENTE" → VIGENTE
  - Si `% similitud >= 95` → OPTIMO inferido
- **Criterio STATUS final** (en ese orden, primera condición que se cumple):
  1. RUT inconsistente entre documentos → **RECHAZADO (RUT inconsistente)**
  2. "RECHAZADO" en texto → **RECHAZADO (RECHAZADO)**
  3. "NO VIGENTE" en texto → **RECHAZADO (NO VIGENTE)**
  4. `% similitud < 80` → **RECHAZADO (X.XX% similitud)**
  5. `% similitud >= 80` y ninguno de los anteriores → **APROBADO**
  6. Sin datos de verificación → **PENDIENTE**
- STATUS en GUI muestra los motivos acumulados, ej: `RECHAZADO (RUT inconsistente, NO VIGENTE, 0.00% similitud)`
- `requirements.txt`: +`pytesseract`
- Dependencia sistema: `tesseract-ocr` (winget: `UB-Mannheim.TesseractOCR`)
- `bot.py` ahora acepta `--desk N` (CLI) y también descarga + OCR imágenes
- `gui.py`: importa `check_vigente_optimo`, `download_img`, `ocr_image` de bot; procesa PDFs + imágenes y muestra STATUS en color

### 2026-06-30 — Servipag: consulta de deudas TAG
- **`servipag.py`**: consulta deudas en Servipag usando Chrome CDP (subprocess + Playwright connect_over_cdp) para evitar deteccion de Cloudflare Turnstile
- Lanza Chrome directamente (sin flags de automatizacion), conecta via `--remote-debugging-port`, interactua con la SPA: selecciona empresa → ingresa RUT → click Continuar → parsea resultado
- `EMPRESAS` dict con 15 autopistas (Pago Total TAG, Autopista Central, Costanera Norte, etc.)
- `gui.py`: seccion Servipag en panel Resultado con Combobox de empresa + boton "Ver Deudas"
- Popup con detalle de deudas si las hay; status "Sin deudas ✓" si no
- `requirements.txt` actualizado con `playwright>=1.40`

### 2026-06-30 — Direccion + telefono
- Extraccion de direccion (`su domicilio es...`) y telefono (`+56 ...`) desde PDF/ticket
- Nuevos campos en GUI: Direccion y Telefono
- Icono BMP en .exe para Explorer

### 2026-06-29 — Rose final
- Proyecto renombrado a **Rose** (carpeta + GitHub)
- Proyecto renombrado a **Rose** (carpeta + GitHub)
- Icono de rosa en `.exe` (PyInstaller `--icon`) y en ventana tkinter (`iconbitmap`)
- `BASE_DIR` junto al .exe para encontrar `config.json`
- Ventana posicionada en esquina superior izquierda
- Título "Rose"

### 2026-06-29 — Sesiones previas (integro-rut-bot → Rose)
- `gui.py`: interfaz grafica, boton Copiar, validacion RUT, foto, navegacion, log toggle, pegar
- `.exe` standalone (PyInstaller), RUT sin puntos/guion al copiar
- Push a `github.com/Arnaldolandin/integro-rut-bot`
