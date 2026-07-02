# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es

**Rose** automatiza la verificación de documentos para solicitudes de TAG (tag de peaje de autopistas chilenas) enviadas en `tag-admin.integrocorp.cl` (backend Laravel Sanctum + frontend Next.js). Dado un número de *desk/ticket*, descarga los documentos del solicitante, extrae los datos de identidad, decide APROBADO/RECHAZADO/PENDIENTE, y hace cruces contra portales gubernamentales/de pago chilenos.

Todo el texto de UI, los logs y los strings de estado están en español — mantenlo así al editar.

## Comandos

```bash
pip install -r requirements.txt
playwright install chromium        # requerido por los módulos de verificación vía CDP

python gui.py                      # GUI tkinter (interfaz principal)
python bot.py                      # CLI, ticket único desde config.json
python bot.py --desk 498981        # CLI, ticket específico
python bot.py -b tickets.txt       # batch: un desk id por línea, corre Servipag por ticket

pyinstaller Rose.spec              # genera dist/Rose.exe (standalone, sin Python)
```

No hay suite de tests, linter ni CI. La verificación es manual, corriendo contra tickets reales.

`config.json` guarda `user`/`password`/`desk` (las credenciales viven en el repo — es una herramienta interna). El `.exe` resuelve `config.json` relativo a `BASE_DIR` (junto al ejecutable cuando está congelado, junto al fuente en otro caso).

## Arquitectura

Dos puntos de entrada comparten un núcleo (`bot.py`) más un conjunto de módulos de verificación contra portales externos.

### Pipeline central — `bot.py`
`procesar_ticket()` es la unidad reutilizable de extremo a extremo usada por CLI y GUI:
1. `sanctum_login()` — cookie CSRF → POST /login → verifica con /api/user (puro `requests`).
2. `fetch_desk_rsc()` — hace GET a la página Next.js y reconstruye el payload RSC desde los chunks `self.__next_f.push([...])`.
3. `parse_ticket()` / `extract_file_urls()` — extraen por regex el JSON del ticket y las URLs de archivos en S3 desde el texto RSC (manejando `&` etc.). Los archivos de S3 se descargan sin auth.
4. Extracción de texto: `extract_text()` (PyPDF2) con fallback `_ocr_pdf_images()` para PDFs escaneados; `ocr_image()` para JPG/PNG. El OCR usa Tesseract con `spa.traineddata` en español, autodescargado a `~/.tessdata/` en la primera ejecución. La ruta del binario Tesseract está fija a `C:\Program Files\Tesseract-OCR\tesseract.exe`.
5. Extractores por regex: `find_ruts`, `find_patentes`, `find_nombres`, `find_razon_social`, `find_telefono`, `find_direccion`, `find_fecha_emision`. `validar_rut()` hace la validación de dígito verificador módulo 11; `_normalize()` canoniza el formato del RUT.
6. `check_vigente_optimo()` lee los sellos de verificación (`% similitud`, VIGENTE/NO VIGENTE/RECHAZADO/OPTIMO) del texto del documento.
7. Decisión de estado (el orden importa — acumula `motivos`): inconsistencia de RUT/razón social → texto RECHAZADO → NO VIGENTE → similitud < 90% → documento con más de 30 días → fallos de SII/RVM. **APROBADO solo cuando similitud ≥ 90% y sin motivos**; de lo contrario PENDIENTE. Ver el docstring/AGENTS.md para la precedencia exacta, que ha sido afinada repetidamente.

Invariantes de extracción clave (cada una corrigió un falso positivo real; no las regreses):
- Los datos del ticket tienen prioridad sobre los del documento para los campos mostrados; los PDFs nunca sobrescriben el RUT/nombre del ticket.
- Los RUT extraídos por OCR se loguean pero se excluyen de los chequeos de consistencia (el OCR del reverso del carnet producía RUTs espurios).
- similitud ≥ 90% es autoritativa y sobrescribe un "NO VIGENTE" perdido que aparezca en contexto no relacionado del documento.

### Módulos de verificación externa — el patrón CDP
`servipag.py` (deudas TAG), `sii.py` (estado tributario/RUT), `rvm.py` (certificado vehicular Registro Civil), `robos.py` (encargo por robo) y `sap.py` (llenado de formulario SAP CRM) siguen **la misma estructura** — copia uno existente al agregar un portal:

- Un `async def ..._async(...)` y un envoltorio síncrono delgado (`asyncio.run(...)`).
- **Lanzan Chrome real vía `subprocess`** con `--remote-debugging-port` + un `--user-data-dir` temporal, y luego `playwright.chromium.connect_over_cdp(...)`. Esto es deliberado: lanzar Chrome directamente (en vez del navegador que trae Playwright) evade la detección de bots de Cloudflare Turnstile. No los "simplifiques" a `playwright.chromium.launch()`.
- `_find_free_port()` y el descubrimiento `_CHROME_CANDIDATES`/`CHROME_PATH` están duplicados en cada módulo.
- `robos.py` además evade reCAPTCHA atrapando `window.__bypassCaptchaValidation` vía `Object.defineProperty` antes de que el script de la página lo lea.
- `sii.py`/`rvm.py` aceptan `keep_open` para dejar Chrome abierto para depuración.

`bot.py` importa estos módulos de forma perezosa (dentro de funciones) para que la CLI funcione aunque Playwright/Chrome no estén.

### GUI — `gui.py`
`App(tk.Tk)` en tkinter. Corre todo el trabajo bloqueante (login, procesamiento de tickets, cada llamada a Chrome/CDP, carga de imágenes) en `threading.Thread`s daemon, y luego devuelve las actualizaciones de UI con `self.after(...)`. `TextHandler` canaliza la salida de `logging` al panel de log en pantalla.

Dos locks controlan la concurrencia:
- `_buscar_lock` — serializa búsqueda/batch para que dos corridas de ticket no se solapen.
- `_chrome_lock` — serializa **todas** las operaciones que lanzan Chrome (Servipag, SII, RVM, robo, SAP). Todo método `_do_*` que toque un módulo CDP debe adquirirlo; lanzar dos Chrome sobre el mismo setup de debug a la vez genera conflicto.

La GUI muestra los campos extraídos con botones de copiar por campo (el RUT se copia sin puntos ni guion), un STATUS con código de color, un visor de imágenes del documento con zoom por rueda del mouse ("lupa", usa `anchor=tk.NW` para que las coordenadas del mouse mapeen bien), y botones que disparan cada módulo de verificación. En APROBADO corre Servipag automáticamente; el chequeo de robo corre automáticamente durante `_do_buscar`.

## Bitácora del proyecto — `AGENTS.md`

`AGENTS.md` es un log de sesiones corrido y fechado (secciones más nuevas al final) que documenta el *porqué* de los comportamientos — especialmente las correcciones de falsos positivos y el afinamiento de la lógica de estado. **Léelo antes de cambiar los regex de extracción o las reglas de estado**, y agrega una entrada fechada cuando hagas cambios notables. El término del usuario **"conmitea"** significa: commit + push + actualizar `AGENTS.md`, en un solo paso.
