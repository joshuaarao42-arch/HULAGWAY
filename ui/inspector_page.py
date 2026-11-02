from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core.image_ops import ProcessOptions, inspect_image, make_thumbnail, process_image
from core.utils import format_bytes, reveal_in_folder
from .theme import COLORS, button, font
from .widgets import Card, ImageView, PageHeader, card_title, make_tree, muted, tree_with_scroll

IMG_TYPES = [("Images", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff"), ("All files", "*.*")]


class InspectorPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.path = None
        self.details = None
        self._token = 0
        self.grid_columnconfigure(0, weight=2, uniform="i")
        self.grid_columnconfigure(1, weight=3, uniform="i")
        self.grid_rowconfigure(1, weight=1)
        PageHeader(self, "Image Inspector", "Image details").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        left = Card(self)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(left, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=14, pady=12)
        button(top, "Choose image", self.pick, width=130).pack(side="left")
        button(top, "Show in folder", self._reveal, "secondary", width=120).pack(side="left", padx=8)
        self.preview = ImageView(left, "Choose an image to inspect", min_size=(260, 260))
        self.preview.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        right = Card(self)
        right.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
        right.grid_rowconfigure(2, weight=1)
        right.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(right, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))
        card_title(head, "Details").pack(side="left")
        button(head, "Copy", self.copy, "secondary", width=70).pack(side="right")
        button(head, "Save clean copy", self.clean_copy, "secondary", width=130).pack(side="right", padx=6)
        self.warn = ctk.CTkLabel(right, text="", text_color=COLORS["warning"], font=font(12), anchor="w")
        self.warn.grid(row=1, column=0, sticky="ew", padx=16)
        self.tree = tree_with_scroll(right, lambda p: make_tree(p, [
            ("prop", "Property", 190, "w", False), ("value", "Value", 400, "w", True)], "browse"))
        self.tree._holder.grid(row=2, column=0, sticky="nsew", padx=12, pady=(4, 12))

    def pick(self) -> None:
        p = filedialog.askopenfilename(title="Choose an image", filetypes=IMG_TYPES)
        if p:
            self.load(Path(p))

    def load(self, path: Path) -> None:
        self._token += 1
        token = self._token
        self.preview.message("Loading")

        def job():
            return inspect_image(path), make_thumbnail(path, (700, 700))[0]

        def done(res):
            if token != self._token:
                return
            self.path, (self.details, thumb) = path, res
            self.preview.set_image(thumb)
            self._fill()

        def fail(exc):
            if token == self._token:
                self.preview.message("Cannot read this file")
                self.tree.delete(*self.tree.get_children())
                messagebox.showerror("Cannot inspect image", str(exc))

        self.app.bridge.run_async(job, done, fail)

    def _fill(self) -> None:
        t, info = self.tree, self.details
        t.delete(*t.get_children())

        def group(name, rows, empty):
            t.insert("", "end", values=(f"  {name}", ""), tags=("group",))
            for k, v in rows or [(empty, "")]:
                t.insert("", "end", values=(k, v))

        group("IMAGE", info["basic"], "")
        group("METADATA EXIF", info["exif"], "No EXIF metadata")
        if info["other"]:
            group("OTHER EMBEDDED DATA", info["other"], "")
        self.warn.configure(text="GPS data found clean copy recommended"
                            if info["has_gps"] else "")

    def _text(self) -> str:
        if not self.details:
            return ""
        lines = [f"{k}: {v}" for k, v in self.details["basic"]] + ["", "EXIF:"] + \
                [f"{k}: {v}" for k, v in self.details["exif"]]
        return "\n".join(lines)

    def copy(self) -> None:
        if not self.details:
            return
        self.clipboard_clear()
        self.clipboard_append(self._text())

    def _reveal(self) -> None:
        if self.path:
            reveal_in_folder(self.path)

    def clean_copy(self) -> None:
        if not self.path:
            messagebox.showinfo("Inspector", "Choose an image first")
            return
        res = process_image(self.path, self.app.output_dir,
                            ProcessOptions(strip_metadata=True, quality=95, suffix="_clean"))
        if res.ok:
            self.app.db.add_results("Compress", [res])
            messagebox.showinfo("Saved", f"Metadata free copy saved\n{res.dest}\n{format_bytes(res.new_size)}")
        else:
            messagebox.showerror("Could not save", res.error or "Unknown error")
