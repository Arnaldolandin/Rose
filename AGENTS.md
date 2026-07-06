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

### 2026-07-02 (cont.) — Servipag: "RUT no encontrado" intermitente

- **Causa**: efecto colateral del cambio `time.sleep(8)` → `wait_for_cdp()`.
  Servipag lanza Chrome CON la URL (`url=SERVIPAG_URL`), así que la página carga
  sola; el `sleep(8)` daba margen para que la SPA renderizara. `wait_for_cdp`
  retorna apenas responde el puerto de debug (~1-2s) y, como la URL ya es
  servipag, el flujo se saltaba el `goto`/espera y consultaba el selector de
  empresa / campo RUT antes de que existieran → el portal respondía "RUT no
  encontrado". Flaky: al reintentar, la SPA ya estaba caliente.
- **Fix** (`servipag.py`): tras el chequeo de Cloudflare, esperar explícitamente
  `page.wait_for_selector("#card-lib-rut-change", timeout=30000)` antes de
  interactuar. Más robusto que el sleep fijo (espera lo necesario, no un tiempo
  arbitrario) y conserva el ahorro de `wait_for_cdp`.
- Solo servipag estaba afectado: los otros módulos lanzan Chrome sin URL y hacen
  `page.goto(url, wait_until="load")` tras conectar, así que la carga siempre se
  espera bajo control de Playwright.
- **Red de seguridad — reintento automático** (`servipag.py`): `consultar_deudas()`
  ahora reintenta (default `intentos=2`) ante fallos transitorios vía
  `_fallo_reintentable()`. Reintenta si: `success=False` (error genérico/Cloudflare)
  o el `raw_text` dice "no encontrado". NO reintenta ante resultado definitivo
  (sin deudas o deudas encontradas) ni errores de config (Chrome/Playwright
  ausente, empresa desconocida). Cada intento relanza Chrome limpio. Firma
  compatible (gui/bot no cambian).
- **Reintento replicado a SII/RVM/Robo** (`sii.py`, `rvm.py`, `robos.py`): mismo
  patrón, cada uno con su `_fallo_reintentable()` adaptado al shape del resultado.
  Todos con `intentos=2` y **sin reintentar en modo `keep_open`** (debug deja el
  primer Chrome abierto). Reintentan ante:
  - SII: cualquier `success=False` (cola Queue-it, campo RUT ausente, datos no
    extraídos, excepción).
  - RVM: `success=False`, o `mensaje="No se pudo determinar"` (modal no apareció).
    NO reintenta el caso "sin código" (success=True, valido=None) ni un veredicto
    válido/no-válido definitivo.
  - Robo: cualquier `success=False`.
  - Ninguno reintenta errores de config (Chrome/Playwright ausente).

### 2026-07-03 — GUI: eliminar doble-extracción (mismo fix que bot.py)

- **`gui.py`**: el flujo de `_do_buscar` tenía la misma doble-extracción que se
  arregló en `bot.py`: el loop principal extraía texto de cada PDF (`extract_text`)
  y OCR-eaba cada imagen (`ocr_image`), y luego la sección RVM volvía a hacer
  `OUT_DIR.glob(...)` + `extract_text`/`ocr_image` sobre **todos** los archivos.
  Fix: cachear el texto por archivo en `textos_por_archivo: dict` durante el loop
  principal y reusarlo en RVM. Elimina una segunda ronda de OCR de imágenes +
  re-parseo de PDFs por búsqueda (lo más caro del flujo). Orden preservado
  (PDFs antes que imágenes; el `break` en el primer RVM encontrado sigue igual).
- **`gui.py`**: quitada una llamada redundante a `find_ruts(text)` (se calculaba
  dos veces por PDF; ahora se reusa `ruts`).
- Sin cambios de comportamiento.

### 2026-07-03 — Solicitud de Transferencia / compraventa (alternativa al RVM)

En lugar del RVM/padrón, a veces el solicitante sube la **Solicitud de
Transferencia del Registro Civil** basada en un contrato privado de compraventa
ante notario (PDF escaneado → OCR). Secciones: ACTUAL PROPIETARIO (vendedor) /
ADQUIRENTE (nuevo dueño) / SOLICITANTE, código PPU (patente), y datos del
documento (naturaleza COMPRAVENTA, fecha, notario). No hay folio+código
verificable online como el RVM.

- **`bot.py`**: `es_transferencia_compraventa()` + `extraer_datos_transferencia()`
  (patente vía ancla "PPU" — más confiable que `find_patentes`, que daba falso
  positivo `HORA08`; RUT de cada sección vía `_primer_rut_tras()` porque el OCR
  separa rótulos de valores; fecha anclada en COMPRAVENTA; notario por prefijo
  "NOT "). Probado contra un documento real (extrae PPU ZB5004, adquirente
  16.066.831-8, propietario 15.122.931-K, fecha 01-07-2026, notaría PABLO MARTINEZ).
- **Cotejo con adquirente** (decisión #2): si se detecta transferencia y el RUT
  del ticket **no** es el del adquirente (nuevo dueño), se agrega motivo "RUT del
  ticket no es el adquirente" → RECHAZADO. Aplica en `bot.py` y `gui.py`.
- **Consistencia de RUT por presencia en bot.py** (decisión #3): `procesar_ticket`
  pasó de conteo (`>1 RUT` → inconsistente) a **presencia** (RUT del ticket debe
  estar en los docs), alineándose con la GUI. Evita el falso RECHAZADO en batch de
  docs con varios RUT legítimos (transferencia). **Cambio de lógica de estado en
  el path CLI/batch.**
- **`gui.py`**: línea informativa en el reporte cuando se detecta transferencia y
  no hubo RVM ("Transferencia (compraventa) | PPU ... | adq ... | fecha — revisar
  manual"). NO fuerza PENDIENTE por sí sola (decisión #1 quedó descartada); solo
  el cotejo de adquirente afecta el status.
- Detección afinada sobre **un** documento; con más muestras puede requerir ajuste.

### 2026-07-03 — Compraventa: 2do formato (cert notarial) + verificación CVE + OCR mixto

Segunda muestra reveló un **segundo formato** de compraventa distinto al formulario
RC: la **certificación notarial electrónica** de "COMPRAVENTA DE VEHÍCULOS". Ahora
se manejan ambos (`tipo` = `transferencia_rc` | `notarial`).

- **`extract_text(path, force_ocr_images=False)`** (`bot.py`): nuevo flag. El cert
  notarial es mixto — portada con capa de texto (CVE/notaría/partes) + contrato
  escaneado en páginas siguientes (RUT/patente). Antes el fallback OCR solo corría
  si NO había texto, así que el contrato nunca se OCR-eaba. Con `force_ocr_images`
  se anexa el OCR de las imágenes aunque haya texto. Opt-in (es lento): el llamador
  lo activa solo cuando detecta una compraventa candidata.
- **`bot.py`**: `es_transferencia_compraventa()` ampliado (detecta cert notarial por
  NOTARI/REPERTORIO/CVE/FIRMA ELECTR/VENDEDOR/COMPRADOR). `extraer_datos_transferencia()`
  ahora devuelve `tipo`, `cve`, `notaria`, `materia`, `repertorio`. Helpers:
  `_rut_antes()` (RUT antes de "como Comprador/Vendedor" en el contrato en prosa),
  `_patente_ppu()` (PPU 2L+4N o 4L+2N, descarta el dígito verificador -N).
  Comprador = adquirente, vendedor = propietario.
- **`notarial.py`** (nuevo): verifica el CVE. **HTTP puro, sin Chrome ni captcha**
  (a diferencia de los otros módulos): el portal ajs.cl para docs notariales
  (radio "NOTA") consulta `GET https://repositorio.registrosnotariales.cl:8181/rest/api/verificar/{cve}`
  → JSON `{error, url, datosDocumento:{notaria,materia,repertorio,fechaRepertorio}}`.
  SSL estricto OK. Con reintento. `verificar_cve(cve)`.
- **Integración gui/bot**: al detectar compraventa candidata, se re-extrae con
  `force_ocr_images=True`, y si hay CVE se verifica online. Reporte GUI:
  "Compraventa: Notarial | PPU LKPK16 | adq 19.902.071-4 | CVE ✓ (notaría)" o
  "Transferencia RC | ... | revisar manual". Motivos: "CVE notarial no válido"
  (si el CVE es falso) y "RUT del ticket no es el adquirente" (cotejo). `Rose.spec`
  +`notarial`.
- Probado contra los DOS documentos reales (RC y notarial), incl. verificación CVE
  online válida. Docs mixtos con >1 notaría/formato podrían requerir ajuste.

### 2026-07-03 — Prototipo de extracción con LLM (aparte, no enganchado)

- **`extractor_llm.py`** (nuevo, standalone): extrae los datos de compraventa con
  Claude en vez de regex, para evaluar si generaliza mejor a layouts de notaría no
  vistos. Toma el PDF directo (Claude hace OCR + extracción en un paso, sin
  Tesseract) o texto ya extraído; devuelve JSON estructurado validado con Pydantic
  vía `client.messages.parse()`. Modelo default `claude-opus-4-8` (Sonnet 5 como
  opción producción más barata). `anthropic` es import opcional (degrada con
  mensaje claro si falta). El `__main__` imprime LLM vs `extraer_datos_transferencia`
  (regex) lado a lado sobre el mismo PDF.
- **No toca el pipeline.** La verificación (CVE/SII/RVM) y validación (mód-11,
  patente) siguen en el pipeline como guardarraíl; el LLM solo extrae.
- Requisitos para correrlo: `pip install anthropic pydantic` + `ANTHROPIC_API_KEY`.
  No verificado en vivo aún (el entorno de dev no tenía SDK ni credenciales).

### 2026-07-03 — Descartado el LLM; se blindaron los regex

- Se **eliminaron** los prototipos LLM (`extractor_llm.py` API de pago, y un
  `extractor_local.py` con Ollama que no llegó a commitearse). Decisión: para el
  volumen actual no justifica el costo/instalación; los regex ya funcionan y son
  gratis/sin setup. Ante un layout nuevo que falle, se ajustan los anclajes a mano
  (flujo ya probado con cv.pdf y cv3.pdf).
- **`bot.py` — anclajes con sinónimos** en `extraer_datos_transferencia`, para
  tolerar la redacción de distintas notarías sin tocar código:
  - `_patente_ppu`: PPU / P.P.U / **Placa** / **Placa Única** / **Patente**.
  - comprador: `como Comprador/Compradora`, **parte compradora**, `compra y
    adquiere`, **adquiere para**.
  - vendedor: `como Vendedor/Vendedora`, **parte vendedora**, `vende y transfiere`.
- Sin regresión: cv.pdf y cv3.pdf extraen idéntico (ZB5004/LKPK16, adquirente y
  propietario correctos, CVE ok).

### 2026-07-03 — Bugfixes de corrida real (tickets 499406/408/409)

- **`normalizar_patente` — dígito verificador en 2L4N**: patente de ticket
  "ZB5004-3" (2 letras + 4 dígitos + DV) quedaba en "ZB50043" (7 chars) y se
  mandaba así al chequeo de robo. La rama 4L2N descartaba el `-N` pero la 2L4N no.
  Fix: `^([A-Z]{2})-?(\d{3,4})(?:-[\dkK])?$` descarta el DV (en 2L4N no hay
  ambigüedad con patente interna). "PYKS20-4" (interno 4L2N) se sigue conservando.
- **OCR de imágenes MPO**: fotos de celular en formato MPO (multi-imagen) tiraban
  "Unsupported image format/type" y se saltaba la imagen. Fix: `_ocr_pil` convierte
  a RGB antes del OCR (también cubre CMYK/paleta).
- La corrida confirmó en producción: compraventa (transferencia_rc) detectada +
  cotejo de adquirente, SII, robo y Servipag en paralelo, status correcto
  (RECHAZADO por similitud 0%/NO VIGENTE vs APROBADO con similitud 97%).
- **`parse_ticket` — "Error parseando ticket JSON: Extra data"**: el regex era
  greedy (`(\{.+\})\s*\}`) y capturaba desde el `{` del ticket hasta el ÚLTIMO `}`
  del RSC, así que `json.loads` parseaba el ticket y fallaba con "Extra data" por
  todo el resto → caía al fallback por regex en cada ticket. Fix: capturar `(\{.+)`
  y usar `json.JSONDecoder().raw_decode(raw)[0]`, que parsea sólo el objeto del
  ticket e ignora lo que sigue. Ahora devuelve el dict completo sin warning ni
  fallback.

### 2026-07-06 — Credenciales SAP a config.json

- **`sap.py`**: las credenciales de SAP dejaron de estar hardcodeadas. Nuevo
  `_sap_creds()` las lee de `config.json` (`sap_user`/`sap_password`), resuelto
  junto al `.exe` (frozen) o al fuente, igual que la GUI. `sap_llenar()` /
  `sap_llenar_async()` ahora default `None` y toman del config si no se pasan;
  si faltan, devuelven error claro. `config.json` +`sap_user`/`sap_password`.
