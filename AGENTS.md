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

### 2026-07-06 — SAP: llenar solo el RUT + Enter (búsqueda de cuenta)

- **`sap.py`**: el llenado genérico se reemplazó por: tras el login, ingresar
  **solo el RUT** en el campo RUT y presionar Enter para disparar la búsqueda de
  cuenta. Aprendizajes de la corrida real:
  - SAP CRM usa **iframes anidados**; el formulario carga en un frame profundo
    (ej. Frame[9]) que **tarda**. Se hace **polling hasta ~40s** probando el
    `fill_js` en TODOS los `page.frames` hasta encontrar el campo.
  - El campo RUT tiene `zztaxnum` en el id (id dinámico tipo
    `C3_W18_V19_V20_searchcustomer_struct.zztaxnum`); se localiza por rótulo "RUT"
    o por `input[id*="rut"]`.
  - **RUT con guion**: se reconstruye `cuerpo-DV` (ej. `16333784-3`) venga como
    venga el origen (con/sin puntos, con/sin guion).
  - **Enter**: `Frame` no expone `.keyboard`; se usa
    `rut_frame.locator('input[id*="zztaxnum"]').first.press("Enter")` (evento
    nativo) con fallback a `KeyboardEvent` sintético.
  - Ventana de Chrome abierta 5 min para ver la búsqueda.

### 2026-07-06 — SAP: leer "Desconectado por mora"

- **`sap.py`**: tras el Enter (que abre "Identificar cuenta"), se clickea el menú
  izquierdo **"Hoja informativa de cuenta"** y se lee el valor de la caja de texto
  al lado del rótulo **"Desconectado por mora:"** (Sí/No). Se devuelve en
  `result["desconectado_mora"]` y se loguea (`SAP: Desconectado por mora = No`).
  El valor se busca por rótulo → celda/hermano siguiente (input/select/texto).
  Verificado en vivo (RUT 16333784-3 → "No").
- **`gui.py`**: el status de SAP ahora muestra `Desconectado por mora: No/Sí`.
- Nota: el campo NO está en la pantalla de búsqueda ni en "Identificar cuenta";
  vive en "Hoja informativa de cuenta". Ubicado con capturas de pantalla del flujo
  real (dumps del DOM no lo encontraban solos).
- **`gui.py`**: si "Desconectado por mora" = **Sí**, `_do_sap_llenar` fuerza
  **RECHAZADO** vía `_agregar_motivo_rechazo("Cliente desconectado por mora")`, que
  preserva los motivos previos (APROBADO/PENDIENTE → RECHAZADO; un RECHAZADO
  existente suma el motivo dentro de los paréntesis). Como SAP se corre con el
  botón "Llenar SAP" (después del status), el bloqueo se aplica al terminar ese
  paso.

### 2026-07-06 — SAP automático + mora en el reporte

- **SAP ahora corre automático en `_do_buscar`**, en paralelo con Robo/Servipag
  (thread `_run_sap_mora`, bajo `_chrome_lock`/Semaphore). Se **junta ANTES** del
  status: si "Desconectado por mora: Sí" agrega motivo "Cliente desconectado por
  mora" → RECHAZADO. Se agrega la línea `SAP: Desconectado por mora: No/Sí` al
  reporte. Solo corre si el RUT del ticket es válido (`validar_rut`).
- **`sap.py` — `mantener_abierto: bool = True`**: nuevo parámetro. En automático
  se llama con `mantener_abierto=False` (cierra apenas lee la mora, ~37s, NO
  bloquea el `_chrome_lock` 5 min). El botón manual "Llenar SAP" sigue con el
  default `True` (deja Chrome abierto para que el operador trabaje la cuenta).
- Costo: ~40-60s extra por ticket con RUT válido (el status espera a SAP).
  Verificado en vivo (RUT 16333784-3 → "No", 37s).

### 2026-07-06 — SAP: cerrar sesión ("Salir del sistema")

- **Matar Chrome NO libera la sesión server-side de SAP.** Con SAP automático por
  ticket (login cada vez), las sesiones del usuario se acumulan hasta topar el
  límite → SAP deja de cargar la CRM (login devuelve 1 solo frame, URL con
  `SID:ANON`/`sap-system-login=X`). Por eso `sap_llenar(mantener_abierto=False)`
  ahora clickea **"Salir del sistema"** antes de matar Chrome.
- **Pantalla de sesión existente**: si tras el login SAP muestra la pantalla de
  "sesión ya conectada" (`SID:ANON` / `sap-system-login=X`, 1 solo frame), tiene un
  botón **"cont."** para continuar. `sap_llenar_async` ahora lo clickea tras el
  login → entra reusando/continuando la sesión (antes fallaba: CRM no cargaba).
- Con ambos (click "cont." al entrar + "Salir del sistema" al salir) el manejo de
  sesiones quedó sólido. Verificado en vivo: click cont. → 11 frames → mora="No" →
  sesión cerrada, 43s.

### 2026-07-07 — SAP: "Datos del cliente" — verificar nombre + email

- **`sap.py`**: tras leer "Desconectado por mora", ahora click en **"Datos de cliente"**
  (menú izquierdo de SAP CRM — OJO: el menú dice "Datos de cliente", NO "del").
  Extrae **Nombre** + **Apellidos** de los labels, los combina y devuelve
  `nombre_sap`. Busca **email** en labels, inputs y patrón `@` en el body →
  `email_sap`. Dump de labels + inputs para debug.
- **`gui.py`**: dos flujos actualizados (automático `_do_buscar` y manual
  `_do_sap_llenar`):
  - Pasa `nombre` + `email` del ticket a `sap_llenar(datos=...)`.
  - Compara nombre de ticket vs SAP con **normalización de tildes/acentos**
    (`unicodedata.normalize('NFD')` → strip ASCII): ANDRÉS = ANDRES.
  - Compara email case-insensitive.
  - Si no coinciden → motivo `"Nombre no coincide con SAP"` / `"Email no coincide
    con SAP"` → RECHAZADO.
- **Bug selector**: el menú dice "Datos de cliente" (no "del"). Selector corregido
  a match exacto (`<=30 chars`) para evitar que un div padre con todo el menú
  coincida con `includes()`.
- Verificado con ticket 454552: nombre SAP "FELIPE ANDRES AGUILAR BARBOSA" coincide
  con ticket (con normalización de tildes). Email SAP "FELIPEAGUILAR.B@GMAIL.COM"
  coincide con ticket.

### 2026-07-07 — SAP: limpieza del andamiaje de debug de "Datos de cliente"

El bloque de "Datos de cliente" se escribió explorando el DOM de SAP CRM a ciegas.
Una vez que los selectores de `nombre_js`/`email_js` quedaron verificados, el
andamiaje sobraba. Removido (58 líneas, sin cambio de comportamiento):

- **Screenshot `sap_datos_cliente.png`**: escribía a `debug_dir`, que es un
  `mkdtemp` que el `finally` borra con `shutil.rmtree` → nunca se podía mirar.
- **Dump de inputs** (hasta 40 por frame) y **dump de labels** (hasta 80 por
  frame), ambos a nivel INFO: servían para descubrir qué campos tenía la pantalla,
  pero en producción inundan el panel de log de la GUI con datos del cliente.

Removido después, en el mismo barrido:

- **Screenshot `sap_pagina.png`** de la fase de login. Mismo defecto: escribía al
  `mkdtemp` que el `finally` borra. `sap.py` ya no toma screenshots.
  Nota: `debug_dir` sigue existiendo, pero ya solo cumple de `--user-data-dir`
  del Chrome que se lanza — el nombre quedó engañoso.

Se conservó a propósito:

- El `wait_for_timeout(10000)` tras el click en "Datos de cliente". Es funcional
  (espera la carga del frame), no debug. Los demás saltos de frame del archivo
  usan 8000; bajarlo a 8000 alinearía la convención pero no es verificable sin
  correr contra SAP en vivo, y el flujo de 10s ya está probado.
- Los **dumps de inputs** de la fase de login (~línea 106) y del campo RUT
  (~línea 325): a diferencia de los screenshots, sí llegan al log y son el
  diagnóstico cuando el login o la búsqueda por RUT falla.

### 2026-07-07 — Entorno roto, OCR que no degradaba, y SII: reintento que jugaba en contra

Sesión de compilar + ejecutar + monitorear. Salieron tres cosas, dos de ellas
bugs reales que solo se ven corriendo la app.

**Entorno (no es código, pero costó encontrarlo).** Faltaban `PyPDF2`,
`pytesseract` y `playwright` del `requirements.txt`, y `pandas 2.1.3` convivía
con `numpy 2.2.6` — ABI incompatibles. `pytesseract` hace `import pandas` dentro
de un `try/except ModuleNotFoundError`, pero el choque de ABI lanza `ValueError`,
que se escapaba. Se subió pandas a 2.3.3. También faltaba el binario de
Tesseract: instalado 5.4.0.20240606 vía `winget install UB-Mannheim.TesseractOCR`,
que cae justo en `C:\Program Files\Tesseract-OCR\tesseract.exe`, la ruta fija de
`bot.py`. `PyInstaller` tampoco estaba (no figura en `requirements.txt`).

**`bot.py` — el `except ImportError` del bloque de OCR era demasiado angosto.**
Con el `ValueError` de arriba, `import bot` reventaba y con él **toda la app**,
en vez de degradar a "sin OCR" que es lo que el bloque quiere hacer. Tres
cambios:
- `except ImportError` → `except Exception`, guardando el motivo en `_OCR_ERROR`.
- **La descarga de `spa.traineddata` se separó del import**, con su propio `try`
  y su `_TESSDATA_ERROR`. Estaban fusionadas: si fallaba la red, el `except`
  dejaba `pytesseract = None` y perdías el OCR entero aunque el stack estuviera
  sano. Ahora Tesseract cae a su tessdata del sistema.
- El motivo se reporta en dos lados: `log.warning` al arrancar **y** dentro de
  `ocr_image()`. El segundo importa porque `gui.py:61` hace `log.handlers.clear()`
  antes de instalar el suyo → el aviso de import NO llega al panel de la GUI.

**`RVM: —` en certificados escaneados = era el Tesseract faltante.** El fallback
a OCR funcionaba bien (detectaba los PDFs sin capa de texto y los mandaba a
OCR); lo que fallaba era el binario. PDF escaneado → 0 texto → sin keywords
`R.V.M.`/`INSCRIPCION` → `RVM: —`. Se confirmó por contraste: los PDFs *con*
capa de texto sí verificaban (dos tickets dieron `Certificado RVM no válido`).

**`sii.py` — el reintento perdía el lugar en la cola.** `consultar_sii_async`
hacía `mkdtemp` propio en cada llamada, o sea perfil de Chrome nuevo por intento.
Queue-it guarda la posición en la cola en una cookie del navegador → el reintento
**volvía al final de la fila**, justo lo contrario de lo que se busca. Ahora
acepta `perfil` y el wrapper síncrono crea uno solo para todos los intentos y lo
borra en un `finally`. Sin `perfil` el comportamiento es el de antes (el módulo
sigue usable suelto).

**`sii.py` — dos fallas distintas compartían mensaje.** `_esperar_fuera_de_cola`
devolvía `bool`, y el `False` tapaba dos casos muy distintos bajo el texto único
"SII en cola - tiempo excedido". Pasó a `Optional[str]`:
- `"SII sigue en sala de espera tras 120s"` → saturación real, reintentar sirve.
- `"SII fuera de cola pero el SPA no renderizó (input.rut-form) en 30s"` → si se
  vuelve permanente, el SII cambió el HTML y hay que actualizar el selector.
Ambos siguen clasificando como reintentables en `_fallo_reintentable`. De paso se
sacó el `screenshot(debug_dir / "sii_cola.png")`: mismo caso que en `sap.py`, el
`finally` borra `debug_dir`. Quedan `sii_no_rut.png` y `sii_resultado.png`.

**Despliegue — `dist/config.json` se desincroniza en silencio.** `Rose.spec` no
empaqueta `config.json` (a propósito: permite cambiar credenciales sin
recompilar), así que hay que copiarlo a mano a `dist/` tras cada cambio. Estaba
viejo, sin `sap_user`/`sap_password` → el `.exe` fallaba todo SAP con "Faltan
credenciales SAP". **Acordarse de `cp config.json dist/` al compilar.**

### 2026-07-07 — Adjuntos que el pipeline descartaba en silencio (Autofact)

Probando el ticket 454515 apareció que `extract_file_urls` clasifica como `"otro"`
todo lo que no termine en `.pdf`/`.jpg`/`.jpeg`/`.png`/`.gif`, y el pipeline solo
procesa `"pdf"` e `"img"` → el resto se descartaba **sin ningún log**. El ticket
parecía "sin adjuntos" (la GUI incluso dice "Ticket sin PDFs adjuntos") cuando en
realidad tenía uno que nadie miró.

- **`bot.py`**: `extract_file_urls` ahora emite un `log.warning` con la cuenta y
  las URLs de los adjuntos ignorados. Verificado que no mete ruido: en un ticket
  con 5 adjuntos todos pdf/img no dice nada.

**El hallazgo importante no es el log, es qué había del otro lado.** El adjunto de
454515 ("Documentos Adicionales") era:

```
https://docs.transferencias.autofact.cl/weAAhtGSMAIMn-fLKFCzR
```

`Content-Type: text/html`, 364 bytes — **no es un archivo, es el visor SPA de
Autofact** (JS que carga el documento aparte). La URL no trae extensión, por eso
caía en `"otro"`.

Y el subdominio es **`docs.transferencias`**: son documentos de compraventa. O sea
que el punto ciego cae justo sobre el flujo de transferencia, que es donde más
lógica hay invertida (`es_transferencia_compraventa`, `extraer_datos_transferencia`,
cotejo del adquirente, CVE notarial en `notarial.py`). Si Autofact es un canal
habitual, hay una familia entera de tickets donde no se está mirando el documento
que más importa.

**Pendiente**: medir qué tan común es (correr el extractor sobre varios desks de
transferencia y contar cuántos caen en Autofact) antes de decidir si vale
resolver el visor —bajar el PDF real desde la SPA— o dejarlo a revisión manual.

**Nota de la misma corrida**: el SII tardó **79 s** en la cola Queue-it y salió al
primer intento. Con un presupuesto de 120 s, eso explica el error intermitente
"tiempo excedido" en días cargados — y por qué el fix del perfil compartido entre
reintentos importa: antes cada reintento hacía la fila entera de nuevo.

### 2026-07-07 — RVM: "no pude leer la página" se reportaba como "certificado no válido"

**Falso RECHAZADO.** El peor bug de la sesión, encontrado probando el ticket 454523.

`verificar_rvm_async` tenía tres ramas tras clickear Consultar:
1. body contiene "El certificado es v..." → `valido=True`.
2. body contiene "error" + "folio"/"código" → `valido=False`. **Única rama en que
   el Registro Civil realmente se pronuncia.**
3. else → esperaba 5 s más y, si seguía sin aparecer, `valido=False` +
   `success=True` + `mensaje="No se pudo determinar"`.

La rama 3 convertía "no pude leer la página" en **un veredicto en firme de
certificado inválido**. Y `bot.py` lo tomaba al pie de la letra:
`if valido is True: ... else: motivos.append("Certificado RVM no válido")` — ese
`else` capturaba también el `None`/indeterminado → **RECHAZADO**.

Medido en vivo: la página del Registro Civil devolvió **204 chars** en los dos
intentos (el SII, de comparación, rinde 3.022). O sea prácticamente vacía: el RC
nunca dijo que el certificado fuera inválido.

Cambios:
- **`rvm.py`**: rama 3 → `valido=None`, `success=False`, con `log.warning` que
  incluye el tamaño del body (así se ve al toque cuando la página no rindió).
  Con `success=False` el reintento sigue funcionando vía `_fallo_reintentable`.
- **`bot.py`**: solo un `valido is False` **explícito** agrega motivo. `None` va a
  un warning "revisar a mano".
- **`gui.py`**: `_mostrar_resultado_rvm` mostraba `Error` pelado ante
  `success=False`; ahora muestra el mensaje real. El flujo automático
  (`gui.py:1276`) ya chequeaba `valido is False` explícitamente y estaba bien —
  lo que lo rompía era que `rvm.py` le mandaba `False`.

Verificado en el mismo ticket 454523:
```
antes:    RECHAZADO (Documento vencido (258 días), Certificado RVM no válido)
después:  RECHAZADO (Documento vencido (258 días))
```

**Pendiente aparte, y no menor**: no se sabe *por qué* el portal del RC devuelve
204 chars — lentitud, cambio del sitio o bloqueo. Este fix hace que el bot deje de
mentir sobre eso, pero no lo arregla. Mientras siga así, **ningún** certificado RVM
se puede verificar (antes todos salían "no válido" → rechazos falsos en masa; ahora
todos salen "sin veredicto" → revisión manual). Vale investigarlo aparte.

### 2026-07-07 — RVM: el parseo del código se rompía sobre texto OCR

Encontrado probando el ticket 454517, que logueaba `codigo=Verificaci` — un pedazo
de la palabra "Verificación", no un código.

Los dos PDFs del ticket son el mismo certificado con layouts distintos:

```
escaneado (OCR):   FOLIO:600023308517
                   ... Código Verificación:
                   - 88150c1f58f4        <- código en la línea siguiente, con "- "

capa de texto:     FOLIO:
                   88150c1f58f4Código Verificación:600023308517   <- "mangled", ya soportado
```

Cadena del fallo, en `extraer_datos_rvm`:
1. `CODIGO_VERIF_RE` usaba `[:\s]*` entre el rótulo y el código. Sobre el layout OCR
   frenaba en el guion → no matcheaba (`search()` devolvía `None`).
2. Al no tener código, caía al fallback de prioridad 5, cuya alternativa
   `[Cc]ódigo[:\s]*` matcheaba **"Código"**, se comía el espacio y capturaba los
   primeros 10 alfanuméricos de la palabra siguiente: **"Verificaci"** (corta en la
   "ó", que no está en `[A-Za-z0-9]`).

Arreglos:
- `CODIGO_VERIF_RE` acepta `[-–]?\s*` antes del código, para el salto de línea con
  guion del OCR.
- La prioridad 5 lleva un lookahead `(?![Vv]erificaci)` en la rama `[Cc]ódigo`, para
  que no se coma el rótulo "Código Verificación" — ese caso es de `CODIGO_VERIF_RE`.

Verificado sobre 6 formatos (los 2 del docstring, los de 454517 y 454523 en sus dos
variantes, y salto de línea sin guion) y contra los 3 PDFs reales de ambos tickets:
todos extraen folio y código correctos. Sin regresión en los formatos que ya andaban.

**Nota**: este bug estaba tapado por el de los 204 chars del portal del RC — el
resultado era "sin veredicto" igual. Son independientes: aun con el portal sano,
454517 habría fallado por el código mal extraído.

### 2026-07-07 — Autofact: recuperar los documentos que el pipeline no veía

Medido sobre 20 tickets `454xxx` al azar: **6 de 20 (30%) no tenían un solo
documento procesable**. Su único adjunto ("Documentos Adicionales") es un link al
visor SPA de Autofact — 364 bytes de HTML que cargan React, no un archivo. Esos
tickets pasaban por todo el pipeline sin nada que analizar y quedaban PENDIENTE
por construcción.

**Cómo se encontraron los PDFs**: cargando el visor con Chrome headless y mirando
el tráfico. La SPA consulta un API sin autenticación:

```
GET https://xoyx149gh7.execute-api.us-east-1.amazonaws.com/latest/v2/transference/
    gateway/retail-api-transference/transference-wizard/v1/transference/
    document/tag/{TOKEN}/token/all
```

El `{TOKEN}` es el último segmento del path del visor. Devuelve JSON con `path`
(URL directa al PDF), fecha y tipo. **Anda con `requests` puro** — probado en los
6 tickets, 5 documentos en cada uno: CONTRATO, CAV, CÉDULA DEL COMPRADOR,
SOLICITUD TRANSFERENCIA y COMPROBANTE TRANSFERENCIA DE VEHÍCULO.

- **`autofact.py`** (nuevo): HTTP puro, sin Chrome, mismo patrón que `notarial.py`.
  Ante cualquier fallo devuelve lista vacía — nunca afirma que el ticket no tiene
  documentos.
- **`bot.py`**: `resolver_adjuntos(files)` expande los links de Autofact y avisa
  de lo que quede sin resolver. Se dejó FUERA de `extract_file_urls`, que es una
  función pura de regex, para no meterle una llamada de red. El aviso de adjuntos
  ignorados de `c5f6d15` se movió acá: ahora reporta solo lo que quedó sin
  resolver *después* de expandir.
- **`gui.py`** / **`bot.py`**: ambos puntos de entrada llaman
  `resolver_adjuntos(extract_file_urls(rsc))` — los dos flujos quedan parejos.
- **`Rose.spec`**: `autofact` en `hiddenimports`.

**Falso positivo que esto destapó, y hubo que arreglar antes de poder usarlo.**
El contrato de Autofact es un FORMULARIO (rótulo antes del valor):

```
Vendedor / RUT: 10.037.200-2  ...  Firma del Comprador / RUT: 16.191.948-9
```

mientras que `extraer_datos_transferencia` estaba escrito para contratos en PROSA
(RUT antes del rótulo: "... CI 16.191.948-9, como Comprador ..."). Leído con los
anclajes de prosa, `rut_adquirente` salía con el RUT del **vendedor** → motivo
"RUT del ticket no es el adquirente" → **RECHAZADO falso**, cuando el solicitante
sí era el comprador.

Arreglo: se prueban las dos lecturas (prosa con `_rut_antes`, formulario con
`_primer_rut_tras`) y se acepta la primera que produzca **dos partes DISTINTAS**
— que es lo que una compraventa tiene por definición. Si ninguna lo logra, ambos
quedan en `None` y el cotejo no corre: preferible no cotejar a rechazar sobre una
lectura que ya sabemos incoherente.

Verificado en 454310:
```
antes (sin Autofact):    PENDIENTE  (no había documentos)
con extractor roto:      RECHAZADO (RUT del ticket no es el adquirente, Documento vencido)
ahora:                   RECHAZADO (Documento vencido (254 días))   ← adq=16.191.948-9 = RUT del ticket
```

**Pendiente detectado, NO tocado**: `_rut_antes` devuelve el RUT más a la
izquierda dentro de su ventana de 160 chars, no el más cercano al rótulo. En un
contrato en prosa donde ambas partes caen juntas, da el RUT equivocado. Es
preexistente. No se arregló porque no hay ningún contrato notarial en prosa en el
repo para validar el cambio, y estos anclajes se afinaron contra documentos
reales — tocarlos a ciegas es la receta de regresión que documenta este archivo.
