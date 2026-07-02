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

### 2026-06-30 — Razón social, batch, deuda threshold
- **Razón social**: nueva función `find_razon_social()` en bot.py extrae "Razón Social:" / "NOMBRE O RAZÓN SOCIAL:" de PDFs
- **Validación**: si hay razones sociales distintas entre documentos → STATUS incluye "Razón social inconsistente"
- **Bugfix RUT pisado**: datos del ticket tienen prioridad; PDFs ya no sobrescriben los campos mostrados
- **Similitud 80% → 90%**: umbral de coincidencia subido a 90% en todos los chequeos
- **`procesar_ticket()`**: función reusable que encapsula el análisis completo y devuelve dict con status/motivos/deudas
- **Batch CLI**: `python bot.py -b tickets.txt` procesa lista de tickets, consulta Servipag, reporte final
- **Batch GUI**: botón Batch lee tickets desde la caja de texto; un solo botón "Buscar" decide si es single o batch según cantidad
- **Caja de texto multilínea**: reemplaza el Entry por un Text widget (soporta pegar múltiples tickets)
- **Deuda threshold**: solo deudas ≥ $1.000.000 bloquean la aprobación (deudas menores se ignoran)
- Reporte batch muestra aprobados sin deudas y no aprobados con razón + monto de deuda si aplica

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

### 2026-06-30 — Bugfixes lupa, RUT OCR, Servipag auto
- **Bug RUT cambiaba solo**: OCR de cédula trasera (sin RUT) pisaba el RUT correcto del comprobante → OCR ya no sobrescribe ni se incluye en chequeo de consistencia (solo se loguea)
- **Bug "RUT inconsistente" falso**: Tesseract malinterpretaba texto de la parte trasera del carnet como RUT → OCR RUTs excluidos de `all_ruts_encontrados`
- **Servipag automático**: cuando STATUS = APROBADO, ejecuta "Ver Deudas" tras 500ms
- **Limpieza labels al buscar**: `_limpiar_resultados()` ahora también resetea Servipag status
- **Resumen de deuda(s)**: usa suma computada de todas las deudas individuales (no el `total` de Servipag que a veces es incorrecto)
- **Lupa con scroll**: zoom ajustable 1.0x–5.0x con rueda del mouse (bind al img_label)
- **Lupa corregida**: imagen con `anchor=tk.NW` para que coordenadas del mouse coincidan sin importar el tamaño de la ventana; caption separado en otro label
- **`gui.py`: `anchor=tk.NW`**, `_lupa_zoom`, `<MouseWheel>` binding, limpieza sp_status

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

## Session: 2026-07-01 — robos + RUT/NO_VIGENTE false positive fixes

### Cambios
- **`robos.py`** (nuevo): consulta encargo por robo en autoseguro.gob.cl vía Chrome CDP + Playwright.
  - Bypass reCAPTCHA con `Object.defineProperty` trap en `__bypassCaptchaValidation`.
  - Detección por safe keywords ("no mantiene") y robo keywords ("sustraído", "robado").
- **`gui.py`**: botón "Verificar Robo" + auto-check en `_do_buscar`.
- **`gui.py`**: RUT consistency ahora verifica que el ticket RUT esté presente en docs, no cuenta RUTs totales.
- **`bot.py`**: `check_vigente_optimo` — similitud ≥ 90% sobreescribe `no_vigente=False`.
- **`gui.py`**+**`bot.py`**: logging de `check_vigente_optimo` por documento y `status_global`.

### Problemas resueltos
1. **RUT inconsistente** (498926): documento con RUTs de adquiriente + empresa. Fix: verifica presencia del ticket RUT.
2. **NO VIGENTE** (498928): similitud 99.94% + "NO VIGENTE" de otro contexto. Fix: similitud ≥ 90% es autoritativa.
3. **reCAPTCHA autoseguro**: bypass con `Object.defineProperty`.

## Session: 2026-07-01 — FlateDecode image OCR + messagebox report + Servipag inline

### Cambios
- **`bot.py`**: `_ocr_pdf_images()` — para imágenes FlateDecode (no JPEG), ahora lee `/Width`, `/Height`, `/ColorSpace` del XObject y construye `PIL.Image.frombuffer()` en vez de escribir bytes crudos como `.png` inválido.
- **`gui.py`**: reporte final en `messagebox` con RUT, SII, RVM, Robo, Similitud, Emisión, Servipag. Servipag movido de async `after(500)` a inline con `_chrome_lock`. RVM bugfix: `rvm_res.get("mensaje", "Error")` → `rvm_res.get("mensaje") or "Error"`.
- **`gui.py`**: RVM log por archivo (keywords encontradas/no encontradas). Umbral Servipag ≥ $1.000.000 agrega motivo.

### Compilado
- `rose.exe` (64 MB) con PyInstaller, incluye `robos` como hidden import.

### HEAD
`7ef3922` fix: FlateDecode image OCR via Image.frombuffer() with Width/Height/ColorSpace

## Session: 2026-07-02 — Optimizaciones (sin cambios de comportamiento)

Refactors de rendimiento y mantenibilidad. **No** se tocó la lógica de estado
(APROBADO/RECHAZADO/PENDIENTE), regex de extracción ni la precedencia de motivos.

### Cambios
- **`bot.py` — doble extracción eliminada**: `procesar_ticket()` ahora cachea el
  texto de cada PDF en `textos_pdf: dict[Path, str]` durante el loop principal.
  La fase RVM reusa ese cache en vez de volver a `extract_text()` (que incluye
  OCR) sobre todos los PDFs con `out_dir.glob("*.pdf")`. Elimina una segunda
  ronda completa de OCR por ticket (mayor impacto en batch).
- **`bot.py` — OCR en memoria**: nuevo `_ocr_pil(img)` corre Tesseract sobre un
  `PIL.Image` directo. `_ocr_pdf_images()` ya no escribe cada imagen embebida a
  un `tempfile` para releerla (JPEG vía `Image.open(BytesIO(data))`, FlateDecode
  vía el `frombuffer` ya construido). `ocr_image(path)` delega en `_ocr_pil`.
  Se quitó `import tempfile` de bot.py.
- **`cdp_common.py` (nuevo)**: centraliza el boilerplate idéntico de los 5
  módulos CDP — `CHROME_PATH`, `find_free_port()`, `launch_chrome()` y
  `wait_for_cdp()`. Sigue lanzando Chrome real por subprocess (anti-Cloudflare);
  NO se migró a `playwright.chromium.launch()`.
- **`servipag/sii/rvm/robos/sap.py`**: usan `cdp_common`. El `time.sleep(6..8)`
  fijo tras lanzar Chrome se reemplazó por `wait_for_cdp()` que sondea el
  endpoint DevTools `/json/version` y conecta apenas está listo (~1-2s vs 6-8s).
  En un ticket APROBADO que dispara SII+RVM+robo+Servipag en serie son ~20-26s
  menos de espera fija.
- **`beautifulsoup4` eliminado**: `from bs4 import BeautifulSoup` en bot.py era
  import muerto (el RSC se parsea con regex). Removido de `requirements.txt` y de
  `Rose.spec` (hiddenimports). Spec ahora también lista `cdp_common`, `sii`, `rvm`.

### Verificación
- AST + import de los 8 módulos OK. Sin referencias colgantes a
  `subprocess`/`socket`/`_find_free_port`/`time.sleep`/`tempfile` en el código de
  lanzamiento de Chrome. Pendiente: prueba manual contra un ticket real.

### 2026-07-02 (cont.) — Normalización de patente + Robo/Servipag en paralelo

- **`bot.py` — `normalizar_patente()`**: nueva función que limpia la patente a su
  forma canónica chilena. Bug reportado: a veces la patente sale con símbolos
  intercalados (ej. `CYRD.72-1`) y autoseguro.gob.cl responde "matrícula no
  válida para Chile". Heurística: si hay separador de ruido (punto/·/espacio) se
  asume basura y se reduce a la matrícula de 6 chars (`CYRD72`); una patente ya
  limpia con sufijo interno (`PYKS20-4`) se conserva. **No** se tocó `PATENTE_RE`
  (sigue capturando el formato interno). Aplicada en `find_patentes` (por match),
  en `procesar_ticket` (`result["patente"]`) y en `gui.py` al mostrar la patente
  del ticket. `gui.py` importa `normalizar_patente`.
- **`gui.py` — Robo + Servipag en paralelo**: `_chrome_lock` pasó de `Lock()` a
  `Semaphore(2)` (permite 2 Chrome CDP simultáneos; cada módulo ya usa su propio
  `--user-data-dir`/puerto). En el flujo de reporte, Robo y Servipag se lanzan en
  dos threads a la vez. **Se preserva el orden semántico**: Robo se `join`ea ANTES
  de calcular `status_text` (su motivo "encargo por robo" afecta el resultado);
  Servipag se `join`ea DESPUÉS (su motivo de deuda no altera el status ya
  calculado, igual que antes). SII y RVM siguen en serie (SII cae en cola
  Queue-it). Ahorro ~15-20s por ticket APROBADO.
- **Riesgo**: el `Semaphore(2)` afloja el mutex que `f1c8b99` agregó para evitar
  conflictos de Chrome entre threads. Si aparecen cuelgues/fallos esporádicos de
  conexión CDP, volver a `Lock()`. Pendiente: prueba contra tickets reales.
