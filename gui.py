import logging
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, scrolledtext
import io

import requests
from PIL import Image, ImageTk

from bot import (
    sanctum_login,
    fetch_desk_rsc,
    parse_ticket,
    extract_file_urls,
    download_pdf,
    extract_text,
    find_nombres,
    find_ruts,
    find_patentes,
    validar_rut,
    log,
)

OUT_DIR = Path("./pdfs")
MAX_IMG_W, MAX_IMG_H = 500, 500

logging.getLogger().setLevel(logging.DEBUG)
log.handlers.clear()


class TextHandler(logging.Handler):
    def __init__(self, widget: scrolledtext.ScrolledText):
        super().__init__()
        self.widget = widget

    def emit(self, record):
        msg = self.format(record)
        self.widget.after(0, self._append, msg + "\n")

    def _append(self, msg):
        self.widget.configure(state="normal")
        self.widget.insert(tk.END, msg)
        self.widget.see(tk.END)
        self.widget.configure(state="disabled")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Integro RUT Bot")
        self.geometry("950x650")
        self.resizable(True, True)

        self.session: requests.Session | None = None
        self._busy = False
        self._img_urls: list[str] = []
        self._img_idx = -1

        self._build_ui()
        self._start_login()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        main = ttk.Frame(self, padding=12)
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(2, weight=1)

        # -- Top: ticket input (row 0, colspan 2) --
        top = ttk.Frame(main)
        top.grid(row=0, column=0, columnspan=2, sticky=tk.EW, pady=(0, 8))

        ttk.Label(top, text="Ticket:").pack(side=tk.LEFT)
        self.ticket_var = tk.StringVar()
        self.ticket_entry = ttk.Entry(
            top, textvariable=self.ticket_var, width=20, font=("Consolas", 12)
        )
        self.ticket_entry.pack(side=tk.LEFT, padx=6)
        self.ticket_entry.bind("<Return>", lambda e: self._buscar())
        self.ticket_entry.focus()

        self.buscar_btn = ttk.Button(
            top, text="Buscar", command=self._buscar
        )
        self.buscar_btn.pack(side=tk.LEFT)

        # -- Left: results (row 1, col 0) --
        self.result_vars: dict[str, tk.StringVar] = {}
        results_frame = ttk.LabelFrame(main, text="Resultado", padding=8)
        results_frame.grid(row=1, column=0, sticky=tk.NSEW, padx=(0, 6), pady=(0, 8))

        fields = [
            ("Nombre:", "nombre"),
            ("RUT:", "rut"),
            ("Patente:", "patente"),
            ("Email:", "email"),
            ("Solicitud:", "solicitud"),
        ]
        for label, key in fields:
            row = ttk.Frame(results_frame)
            row.pack(fill=tk.X, pady=1)
            ttk.Label(row, text=label, width=10, anchor=tk.E).pack(side=tk.LEFT)
            var = tk.StringVar(value="—")
            self.result_vars[key] = var
            val_label = ttk.Label(
                row,
                textvariable=var,
                font=("Consolas", 11, "bold"),
                foreground="#2b2b2b",
            )
            val_label.pack(side=tk.LEFT, padx=(6, 2))

            if key == "rut":
                self._rut_val_label = ttk.Label(row, text="", font=("Consolas", 10))
                self._rut_val_label.pack(side=tk.LEFT, padx=(0, 4))

            btn = ttk.Button(row, text="Copiar", width=5, command=lambda k=key: self._copiar(k))
            btn.pack(side=tk.LEFT, padx=2)

        # -- Right: image preview (row 1, col 1) --
        img_frame = ttk.LabelFrame(main, text="Foto", padding=8)
        img_frame.grid(row=1, column=1, sticky=tk.NSEW, pady=(0, 8))
        img_frame.columnconfigure(0, weight=1)

        self.img_label = ttk.Label(img_frame, text="(sin imagen)")
        self.img_label.grid(row=0, column=0, columnspan=2, pady=(0, 6))

        nav = ttk.Frame(img_frame)
        nav.grid(row=1, column=0, columnspan=2)
        self.btn_anterior = ttk.Button(nav, text="< Anterior", command=self._img_anterior, state="disabled")
        self.btn_anterior.pack(side=tk.LEFT, padx=4)
        self.btn_siguiente = ttk.Button(nav, text="Siguiente >", command=self._img_siguiente, state="disabled")
        self.btn_siguiente.pack(side=tk.LEFT, padx=4)

        self._main = main
        log_header.grid(row=2, column=0, columnspan=2, sticky=tk.W)
        self._log_visible = tk.BooleanVar(value=True)
        ttk.Checkbutton(log_header, text="Log", variable=self._log_visible,
                        command=self._toggle_log).pack(side=tk.LEFT)
        self.log_area = scrolledtext.ScrolledText(
            main,
            height=12,
            font=("Consolas", 9),
            state="disabled",
            wrap=tk.WORD,
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white",
        )
        self.log_area.grid(row=3, column=0, columnspan=2, sticky=tk.NSEW)
        main.rowconfigure(3, weight=1)

        # Log handler
        handler = TextHandler(self.log_area)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
        )
        logging.getLogger().addHandler(handler)

    # ------------------------------------------------------------------
    # Login (background)
    # ------------------------------------------------------------------

    def _set_busy(self, busy: bool):
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.buscar_btn.configure(state=state)
        self.ticket_entry.configure(state=state)

    def _start_login(self):
        self._set_busy(True)
        log.info("Iniciando sesion...")
        threading.Thread(target=self._do_login, daemon=True).start()

    def _do_login(self):
        try:
            cfg = {"user": None, "password": None}
            cfg_path = Path("./config.json")
            if cfg_path.exists():
                import json
                cfg |= json.loads(cfg_path.read_text(encoding="utf-8"))
            s = requests.Session()
            s.headers["User-Agent"] = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
            if sanctum_login(s, cfg.get("user"), cfg.get("password")):
                self.session = s
                self.after(0, self._on_login_ok)
            else:
                self.after(0, self._on_login_fail)
        except Exception as e:
            log.error("Error login: %s", e)
            self.after(0, self._on_login_fail)

    def _on_login_ok(self):
        log.info("Sesion lista. Ingrese ticket y presione Enter.")
        self._set_busy(False)

    def _on_login_fail(self):
        log.error("Login fallido — revise config.json")
        self._set_busy(False)

    # ------------------------------------------------------------------
    # Buscar ticket
    # ------------------------------------------------------------------

    def _buscar(self):
        if self._busy or not self.session:
            return
        raw = self.ticket_var.get().strip()
        if not raw:
            return
        try:
            desk = int(raw)
        except ValueError:
            log.warning("Ticket debe ser numerico: %s", raw)
            return
        self._limpiar_resultados()
        self._limpiar_imagen()
        self._set_busy(True)
        threading.Thread(target=self._do_buscar, args=(desk,), daemon=True).start()

    def _copiar(self, key: str):
        val = self.result_vars[key].get()
        if val and val != "—":
            self.clipboard_clear()
            self.clipboard_append(val)
            log.info("Copiado '%s' al portapapeles", val)

    def _actualizar_rut_val(self, rut: str):
        if not rut or rut == "—":
            self._rut_val_label.configure(text="")
            return
        valido = validar_rut(rut)
        texto = "✓" if valido else "✗"
        color = "green" if valido else "red"
        self._rut_val_label.configure(text=texto, foreground=color)

    def _toggle_log(self):
        if self._log_visible.get():
            self.log_area.grid()
            self._main.rowconfigure(3, weight=1)
        else:
            self.log_area.grid_remove()
            self._main.rowconfigure(3, weight=0)

    def _limpiar_resultados(self):
        for var in self.result_vars.values():
            var.set("—")
        self._rut_val_label.configure(text="")

    def _limpiar_imagen(self):
        self._img_urls = []
        self._img_idx = -1
        self.btn_anterior.configure(state="disabled")
        self.btn_siguiente.configure(state="disabled")
        self.img_label.configure(image="", text="(cargando...)")

    # ------------------------------------------------------------------
    # Mostrar imagen por indice
    # ------------------------------------------------------------------

    def _mostrar_imagen_idx(self, idx: int):
        if idx < 0 or idx >= len(self._img_urls):
            return
        self._img_idx = idx
        url = self._img_urls[idx]
        self.btn_anterior.configure(state="normal" if idx > 0 else "disabled")
        self.btn_siguiente.configure(state="normal" if idx < len(self._img_urls) - 1 else "disabled")
        self.img_label.configure(text=f"(cargando {idx + 1}/{len(self._img_urls)})...")
        threading.Thread(target=self._do_cargar_imagen, args=(url,), daemon=True).start()

    def _do_cargar_imagen(self, url: str):
        try:
            r = self.session.get(url, timeout=30)
            r.raise_for_status()
            img_data = io.BytesIO(r.content)
            pil_img = Image.open(img_data)

            w, h = pil_img.size
            scale = min(MAX_IMG_W / w, MAX_IMG_H / h, 1.0)
            if scale < 1.0:
                pil_img = pil_img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

            self._tk_img = ImageTk.PhotoImage(pil_img)
            self.after(0, self._set_imagen, self._tk_img)
        except Exception as e:
            log.warning("Error al cargar imagen: %s", e)
            self.after(0, self._set_imagen_error)

    def _set_imagen(self, photo):
        caption = f"{self._img_idx + 1}/{len(self._img_urls)}" if self._img_urls else ""
        self.img_label.configure(image=photo, text=caption, compound=tk.BOTTOM)

    def _set_img_urls(self, urls: list[str]):
        self._img_urls = urls
        self._mostrar_imagen_idx(0)

    def _set_imagen_error(self):
        self.img_label.configure(image="", text="(sin imagen)")

    def _img_anterior(self):
        self._mostrar_imagen_idx(self._img_idx - 1)

    def _img_siguiente(self):
        self._mostrar_imagen_idx(self._img_idx + 1)

    def _do_buscar(self, desk: int):
        try:
            log.info("Consultando ticket %s...", desk)
            rsc = fetch_desk_rsc(self.session, desk)
            if not rsc:
                self.after(0, lambda: log.error("No se pudo obtener datos del ticket %s", desk))
                self.after(0, self._set_busy, False)
                return

            ticket = parse_ticket(rsc)
            files = extract_file_urls(rsc)
            pdfs = [f for f in files if f["tipo"] == "pdf"]
            imgs = [f for f in files if f["tipo"] == "img"]

            # Mostrar datos del ticket en UI
            nombre = (ticket or {}).get("fullName", "")
            rut_ticket = (ticket or {}).get("rut", "")
            patente_ticket = (ticket or {}).get("patente", "")
            email = (ticket or {}).get("email", "")

            self.after(0, self.result_vars["solicitud"].set, str(desk))
            if nombre:
                self.after(0, self.result_vars["nombre"].set, nombre)
            if rut_ticket:
                self.after(0, self.result_vars["rut"].set, rut_ticket)
                self.after(0, self._actualizar_rut_val, rut_ticket)
            if patente_ticket:
                self.after(0, self.result_vars["patente"].set, patente_ticket)
            if email:
                self.after(0, self.result_vars["email"].set, email)

            # Descargar imagen(es)
            if imgs:
                log.info("Descargando %s imagen(es)...", len(imgs))
                self.after(0, self._limpiar_imagen)
                self.after(0, self._set_img_urls, [f["url"] for f in imgs])
            else:
                self.after(0, self._set_imagen_error)
                log.info("Ticket sin imagenes adjuntas.")

            # Descargar PDFs y extraer
            if pdfs:
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                log.info("Descargando %s PDF(s)...", len(pdfs))
                for i, file in enumerate(pdfs, 1):
                    p = download_pdf(self.session, file["url"], OUT_DIR, i)
                    if not p:
                        continue
                    text = extract_text(p)
                    if not text:
                        continue
                    nombres = find_nombres(text)
                    if nombres:
                        self.after(0, self.result_vars["nombre"].set, nombres[0])
                    ruts = find_ruts(text)
                    if ruts:
                        self.after(0, self.result_vars["rut"].set, ruts[0])
                        self.after(0, self._actualizar_rut_val, ruts[0])
                    patentes = find_patentes(text)
                    if patentes:
                        self.after(0, self.result_vars["patente"].set, patentes[0])
            else:
                log.info("Ticket sin PDFs adjuntos.")

            log.info("Listo.")

        except Exception as e:
            log.error("Error: %s", e)
        finally:
            self.after(0, self._set_busy, False)


if __name__ == "__main__":
    App().mainloop()
