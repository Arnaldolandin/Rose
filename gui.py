import logging
import threading
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, scrolledtext
import io
import os

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
    find_telefono,
    find_direccion,
    validar_rut,
    check_vigente_optimo,
    download_img,
    ocr_image,
    log,
)
from servipag import consultar_deudas, EMPRESAS

OUT_DIR = Path("./pdfs")
MAX_IMG_W, MAX_IMG_H = 500, 500

# Directorio base: junto al .exe (frozen) o junto al .py (desarrollo)
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
    MEIPASS = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).parent
    MEIPASS = BASE_DIR

ROSE_ICO_B64 = "AAABAAEAICAAAAEAIACoEAAAFgAAACgAAAAgAAAAQAAAAAEAIAAAAAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGRQ8P9kUPD/ZFDw/2RQ8P9kUPD/ZFDw/2RQ8P9kUPD/ZFDw/2RQ8P9kUPD/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGRQ8P9kUPD/ZFDw/2RQ8P9kUPD/ZFDw/2RQ8P9kUPD/ZFDw/2RQ8P9kUPD/ZFDw/2RQ8P9kUPD/ZFDw/wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABkUPD/ZFDw/2RQ8P9kUPD/ZFDw/2RQ8P9kUPD/ZFDw/2RQ8P9kUPD/ZFDw/2RQ8P9kUPD/ZFDw/2RQ8P9kUPD/ZFDw/wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAZFDw/2RQ8P9kUPD/ZFDw/2RQ8P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P9kUPD/ZFDw/2RQ8P9kUPD/ZFDw/wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGRQ8P9kUPD/ZFDw/2RQ8P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/ZFDw/2RQ8P9kUPD/ZFDw/wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABkUPD/ZFDw/2RQ8P9kUPD/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/ZFDw/2RQ8P9kUPD/ZFDw/wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAZFDw/2RQ8P9kUPD/ZFDw/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/ZFDw/2RQ8P9kUPD/ZFDw/wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABkUPD/ZFDw/2RQ8P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/ZFDw/2RQ8P9kUPD/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAZFDw/2RQ8P9kUPD/ZFDw/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P9kUPD/ZFDw/2RQ8P9kUPD/AAAAAAAAAAAAAAAAAAAAAAAAAABkUPD/ZFDw/2RQ8P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P9kUPD/ZFDw/2RQ8P8AAAAAAAAAAAAAAAAAAAAAAAAAAGRQ8P9kUPD/ZFDw/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/2RQ8P9kUPD/ZFDw/wAAAAAAAAAAAAAAAAAAAAAAAAAAZFDw/2RQ8P9kUPD/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/ZFDw/2RQ8P9kUPD/AAAAAAAAAAAAAAAAAAAAAAAAAABkUPD/ZFDw/2RQ8P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P9kUPD/ZFDw/2RQ8P8AAAAAAAAAAAAAAAAAAAAAAAAAAGRQ8P9kUPD/ZFDw/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/2RQ8P9kUPD/ZFDw/wAAAAAAAAAAAAAAAAAAAAAAAAAAZFDw/2RQ8P9kUPD/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/ZFDw/2RQ8P9kUPD/AAAAAAAAAAAAAAAAAAAAAAAAAABkUPD/ZFDw/2RQ8P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P9kUPD/ZFDw/2RQ8P8AAAAAAAAAAAAAAAAAAAAAAAAAAGRQ8P9kUPD/ZFDw/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/2RQ8P9kUPD/ZFDw/wAAAAAAAAAAAAAAAAAAAAAAAAAAZFDw/2RQ8P9kUPD/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/ZFDw/2RQ8P9kUPD/AAAAAAAAAAAAAAAAAAAAAAAAAABkUPD/ZFDw/2RQ8P9kUPD/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/2RQ8P9kUPD/ZFDw/2RQ8P8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABkUPD/ZFDw/2RQ8P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P88FNz/ZFDw/2RQ8P9kUPD/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGRQ8P9kUPD/ZFDw/2RQ8P88FNz/PBTc/zwU3P88FNz/PBTc/zwU3P8ytDL/MrQy/zK0Mv8ytDL/MrQy/zwU3P88FNz/PBTc/zwU3P88FNz/PBTc/2RQ8P9kUPD/ZFDw/2RQ8P8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGRQ8P9kUPD/ZFDw/2RQ8P88FNz/PBTc/zwU3P88FNz/MrQy/zK0Mv8ytDL/MrQy/zK0Mv8ytDL/MrQy/zwU3P88FNz/PBTc/zwU3P9kUPD/ZFDw/2RQ8P9kUPD/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGRQ8P9kUPD/ZFDw/2RQ8P88FNz/PBTc/zwU3P8ytDL/MrQy/zK0Mv8ytDL/MrQy/zK0Mv8ytDL/PBTc/zwU3P88FNz/ZFDw/2RQ8P9kUPD/ZFDw/wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGRQ8P9kUPD/ZFDw/2RQ8P9kUPD/PBTc/zK0Mv8ytDL/MrQy/zK0Mv8ytDL/MrQy/zK0Mv88FNz/ZFDw/2RQ8P9kUPD/ZFDw/2RQ8P8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGRQ8P9kUPD/ZFDw/2RQ8P9kUPD/ZFDw/zK0Mv8ytDL/MrQy/zK0Mv8ytDL/ZFDw/2RQ8P9kUPD/ZFDw/2RQ8P9kUPD/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGRQ8P9kUPD/ZFDw/2RQ8P9kUPD/ZFDw/2RQ8P9kUPD/ZFDw/2RQ8P9kUPD/ZFDw/2RQ8P9kUPD/ZFDw/wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABkUPD/ZFDw/2RQ8P9kUPD/ZFDw/2RQ8P9kUPD/ZFDw/2RQ8P9kUPD/ZFDw/wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAiiyL/Iosi/yKLIv8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

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
        self.title("Rose")
        self.geometry("950x650+0+0")
        self._set_icon()
        self.resizable(True, True)

        self.session: requests.Session | None = None
        self._busy = False
        self._img_urls: list[str] = []
        self._img_idx = -1
        # Lupa (magnifying glass)
        self._pil_original = None
        self._img_scale = 1.0
        self._display_w = 0
        self._display_h = 0
        self._lupa_visible = False
        self._lupa_win = None
        self._lupa_canvas = None
        self._lupa_photo = None

        self._build_ui()
        self._start_login()

    def _set_icon(self):
        import base64, tempfile
        ico_path = MEIPASS / "rose.ico"
        if not ico_path.exists():
            ico_path = Path(tempfile.mktemp(suffix=".ico"))
            ico_path.write_bytes(base64.b64decode(ROSE_ICO_B64))
        try:
            self.iconbitmap(str(ico_path))
            self.iconbitmap(default=str(ico_path))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        main = ttk.Frame(self, padding=12)
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(1, weight=1)
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
        self.ticket_entry.bind("<Button-3>", self._popup_paste)
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
            ("Direccion:", "direccion"),
            ("Telefono:", "telefono"),
            ("Email:", "email"),
            ("Solicitud:", "solicitud"),
            ("Status:", "status"),
        ]
        self._status_label = None
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
            if key == "status":
                self._status_label = val_label

            if key == "rut":
                self._rut_val_label = ttk.Label(row, text="", font=("Consolas", 10))
                self._rut_val_label.pack(side=tk.LEFT, padx=(0, 4))

            btn = ttk.Button(row, text="Copiar", width=5, command=lambda k=key: self._copiar(k))
            btn.pack(side=tk.LEFT, padx=2)

        # -- Servipag section --
        sep = ttk.Separator(results_frame, orient="horizontal")
        sep.pack(fill=tk.X, pady=(8, 4))
        sp_row = ttk.Frame(results_frame)
        sp_row.pack(fill=tk.X, pady=2)
        ttk.Label(sp_row, text="Servipag:", width=10, anchor=tk.E).pack(side=tk.LEFT)
        self.sp_empresa = ttk.Combobox(
            sp_row, values=list(EMPRESAS.keys()), state="readonly", width=22
        )
        self.sp_empresa.set("Pago Total TAG")
        self.sp_empresa.pack(side=tk.LEFT, padx=(6, 4))
        self.sp_btn = ttk.Button(
            sp_row, text="Ver Deudas", command=self._consultar_deudas, width=10
        )
        self.sp_btn.pack(side=tk.LEFT, padx=2)
        self.sp_status_var = tk.StringVar(value="")
        ttk.Label(sp_row, textvariable=self.sp_status_var, font=("Consolas", 9)).pack(
            side=tk.LEFT, padx=(6, 0)
        )

        # -- Right: image preview (row 1, col 1) --
        img_frame = ttk.LabelFrame(main, text="Foto", padding=8)
        img_frame.grid(row=1, column=1, sticky=tk.NSEW, pady=(0, 8))
        img_frame.columnconfigure(0, weight=1)
        img_frame.rowconfigure(0, weight=1)

        self.img_label = ttk.Label(img_frame, text="(sin imagen)")
        self.img_label.grid(row=0, column=0, columnspan=2, sticky=tk.NSEW, pady=(0, 6))

        nav = ttk.Frame(img_frame)
        nav.grid(row=1, column=0, columnspan=2)
        self.btn_anterior = ttk.Button(nav, text="< Anterior", command=self._img_anterior, state="disabled")
        self.btn_anterior.pack(side=tk.LEFT, padx=4)
        self.btn_siguiente = ttk.Button(nav, text="Siguiente >", command=self._img_siguiente, state="disabled")
        self.btn_siguiente.pack(side=tk.LEFT, padx=4)

        self._main = main
        log_frame = ttk.LabelFrame(main, text="", padding=0)
        log_frame.grid(row=2, column=0, columnspan=2, sticky=tk.NSEW)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)

        self._log_visible = tk.BooleanVar(value=False)
        ttk.Checkbutton(log_frame, text="Log", variable=self._log_visible,
                        command=self._toggle_log).grid(row=0, column=0, sticky=tk.W, padx=4, pady=(2, 0))
        self.log_area = scrolledtext.ScrolledText(
            log_frame,
            height=12,
            font=("Consolas", 9),
            state="disabled",
            wrap=tk.WORD,
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white",
        )
        self.log_area.grid(row=1, column=0, sticky=tk.NSEW, padx=4, pady=(2, 4))
        self.log_area.grid_remove()
        self._main.rowconfigure(2, weight=0)

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
            cfg_path = BASE_DIR / "config.json"
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
            txt = val.replace(".", "").replace("-", "") if key == "rut" else val
            self.clipboard_clear()
            self.clipboard_append(txt)
            log.info("Copiado '%s' al portapapeles", txt)

    def _consultar_deudas(self):
        rut = self.result_vars["rut"].get()
        if not rut or rut == "—":
            log.warning("No hay RUT para consultar")
            return
        empresa = self.sp_empresa.get()
        self.sp_btn.configure(state="disabled")
        self.sp_status_var.set("Consultando...")
        log.info("Consultando Servipag: RUT=%s, empresa=%s", rut, empresa)
        threading.Thread(target=self._do_consultar_deudas, args=(rut, empresa), daemon=True).start()

    def _do_consultar_deudas(self, rut: str, empresa: str):
        try:
            res = consultar_deudas(rut, empresa)
            self.after(0, self._mostrar_resultado_servipag, res)
        except Exception as e:
            log.error("Error consulta Servipag: %s", e)
            self.after(0, self.sp_status_var.set, f"Error: {e}")
            self.after(0, self.sp_btn.configure, {"state": "normal"})

    def _mostrar_resultado_servipag(self, res: dict):
        self.sp_btn.configure(state="normal")
        if not res.get("success"):
            msg = res.get("error", "Error desconocido")
            self.sp_status_var.set("Error")
            log.error("Servipag: %s", msg)
            return

        if res.get("sin_deudas"):
            self.sp_status_var.set("Sin deudas ✓")
            log.info("Servipag: SIN deudas para %s en %s",
                     res.get("empresa", ""), self.result_vars["rut"].get())
        elif res.get("deudas"):
            n = len(res["deudas"])
            total = res.get("total") or sum(d["monto"] for d in res["deudas"])
            self.sp_status_var.set(f"{n} deuda(s): ${total:,.0f}")
            log.info("Servipag: %s deuda(s) encontradas para %s en %s",
                     n, self.result_vars["rut"].get(), res.get("empresa", ""))
            for d in res["deudas"]:
                log.info("  Deuda: %s", d.get("descripcion", ""))
            # Mostrar popup con detalles
            self._mostrar_popup_deudas(res)
        else:
            self.sp_status_var.set("Sin resultados")
            log.info("Servipag: sin resultados para %s", self.result_vars["rut"].get())

    def _mostrar_popup_deudas(self, res: dict):
        win = tk.Toplevel(self)
        win.title(f"Deudas - {res.get('empresa', '')}")
        win.geometry("500x300")
        win.transient(self)
        win.grab_set()

        frame = ttk.Frame(win, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text=f"Deudas encontradas para RUT {self.result_vars['rut'].get()}",
                  font=("Consolas", 10, "bold")).pack(anchor=tk.W, pady=(0, 8))

        text = tk.Text(frame, font=("Consolas", 10), wrap=tk.WORD, height=10)
        text.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        total = 0
        for i, d in enumerate(res["deudas"], 1):
            desc = d.get("descripcion", "")
            monto = d.get("monto_raw", "")
            text.insert(tk.END, f"{i}. {desc}\n")
            if monto:
                text.insert(tk.END, f"   Monto: {monto}\n\n")
            total += d.get("monto", 0)

        if res.get("total") is not None:
            text.insert(tk.END, f"\n{'='*40}\nTotal: ${res['total']:,.0f}\n")

        text.configure(state="disabled")

        ttk.Button(frame, text="Cerrar", command=win.destroy).pack()

    def _popup_paste(self, event):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Pegar", command=self._paste_from_clip)
        menu.tk_popup(event.x_root, event.y_root)

    def _paste_from_clip(self):
        try:
            txt = self.clipboard_get()
            self.ticket_entry.insert(tk.INSERT, txt)
        except tk.TclError:
            pass

    def _actualizar_rut_val(self, rut: str):
        if not rut or rut == "—":
            self._rut_val_label.configure(text="")
            return
        valido = validar_rut(rut)
        texto = "✓" if valido else "✗"
        color = "green" if valido else "red"
        self._rut_val_label.configure(text=texto, foreground=color)

    def _set_status(self, text: str, color: str):
        self.result_vars["status"].set(text)
        if self._status_label:
            self._status_label.configure(foreground=color)

    def _toggle_log(self):
        if self._log_visible.get():
            self.log_area.grid()
            self._main.rowconfigure(2, weight=1)
        else:
            self.log_area.grid_remove()
            self._main.rowconfigure(2, weight=0)

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
            self._pil_original = Image.open(img_data)

            w, h = self._pil_original.size
            scale = min(MAX_IMG_W / w, MAX_IMG_H / h, 1.0)
            display_w = int(w * scale) if scale < 1.0 else w
            display_h = int(h * scale) if scale < 1.0 else h
            self._img_scale = scale if scale < 1.0 else 1.0
            self._display_w = display_w
            self._display_h = display_h

            if scale < 1.0:
                pil_display = self._pil_original.resize((display_w, display_h), Image.LANCZOS)
            else:
                pil_display = self._pil_original

            self._tk_img = ImageTk.PhotoImage(pil_display)
            self.after(0, self._set_imagen, self._tk_img)
        except Exception as e:
            log.warning("Error al cargar imagen: %s", e)
            self.after(0, self._set_imagen_error)
            self._pil_original = None

    def _set_imagen(self, photo):
        caption = f"{self._img_idx + 1}/{len(self._img_urls)}" if self._img_urls else ""
        self.img_label.configure(image=photo, text=caption, compound=tk.BOTTOM)
        # Bind mouse events for magnifier
        self.img_label.bind("<Enter>", self._activar_lupa)
        self.img_label.bind("<Leave>", self._desactivar_lupa)
        self.img_label.bind("<Motion>", self._mover_lupa)

    # ------------------------------------------------------------------
    # Lupa (magnifying glass)
    # ------------------------------------------------------------------

    def _activar_lupa(self, event=None):
        if self._pil_original is None:
            return
        self._lupa_visible = True
        self._lupa_win = tk.Toplevel(self)
        self._lupa_win.title("")
        self._lupa_win.overrideredirect(True)
        self._lupa_win.attributes("-topmost", True)
        self._lupa_canvas = tk.Canvas(self._lupa_win, width=160, height=160,
                                       highlightthickness=1, highlightbackground="gray")
        self._lupa_canvas.pack()
        self._mover_lupa(event)

    def _desactivar_lupa(self, event=None):
        self._lupa_visible = False
        if hasattr(self, "_lupa_win") and self._lupa_win:
            try:
                self._lupa_win.destroy()
            except Exception:
                pass
            self._lupa_win = None

    def _mover_lupa(self, event):
        if not hasattr(self, "_lupa_visible") or not self._lupa_visible:
            return
        if self._pil_original is None:
            return

        # Mouse position relative to label
        mx, my = event.x, event.y
        if mx < 0 or my < 0 or mx > self._display_w or my > self._display_h:
            return

        # Map to original image coordinates
        ox = int(mx / self._img_scale)
        oy = int(my / self._img_scale)

        # Crop 134x134 region around cursor from ORIGINAL image, then scale up 1.2x
        half = 67
        ow, oh = self._pil_original.size
        left = max(0, ox - half)
        upper = max(0, oy - half)
        right = min(ow, ox + half)
        lower = min(oh, oy + half)
        crop = self._pil_original.crop((left, upper, right, lower))
        zoomed = crop.resize((160, 160), Image.NEAREST)

        self._lupa_photo = ImageTk.PhotoImage(zoomed)
        self._lupa_canvas.create_image(80, 80, image=self._lupa_photo)

        # Draw crosshair
        self._lupa_canvas.delete("crosshair")
        cw, ch = 160, 160
        self._lupa_canvas.create_line(cw // 2, 0, cw // 2, ch, fill="red", tags="crosshair")
        self._lupa_canvas.create_line(0, ch // 2, cw, ch // 2, fill="red", tags="crosshair")

        # Position near cursor
        wx = event.x_root + 20
        wy = event.y_root + 20
        # Keep on screen
        if wx + 160 > self.winfo_screenwidth():
            wx = event.x_root - 180
        if wy + 160 > self.winfo_screenheight():
            wy = event.y_root - 180
        self._lupa_win.geometry(f"+{wx}+{wy}")

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
            direccion_ticket = (ticket or {}).get("direccion", "")
            telefono_ticket = (ticket or {}).get("telefono", "")

            self.after(0, self.result_vars["solicitud"].set, str(desk))
            if nombre:
                self.after(0, self.result_vars["nombre"].set, nombre)
            if rut_ticket:
                self.after(0, self.result_vars["rut"].set, rut_ticket)
                self.after(0, self._actualizar_rut_val, rut_ticket)
            if patente_ticket:
                self.after(0, self.result_vars["patente"].set, patente_ticket)
            if direccion_ticket:
                self.after(0, self.result_vars["direccion"].set, direccion_ticket)
            if telefono_ticket:
                self.after(0, self.result_vars["telefono"].set, telefono_ticket)
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
            status_global = {"vigente": None, "rechazado": False, "no_vigente": False, "similitud_pct": None}
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
                    telefonos = find_telefono(text)
                    if telefonos:
                        self.after(0, self.result_vars["telefono"].set, telefonos[0])
                    direcciones = find_direccion(text)
                    if direcciones:
                        self.after(0, self.result_vars["direccion"].set, direcciones[0])
                    # Verificar estado de identidad
                    vo = check_vigente_optimo(text)
                    if vo["vigente"] is False:
                        status_global["vigente"] = False
                    elif vo["vigente"] is True and status_global["vigente"] is None:
                        status_global["vigente"] = True
                    if vo["rechazado"]:
                        status_global["rechazado"] = True
                    if vo["no_vigente"]:
                        status_global["no_vigente"] = True
                    if vo.get("similitud_pct") is not None:
                        status_global["similitud_pct"] = vo["similitud_pct"]
            else:
                log.info("Ticket sin PDFs adjuntos.")

            # DOWNLOAD AND OCR IMAGES
            for i, file in enumerate(imgs, 1):
                p = download_img(self.session, file["url"], OUT_DIR, i)
                if not p:
                    continue
                text = ocr_image(p)
                if not text:
                    continue
                vo = check_vigente_optimo(text)
                if vo["vigente"] is False:
                    status_global["vigente"] = False
                elif vo["vigente"] is True and status_global["vigente"] is None:
                    status_global["vigente"] = True
                if vo["rechazado"]:
                    status_global["rechazado"] = True
                if vo["no_vigente"]:
                    status_global["no_vigente"] = True
                if vo.get("similitud_pct") is not None and status_global["similitud_pct"] is None:
                    status_global["similitud_pct"] = vo["similitud_pct"]

            # Determinar status final
            rechazado = status_global["vigente"] is False or status_global["rechazado"] or status_global["no_vigente"]
            sim = status_global["similitud_pct"]
            if rechazado:
                status_text = "RECHAZADO"
                status_color = "red"
            elif sim is not None and sim >= 50:
                status_text = "APROBADO"
                status_color = "green"
            else:
                status_text = "PENDIENTE"
                status_color = "orange"
            log.info("Status: %s (similitud=%s%%, vigente=%s, rechazado=%s)",
                     status_text, sim, status_global["vigente"], status_global["rechazado"])
            self.after(0, self._set_status, status_text, status_color)

            log.info("Listo.")

        except Exception as e:
            log.error("Error: %s", e)
        finally:
            self.after(0, self._set_busy, False)


if __name__ == "__main__":
    App().mainloop()
