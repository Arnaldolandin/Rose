# integro-rut-bot — tag-admin.integrocorp.cl

Bot que extrae RUT, patente y nombre completo desde PDFs de un desk en tag-admin.integrocorp.cl (Laravel Sanctum + Next.js).

## Uso
```bash
pip install -r requirements.txt
python bot.py                  # CLI, usa config.json (desk 498978)
python bot.py --desk 498981    # otro ticket
python gui.py                  # GUI con input de ticket + foto + log
```

## Dependencias
- `requests`, `beautifulsoup4`, `PyPDF2`, `Pillow`

## Arquitectura
- `bot.py` — login Sanctum, fetch RSC desde Next.js, parse ticket + URLs S3, descarga PDFs, extrae RUT/patente/nombre con regex
- `gui.py` — tkinter: input ticket, resultados (Nombre/RUT/Patente/Email/Solicitud), foto con navegacion, log toggle, copiar por campo

## Sesiones

### 2026-06-29 — GUI completa con foto, navegacion, validacion RUT, copiar, log toggle, pegar
- `gui.py`: interfaz grafica con campo ticket + Buscar, panel Resultado con boton Copiar por campo
- Validacion digito verificador RUT chileno (`✓`/`✗`)
- Foto desde S3 con navegacion Anterior/Siguiente si hay varias
- Checkbox para ocultar/mostrar Log, oculto por defecto
- Click derecho > Pegar en campo ticket
- Push a `github.com/Arnaldolandin/integro-rut-bot`
