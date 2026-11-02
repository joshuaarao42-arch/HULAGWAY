from __future__ import annotations

import sys
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image

from core.database import Database
from .compare_page import ComparePage
from .dashboard_page import DashboardPage
from .history_page import HistoryPage
from .inspector_page import InspectorPage
from .theme import COLORS, font, set_mode, setup_theme, style_ttk
from .tool_page import BatchPage, CompressorPage, ConverterPage, ResizerPage
from .widgets import UIBridge

ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "assets"
 
NAV = [("dashboard", "Dashboard"), ("compressor", "Compressor"), ("converter", "Converter"),
       ("resizer", "Resizer"), ("batch", "Batch Processor"), ("compare", "Before After"),
       ("inspector", "Inspector"), ("history", "History")]


class HulagwayApp(ctk.CTk):
    def __init__(self):
        self.mode = "dark"
        setup_theme()
        super().__init__()
        self.title("Hulagway Image Optimization and Conversion Studio")
        self._set_icon()
        self.geometry("1320x860")
        self.minsize(1120, 720)
        self.configure(fg_color=COLORS["bg"])
        style_ttk(self)

        self.db = Database()
        self.bridge = UIBridge(self)
        saved = self.db.get_setting("output_dir")
        self.output_dir = Path(saved) if saved else Path.home() / "Pictures" / "Hulagway"

        self._build_sidebar()
        self._build_interface()
        self.protocol("WM_DELETE_WINDOW", self._confirm_quit)

    def set_output_dir(self, path: Path) -> None:
        self.output_dir = Path(path)
        self.db.set_setting("output_dir", str(self.output_dir))

    def navigate(self, name: str) -> None:
        self.current = name
        page = self.pages[name]
        page.tkraise()
        for key, btn in self.nav_buttons.items():
            active = key == name
            btn.configure(fg_color=COLORS["accent"] if active else "transparent",
                          text_color=COLORS["on_accent"] if active else COLORS["muted"])
        if hasattr(page, "on_show"):
            page.on_show()

    def open_compare(self, original: Path, optimized: Path | None = None) -> None:
        self.navigate("compare")
        self.pages["compare"].load(original, optimized)

    def _build_interface(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.content = ctk.CTkFrame(self, fg_color=COLORS["bg"])
        self.content.grid(row=0, column=1, sticky="nsew", padx=22, pady=20)
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)
        self.pages = {
            "dashboard": DashboardPage(self.content, self),
            "compressor": CompressorPage(self.content, self),
            "converter": ConverterPage(self.content, self),
            "resizer": ResizerPage(self.content, self),
            "batch": BatchPage(self.content, self),
            "compare": ComparePage(self.content, self),
            "inspector": InspectorPage(self.content, self),
            "history": HistoryPage(self.content, self),
        }
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")
        self.current = ""
        self.navigate("dashboard")

    def toggle_mode(self) -> None:
        self.mode = "light" if self.mode == "dark" else "dark"
        set_mode(self.mode)
        setup_theme()
        self.configure(fg_color=COLORS["bg"])
        style_ttk(self)
        for child in self.winfo_children():
            child.destroy()
        self._build_sidebar()
        self._build_interface()

    def _build_sidebar(self) -> None:
        side = ctk.CTkFrame(self, width=230, corner_radius=0, fg_color=COLORS["sidebar"])
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)
        head = ctk.CTkFrame(side, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(24, 4))
        self._logo = self._load_logo(46)
        if self._logo:
            ctk.CTkLabel(head, text="", image=self._logo).pack(side="left")
        ctk.CTkLabel(head, text="Hulagway", font=font(25, "bold"), text_color=COLORS["text"]).pack(
            side="left", padx=(10, 0))
        ctk.CTkSwitch(side, text="Night mode", command=self.toggle_mode, font=font(11),
                      variable=ctk.BooleanVar(value=self.mode == "dark"), onvalue=True,
                      offvalue=False).pack(anchor="w", padx=22, pady=(10, 14))
        self.nav_buttons = {}
        for key, text in NAV:
            b = ctk.CTkButton(side, text=text, anchor="w", height=40, corner_radius=10, fg_color="transparent",
                              hover_color=COLORS["accent_dim"], text_color=COLORS["on_accent"], font=font(14, "bold"),
                              command=lambda k=key: self.navigate(k))
            b.pack(fill="x", padx=12, pady=2)
            self.nav_buttons[key] = b

    def _set_icon(self) -> None:
        ico = ASSETS / "icon.ico"
        if not ico.exists():
            return
        def apply():
            try:
                self.iconbitmap(str(ico))
            except Exception:
                try:
                    from PIL import ImageTk
                    self._icon_photo = ImageTk.PhotoImage(Image.open(ASSETS / "logo.png").resize((64, 64)))
                    self.iconphoto(True, self._icon_photo)
                except Exception:
                    pass
        self.after(300, apply)

    @staticmethod
    def _load_logo(size: int):
        path = ASSETS / "logo.png"
        if not path.exists():
            return None
        img = Image.open(path).convert("RGBA")
        return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))

    def _confirm_quit(self) -> None:
        for page in self.pages.values():
            proc = getattr(page, "_processor", None)
            if proc is not None and proc.running:
                if not messagebox.askyesno("Quit", "A batch is still running Stop it and quit"):
                    return
                proc.cancel()
        self.destroy()
