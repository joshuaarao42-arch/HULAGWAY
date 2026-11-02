from __future__ import annotations

import io
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Optional

import customtkinter as ctk
from PIL import Image

from core.image_ops import (FORMAT_EXT, FORMAT_LABEL, LABEL_FORMAT, ProcessOptions, ProcessResult,
                            build_output, diff_image, load_image, psnr, quality_label, write_unique)
from core.utils import format_bytes, open_path
from .theme import COLORS, button, font
from .widgets import Card, ImageView, PageHeader, QualityControl, card_title, muted

IMG_TYPES = [("Images", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff"), ("All files", "*.*")]


def center_crop(img: Image.Image, box: tuple) -> Image.Image:
    w, h = img.size
    cw, ch = min(w, box[0]), min(h, box[1])
    left, top = (w - cw) // 2, (h - ch) // 2
    return img.crop((left, top, left + cw, top + ch))


class ComparePage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.orig_path: Optional[Path] = None
        self.orig_img: Optional[Image.Image] = None
        self.orig_fmt = ""
        self.orig_size = 0
        self.opt_img: Optional[Image.Image] = None
        self.opt_bytes: Optional[bytes] = None
        self.opt_size = 0
        self.opt_fmt = ""
        self.opt_note = ""
        self.score: Optional[float] = None
        self._token = 0
        self.grid_columnconfigure((0, 1), weight=1, uniform="v")
        self.grid_rowconfigure(2, weight=1)
        PageHeader(self, "Before After", "Side by side").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        ctl = Card(self)
        ctl.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        r1 = ctk.CTkFrame(ctl, fg_color="transparent")
        r1.pack(fill="x", padx=14, pady=(12, 4))
        button(r1, "Choose original", self.pick_original, width=140).pack(side="left")
        self.orig_label = muted(r1, "No image selected")
        self.orig_label.pack(side="left", padx=12)
        self.view = ctk.CTkSegmentedButton(r1, values=["Fit", "Crop", "Difference"], command=lambda _v: self.refresh(),
                                           selected_color=COLORS["accent"])
        self.view.set("Fit")
        self.view.pack(side="right")
        ctk.CTkLabel(r1, text="View ", text_color=COLORS["muted"]).pack(side="right")

        r2 = ctk.CTkFrame(ctl, fg_color="transparent")
        r2.pack(fill="x", padx=14, pady=(4, 12))
        self.source = ctk.CTkSegmentedButton(r2, values=["Generate preview", "Compare with file"],
                                             command=self._source_changed, selected_color=COLORS["accent"])
        self.source.set("Generate preview")
        self.source.pack(side="left")
        self.f_gen = ctk.CTkFrame(r2, fg_color="transparent")
        self.f_file = ctk.CTkFrame(r2, fg_color="transparent")
        self.fmt = ctk.CTkOptionMenu(self.f_gen, values=["Keep original", "JPG", "PNG", "WEBP"], width=130,
                                     fg_color=COLORS["card_alt"], button_color=COLORS["border"])
        self.fmt.pack(side="left", padx=(14, 8))
        self.quality = QualityControl(self.f_gen, 75)
        self.quality.configure(width=230)
        self.quality.pack(side="left", padx=8)
        self.scale = ctk.CTkOptionMenu(self.f_gen, values=["100%", "75%", "50%", "25%"], width=80,
                                       fg_color=COLORS["card_alt"], button_color=COLORS["border"])
        ctk.CTkLabel(self.f_gen, text="Scale", text_color=COLORS["muted"]).pack(side="left", padx=(10, 4))
        self.scale.pack(side="left")
        self.lossy = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self.f_gen, text="Lossy PNG", variable=self.lossy, width=20, checkbox_width=18,
                        checkbox_height=18, font=font(12)).pack(side="left", padx=10)
        button(self.f_gen, "Generate", self.generate, width=90).pack(side="left", padx=4)
        button(self.f_file, "Choose optimized file", self.pick_optimized, "secondary", width=170).pack(side="left", padx=(14, 0))
        self.f_gen.pack(side="left")

        self.panels = []
        for col, title in enumerate(("Original", "Optimized")):
            card = Card(self)
            card.grid(row=2, column=col, sticky="nsew", padx=(0, 6) if col == 0 else (6, 0))
            card.grid_rowconfigure(1, weight=1)
            card.grid_columnconfigure(0, weight=1)
            t = card_title(card, title)
            t.grid(row=0, column=0, sticky="w", padx=14, pady=(10, 4))
            v = ImageView(card, "Choose an image", min_size=(300, 220), max_scale=4.0)
            v.grid(row=1, column=0, sticky="nsew", padx=12)
            info = muted(card, "", wrap=420)
            info.grid(row=2, column=0, sticky="ew", padx=14, pady=(6, 10))
            self.panels.append((t, v, info))

        m = Card(self)
        m.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.metrics = ctk.CTkLabel(m, text="Choose an image",
                                    font=font(14), text_color=COLORS["text"], justify="left", anchor="w")
        self.metrics.pack(side="left", padx=16, pady=14)
        self.save_btn = button(m, "Save optimized copy", self.save_copy, width=160)
        self.save_btn.pack(side="right", padx=14)
        self.save_btn.configure(state="disabled")

    def load(self, original: Path, optimized: Optional[Path] = None) -> None:
        self._load_original(Path(original), then_optimized=Path(optimized) if optimized else None)

    def _source_changed(self, mode: str) -> None:
        self.f_gen.pack_forget()
        self.f_file.pack_forget()
        (self.f_gen if mode == "Generate preview" else self.f_file).pack(side="left")
        self.save_btn.configure(state="disabled")

    def pick_original(self) -> None:
        p = filedialog.askopenfilename(title="Choose the original image", filetypes=IMG_TYPES)
        if p:
            self._load_original(Path(p))

    def pick_optimized(self) -> None:
        if not self.orig_img:
            messagebox.showinfo("Compare", "Choose the original image first")
            return
        p = filedialog.askopenfilename(title="Choose the optimized image", filetypes=IMG_TYPES)
        if p:
            self._load_optimized_file(Path(p))

    def _load_original(self, path: Path, then_optimized: Optional[Path] = None) -> None:
        self._token += 1
        token = self._token
        self.orig_label.configure(text=f"Loading {path.name}")

        def done(res):
            if token != self._token:
                return
            img, fmt = res
            self.orig_path, self.orig_img, self.orig_fmt = path, img, fmt
            self.orig_size = path.stat().st_size
            self.opt_img = self.opt_bytes = None
            self.score = None
            self.orig_label.configure(text=str(path))
            self.refresh()
            if then_optimized:
                self.source.set("Compare with file")
                self._source_changed("Compare with file")
                self._load_optimized_file(then_optimized)
            else:
                self.generate()

        def fail(exc):
            self.orig_label.configure(text="")
            messagebox.showerror("Cannot open image", str(exc))

        self.app.bridge.run_async(lambda: load_image(path)[:2], done, fail)

    def _build_options(self) -> ProcessOptions:
        pct = int(self.scale.get().rstrip("%"))
        return ProcessOptions(output_format=LABEL_FORMAT.get(self.fmt.get()), quality=self.quality.get(),
                              png_lossy=self.lossy.get(), resize_mode="percent" if pct != 100 else "none",
                              percent=float(pct), suffix="_optimized")

    def generate(self) -> None:
        if not self.orig_img:
            messagebox.showinfo("Compare", "Choose an original image first")
            return
        self._token += 1
        token = self._token
        opts, orig, fmt = self._build_options(), self.orig_img, self.orig_fmt
        self.metrics.configure(text="Generating preview")

        def job():
            data, out_fmt, _ = build_output(orig, opts, fmt)
            dec = Image.open(io.BytesIO(data))
            dec.load()
            return data, out_fmt, dec, psnr(orig, dec)

        def done(res):
            if token != self._token:
                return
            self.opt_bytes, self.opt_fmt, self.opt_img, self.score = res
            self.opt_size, self.opt_note = len(self.opt_bytes), ""
            self.save_btn.configure(state="normal")
            self.refresh()

        self.app.bridge.run_async(job, done, lambda e: self.metrics.configure(text=f"Error {e}"))

    def _load_optimized_file(self, path: Path) -> None:
        self._token += 1
        token = self._token
        orig = self.orig_img

        def job():
            img, fmt, _ = load_image(path)
            return img, fmt, psnr(orig, img)

        def done(res):
            if token != self._token:
                return
            self.opt_img, self.opt_fmt, self.score = res
            self.opt_bytes, self.opt_size = None, path.stat().st_size
            self.opt_note = path.name
            self.save_btn.configure(state="disabled")
            self.refresh()

        self.app.bridge.run_async(job, done, lambda e: messagebox.showerror("Cannot open image", str(e)))

    def save_copy(self) -> None:
        if not self.opt_bytes or not self.orig_path:
            return
        try:
            dest = write_unique(self.app.output_dir, self.orig_path.stem + "_optimized",
                                FORMAT_EXT[self.opt_fmt], self.opt_bytes)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Save failed", str(exc))
            return
        res = ProcessResult(src=self.orig_path, status="success", dest=dest, orig_size=self.orig_size,
                            new_size=self.opt_size, orig_dims=self.orig_img.size, new_dims=self.opt_img.size,
                            src_format=self.orig_fmt, out_format=self.opt_fmt)
        self.app.db.add_results("Compress", [res])
        self.metrics.configure(text=f"Saved to {dest}")
        if messagebox.askyesno("Saved", f"Saved\n{dest}\n\nOpen the folder"):
            open_path(dest.parent)

    def refresh(self) -> None:
        (t0, v0, i0), (t1, v1, i1) = self.panels
        if self.orig_img is None:
            return
        a, b = self.orig_img, self.opt_img
        mode = self.view.get()
        t1.configure(text="Optimized" if mode != "Difference" else "Difference")
        i0.configure(text=f"{self.orig_fmt} · {a.size[0]}×{a.size[1]} · {format_bytes(self.orig_size)}")
        if b is None:
            v0.set_image(a)
            v1.set_image(None, "Generate or choose an optimized image")
            i1.configure(text="")
            return
        i1.configure(text=f"{self.opt_fmt} · {b.size[0]}×{b.size[1]} · {format_bytes(self.opt_size)}"
                          + (f" · {self.opt_note}" if self.opt_note else ""))
        v0._max_scale = v1._max_scale = 1.0 if mode == "Crop" else 4.0
        if mode == "Fit":
            v0.set_image(a)
            v1.set_image(b)
        elif mode == "Crop":
            box = v0.box_size()
            b_same = b if b.size == a.size else b.resize(a.size, Image.Resampling.LANCZOS)
            v0.set_image(center_crop(a, box))
            v1.set_image(center_crop(b_same, box))
        else:
            v0.set_image(a)
            v1.set_image(diff_image(a, b))

        change = (self.opt_size / self.orig_size - 1) * 100 if self.orig_size else 0
        saved = f"{-change:.1f}% smaller" if change <= 0 else f"{change:.1f}% larger"
        text = f"{format_bytes(self.orig_size)}  →  {format_bytes(self.opt_size)}   ({saved})"
        if self.score is not None:
            score = "identical" if self.score >= 99 else f"{self.score:.1f} dB"
            text += f"      Quality PSNR {score} {quality_label(self.score)}"
        self.metrics.configure(text=text)
