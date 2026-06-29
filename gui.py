import logging
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, scrolledtext

import requests

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
    log,
)

OUT_DIR = Path("./pdfs")

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
        self.geometry("700x600")
        self.resizable(True, True)

        self.session: requests.Session | None = None
        self._busy = False

        self._build_ui()
        self._start_login()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        main = ttk.Frame(self, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        # -- Top: ticket input --
        top = ttk.Frame(main)
        top.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(top, text="Ticket:").pack(side=tk.LEFT)
        self.ticket_var = tk.StringVar()
        self.ticket_entry = ttk.Entry(
            top, textvariable=self.ticket_var, width=20, font=("Consolas", 12)
        )
        self.ticket_entry.pack(side=tk.LEFT, padx=6)
        self.ticket_entry.bind("<Return>", lambda e: self._buscar())
        self.ticket_entry.focus()

        self.buscar_btn = ttk.Button(
            top, text="Buscar", command=self._buscar, style="Accent.TButton"
        )
        self.buscar_btn.pack(side=tk.LEFT)

        # -- Results --
        self.result_vars: dict[str, tk.StringVar] = {}
        results_frame = ttk.LabelFrame(main, text="Resultado", padding=8)
        results_frame.pack(fill=tk.X, pady=(0, 8))

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
            ttk.Label(
                row,
                textvariable=var,
                font=("Consolas", 11, "bold"),
                foreground="#2b2b2b",
            ).pack(side=tk.LEFT, padx=6)

        # -- Status / Log --
        ttk.Label(main, text="Log:").pack(anchor=tk.W)
        self.log_area = scrolledtext.ScrolledText(
            main,
            height=14,
            font=("Consolas", 9),
            state="disabled",
            wrap=tk.WORD,
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white",
        )
        self.log_area.pack(fill=tk.BOTH, expand=True)

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
            cfg = {
                "user": None,
                "password": None,
                "desk": None,
            }
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
        self._set_busy(True)
        threading.Thread(target=self._do_buscar, args=(desk,), daemon=True).start()

    def _limpiar_resultados(self):
        for var in self.result_vars.values():
            var.set("—")

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
            if patente_ticket:
                self.after(0, self.result_vars["patente"].set, patente_ticket)
            if email:
                self.after(0, self.result_vars["email"].set, email)

            if not pdfs:
                log.warning("Ticket %s no tiene PDFs adjuntos", desk)
                self.after(0, self._set_busy, False)
                return

            # Descargar PDFs y extraer
            self.after(0, log.info, f"Descargando {len(pdfs)} PDF(s)...")
            OUT_DIR.mkdir(parents=True, exist_ok=True)

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
                patentes = find_patentes(text)
                if patentes:
                    self.after(0, self.result_vars["patente"].set, patentes[0])

            log.info("Listo.")

        except Exception as e:
            log.error("Error: %s", e)
        finally:
            self.after(0, self._set_busy, False)


if __name__ == "__main__":
    App().mainloop()
