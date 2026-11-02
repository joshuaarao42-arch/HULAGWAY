from __future__ import annotations

import queue
import threading
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

import customtkinter as ctk
from PIL import Image

from core.image_ops import (PRESETS, ProcessResult, ValidationError, has_alpha,
                            over_checkerboard)
from core.utils import collect_images, format_bytes, format_saved
from .theme import COLORS, RADIUS, button, font

class UIBridge:
    """Lets worker threads schedule callbacks on the Tk main loop safely."""

    def __init__(self, root: ctk.CTk):
        self.root = root
        self._q: queue.SimpleQueue = queue.SimpleQueue()
        self._poll()

    def post(self, fn: Callable, *args, **kwargs) -> None:
        self._q.put((fn, args, kwargs))

    def run_async(self, job: Callable, on_done: Callable, on_error: Optional[Callable] = None) -> None:
        """Run job() on a thread; call on_done(result) / on_error(exc) on the UI thread."""
        def worker():
            try:
                result = job()
            except Exception as exc:  # noqa: BLE001
                if on_error:
                    self.post(on_error, exc)
                return
            self.post(on_done, result)
        threading.Thread(target=worker, daemon=True).start()

    def _poll(self) -> None:
        try:
            for _ in range(200):
                fn, args, kwargs = self._q.get_nowait()
                try:
                    fn(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001 - keep the UI alive
                    print("UI callback error:", exc)
        except queue.Empty:
            pass
        try:
            self.root.after(30, self._poll)
        except Exception:
            pass


class Card(ctk.CTkFrame):
    def __init__(self, master, **kw):
        kw.setdefault("fg_color", COLORS["card"])
        kw.setdefault("corner_radius", RADIUS)
        super().__init__(master, **kw)


class PageHeader(ctk.CTkFrame):
    def __init__(self, master, title: str, subtitle: str = ""):
        super().__init__(master, fg_color="transparent")
        ctk.CTkLabel(self, text=title, font=font(26, "bold"), text_color=COLORS["text"]).pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(self, text=subtitle, font=font(13), text_color=COLORS["muted"]).pack(anchor="w")


def card_title(parent, text: str, **kw) -> ctk.CTkLabel:
    return ctk.CTkLabel(parent, text=text, font=font(14, "bold"), text_color=COLORS["text"], **kw)


def muted(parent, text: str = "", wrap: int = 0, **kw) -> ctk.CTkLabel:
    return ctk.CTkLabel(parent, text=text, font=font(12), text_color=COLORS["muted"],
                        wraplength=wrap, justify="left", anchor="w", **kw)


class StatCard(Card):
    def __init__(self, master, title: str, value: str = "0", color: str = COLORS["accent_text"]):
        super().__init__(master)
        ctk.CTkLabel(self, text=title, font=font(12), text_color=COLORS["muted"]).pack(anchor="w", padx=18, pady=(14, 0))
        self._value = ctk.CTkLabel(self, text=value, font=font(26, "bold"), text_color=color)
        self._value.pack(anchor="w", padx=18, pady=(0, 14))

    def set(self, value: str) -> None:
        self._value.configure(text=value)


class ImageView(ctk.CTkFrame):
    """Fits an image inside its box (keeping aspect ratio); shows transparency on a checkerboard."""

    def __init__(self, master, placeholder: str = "No image", min_size=(200, 160), max_scale: float = 2.0):
        super().__init__(master, fg_color=COLORS["card_alt"], corner_radius=10,
                         width=min_size[0], height=min_size[1])
        self.grid_propagate(False)
        self.pack_propagate(False)
        self._placeholder = placeholder
        self._max_scale = max_scale
        self._src: Optional[Image.Image] = None
        self._ctk_img = None
        self._after = None
        self._blank = ctk.CTkImage(Image.new("RGBA", (1, 1), (0, 0, 0, 0)), size=(1, 1))
        self._label = ctk.CTkLabel(self, text=placeholder, text_color=COLORS["muted"],
                                   image=self._blank, compound="center")
        self._label.place(relx=0.5, rely=0.5, anchor="center")
        self.bind("<Configure>", self._on_resize)

    def box_size(self) -> tuple:
        return max(self.winfo_width() - 20, 40), max(self.winfo_height() - 20, 40)

    def set_image(self, img: Optional[Image.Image], text: Optional[str] = None) -> None:
        if img is None:
            self._src = None
            self._label.configure(image=self._blank, text=text or self._placeholder)
            return
        w, h = img.size
        if max(w, h) > 2400:
            s = 2400 / max(w, h)
            img = img.resize((max(1, round(w * s)), max(1, round(h * s))), Image.Resampling.BILINEAR)
        self._src = img
        self._render()

    def message(self, text: str) -> None:
        self._src = None
        self._label.configure(image=self._blank, text=text)

    def _on_resize(self, _event=None) -> None:
        if self._src is None:
            return
        if self._after:
            self.after_cancel(self._after)
        self._after = self.after(90, self._render)

    def _render(self) -> None:
        self._after = None
        if self._src is None:
            return
        bw, bh = self.box_size()
        w, h = self._src.size
        scale = min(bw / w, bh / h, self._max_scale)
        dw, dh = max(1, int(w * scale)), max(1, int(h * scale))
        img = over_checkerboard(self._src)
        if (dw, dh) != (w, h):
            img = img.resize((dw, dh), Image.Resampling.LANCZOS if scale < 1 else Image.Resampling.BILINEAR)
        self._ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(dw, dh))
        self._label.configure(image=self._ctk_img, text="")


def make_tree(parent, columns: list, selectmode: str = "extended") -> ttk.Treeview:
    """columns: [(id, heading, width, anchor, stretch)]"""
    tree = ttk.Treeview(parent, columns=[c[0] for c in columns], show="headings",
                        style="PP.Treeview", selectmode=selectmode)
    for cid, head, width, anchor, stretch in columns:
        tree.heading(cid, text=head, anchor=anchor)
        tree.column(cid, width=width, minwidth=40, anchor=anchor, stretch=stretch)
    tree.tag_configure("success", foreground=COLORS["text"])
    tree.tag_configure("skipped", foreground=COLORS["warning"])
    tree.tag_configure("failed", foreground=COLORS["danger"])
    tree.tag_configure("group", foreground=COLORS["accent_text"], background=COLORS["card"])
    return tree


def tree_with_scroll(parent, tree_factory) -> ttk.Treeview:
    holder = ctk.CTkFrame(parent, fg_color=COLORS["card_alt"], corner_radius=10)
    holder.grid_rowconfigure(0, weight=1)
    holder.grid_columnconfigure(0, weight=1)
    tree = tree_factory(holder)
    sb = ttk.Scrollbar(holder, orient="vertical", command=tree.yview, style="PP.Vertical.TScrollbar")
    tree.configure(yscrollcommand=sb.set)
    tree.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
    sb.grid(row=0, column=1, sticky="ns", pady=6, padx=(0, 4))
    tree._holder = holder  # type: ignore[attr-defined]
    return tree


class ResultsTable(Card):
    """Live table of per-file processing results."""

    def __init__(self, master, on_open: Optional[Callable[[ProcessResult], None]] = None, title="Results"):
        super().__init__(master)
        self._results: dict = {}
        self._on_open = on_open
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
        card_title(head, title).pack(side="left")
        self.hint = muted(head, "Double click to compare")
        self.hint.pack(side="right")
        self.tree = tree_with_scroll(self, lambda p: make_tree(p, [
            ("file", "File", 260, "w", True), ("orig", "Original", 90, "e", False),
            ("new", "Optimized", 90, "e", False), ("saved", "Saved", 80, "e", False),
            ("dims", "Dimensions", 190, "center", False), ("status", "Status", 230, "w", False)]))
        self.tree._holder.grid(row=1, column=0, sticky="nsew", padx=12, pady=(6, 12))
        self.tree.bind("<Double-1>", self._double)

    def clear(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._results.clear()

    def add(self, r: ProcessResult) -> None:
        if r.status == "success":
            status = "Done" + (f" {r.note}" if r.note else "")
        elif r.status == "skipped":
            status = r.note or "Skipped"
        elif r.status == "cancelled":
            status = "Cancelled"
        else:
            status = r.error or "Failed"
        dims = (f"{r.orig_dims[0]}×{r.orig_dims[1]} → {r.new_dims[0]}×{r.new_dims[1]}"
                if r.orig_dims[0] else "-")
        has_size = r.status in ("success", "skipped") and r.orig_size
        iid = self.tree.insert("", "end", tags=(r.status,), values=(
            r.src.name, format_bytes(r.orig_size) if r.orig_size else "-",
            format_bytes(r.new_size) if has_size else "-",
            format_saved(r.orig_size, r.new_size) if has_size else "-", dims, status))
        self._results[iid] = r
        self.tree.see(iid)

    def selected(self) -> Optional[ProcessResult]:
        sel = self.tree.selection()
        return self._results.get(sel[0]) if sel else None

    def _double(self, _e) -> None:
        r = self.selected()
        if r and self._on_open:
            self._on_open(r)


class FileSelector(Card):
    """List of source images with add / remove / clear controls."""

    def __init__(self, master, extensions, on_change=None, on_select=None,
                 allow_folder: bool = False, title: str = "Source images"):
        super().__init__(master)
        self.extensions = {e.lower() for e in extensions}
        self.files: list = []
        self._known: set = set()
        self._on_change, self._on_select = on_change, on_select
        self.recursive = ctk.BooleanVar(value=True)
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
        card_title(head, title).pack(side="left")
        self.count = muted(head, "No files selected")
        self.count.pack(side="right")

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=14, pady=8)
        button(bar, "Add images", self.pick_files, width=110).pack(side="left", padx=(0, 6))
        if allow_folder:
            button(bar, "Add folder", self.pick_folder, "secondary", width=110).pack(side="left", padx=(0, 6))
            ctk.CTkCheckBox(bar, text="Include subfolders", variable=self.recursive, width=20,
                            font=font(12), checkbox_width=18, checkbox_height=18).pack(side="left", padx=(6, 0))
        button(bar, "Clear", self.clear, "ghost", width=60).pack(side="right")
        button(bar, "Remove", self.remove_selected, "secondary", width=80).pack(side="right", padx=6)

        self.tree = tree_with_scroll(self, lambda p: make_tree(p, [
            ("name", "File name", 240, "w", True), ("type", "Type", 60, "center", False),
            ("size", "Size", 80, "e", False)]))
        self.tree._holder.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.tree.bind("<<TreeviewSelect>>", self._selected)

    def _filetypes(self):
        pats = " ".join(f"*{e}" for e in sorted(self.extensions))
        return [("Images", pats), ("All files", "*.*")]

    def pick_files(self) -> None:
        paths = filedialog.askopenfilenames(title="Select images", filetypes=self._filetypes())
        if paths:
            self.add_paths([Path(p) for p in paths])

    def pick_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select a folder of images")
        if folder:
            self.add_paths([Path(folder)])

    def add_paths(self, paths) -> None:
        added = rejected = 0
        for p in paths:
            p = Path(p)
            candidates = (collect_images(p, self.recursive.get(), self.extensions)
                          if p.is_dir() else [p])
            for f in candidates:
                if f.suffix.lower() not in self.extensions:
                    rejected += 1
                    continue
                key = str(f)
                if key in self._known:
                    continue
                try:
                    size = f.stat().st_size
                except OSError:
                    rejected += 1
                    continue
                self._known.add(key)
                self.files.append(f)
                self.tree.insert("", "end", iid=key, values=(f.name, f.suffix.upper().lstrip("."), format_bytes(size)))
                added += 1
        self._update_count(extra=f"{rejected} unsupported skipped" if rejected else "")
        if rejected and not added:
            messagebox.showwarning("Unsupported files", "None of the selected files are supported image types")
        if self._on_change:
            self._on_change()

    def remove_selected(self) -> None:
        for iid in self.tree.selection():
            self.tree.delete(iid)
            self._known.discard(iid)
        self.files = [f for f in self.files if str(f) in self._known]
        self._update_count()
        if self._on_change:
            self._on_change()

    def clear(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.files.clear()
        self._known.clear()
        self._update_count()
        if self._on_change:
            self._on_change()

    def _update_count(self, extra: str = "") -> None:
        total = 0
        for f in self.files:
            try:
                total += f.stat().st_size
            except OSError:
                pass
        text = f"{len(self.files)} files {format_bytes(total)}" if self.files else "No files selected"
        self.count.configure(text=text + (f" {extra}" if extra else ""))

    def _selected(self, _e) -> None:
        sel = self.tree.selection()
        if sel and self._on_select:
            self._on_select(Path(sel[0]))


class QualityControl(ctk.CTkFrame):
    def __init__(self, master, default: int = 85, label: str = "Quality"):
        super().__init__(master, fg_color="transparent")
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(top, text=label, font=font(13), text_color=COLORS["text"]).pack(side="left")
        self.value_label = ctk.CTkLabel(top, text="", font=font(13, "bold"), text_color=COLORS["accent_text"])
        self.value_label.pack(side="right")
        self.slider = ctk.CTkSlider(self, from_=1, to=100, number_of_steps=99, command=self._changed,
                                    progress_color=COLORS["accent_strong"], button_color=COLORS["accent_strong"])
        self.slider.pack(fill="x", pady=(4, 0))
        self.slider.set(default)
        self._changed(default)

    def _changed(self, v) -> None:
        v = int(round(float(v)))
        hint = ("Maximum" if v >= 100 else "High" if v >= 85 else "Balanced" if v >= 65
                else "Small file" if v >= 40 else "Aggressive")
        self.value_label.configure(text=f"{v}  {hint}")

    def get(self) -> int:
        return int(round(self.slider.get()))

    def set(self, v: int) -> None:
        self.slider.set(v)
        self._changed(v)


class ResizeControls(ctk.CTkFrame):
    """Resize mode selector: original / percent / custom / preset."""

    MODES = ["Original", "Percent", "Custom", "Preset"]

    def __init__(self, master, default_mode: str = "Original"):
        super().__init__(master, fg_color="transparent")
        self.keep_aspect = ctk.BooleanVar(value=True)
        self.no_upscale = ctk.BooleanVar(value=False)
        ctk.CTkLabel(self, text="Resize", font=font(13), text_color=COLORS["text"]).pack(anchor="w")
        self.mode = ctk.CTkSegmentedButton(self, values=self.MODES, command=self._mode_changed,
                                           selected_color=COLORS["accent"], font=font(12))
        self.mode.pack(fill="x", pady=(4, 6))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="x")

        self.f_percent = ctk.CTkFrame(self.body, fg_color="transparent")
        self.percent_label = ctk.CTkLabel(self.f_percent, text="50%", font=font(13, "bold"), text_color=COLORS["accent_text"])
        self.percent_label.pack(anchor="e")
        self.percent = ctk.CTkSlider(self.f_percent, from_=5, to=200, number_of_steps=195, progress_color=COLORS["accent_strong"],
                                     button_color=COLORS["accent_strong"],
                                     command=lambda v: self.percent_label.configure(text=f"{int(round(v))}%"))
        self.percent.set(50)
        self.percent.pack(fill="x")

        self.f_custom = ctk.CTkFrame(self.body, fg_color="transparent")
        self.width_entry = ctk.CTkEntry(self.f_custom, width=90, placeholder_text="Width")
        self.height_entry = ctk.CTkEntry(self.f_custom, width=90, placeholder_text="Height")
        self.width_entry.pack(side="left")
        ctk.CTkLabel(self.f_custom, text=" by ", text_color=COLORS["muted"]).pack(side="left")
        self.height_entry.pack(side="left")
        ctk.CTkLabel(self.f_custom, text="  px", text_color=COLORS["muted"]).pack(side="left")

        self.f_preset = ctk.CTkFrame(self.body, fg_color="transparent")
        self.preset = ctk.CTkOptionMenu(self.f_preset, values=list(PRESETS), width=260, dynamic_resizing=False,
                                        fg_color=COLORS["card_alt"], button_color=COLORS["border"])
        self.preset.pack(anchor="w")

        self.opts = ctk.CTkFrame(self, fg_color="transparent")
        self.opts.pack(fill="x", pady=(6, 0))
        ctk.CTkCheckBox(self.opts, text="Keep ratio", variable=self.keep_aspect,
                        font=font(12), checkbox_width=18, checkbox_height=18).pack(anchor="w", pady=2)
        ctk.CTkCheckBox(self.opts, text="No upscaling", variable=self.no_upscale,
                        font=font(12), checkbox_width=18, checkbox_height=18).pack(anchor="w", pady=2)
        self.hint = muted(self, "", wrap=300)
        self.hint.pack(anchor="w", pady=(2, 0))
        self.mode.set(default_mode)
        self._mode_changed(default_mode)

    def _mode_changed(self, mode: str) -> None:
        frames = {"Percent": self.f_percent, "Custom": self.f_custom, "Preset": self.f_preset}
        for f in frames.values():
            f.pack_forget()
        if mode in frames:
            frames[mode].pack(fill="x")
        show = mode in ("Custom", "Preset")
        if show:
            self.opts.pack(fill="x", pady=(6, 0))
        else:
            self.opts.pack_forget()
        self.hint.configure(text="Leave one field empty to scale proportionally" if mode == "Custom" else "")

    def values(self) -> dict:
        """Return ProcessOptions kwargs for the selected mode (raises ValidationError on bad input)."""
        mode = self.mode.get()
        if mode == "Original":
            return {"resize_mode": "none"}
        if mode == "Percent":
            return {"resize_mode": "percent", "percent": float(int(round(self.percent.get())))}
        common = {"keep_aspect": self.keep_aspect.get(), "no_upscale": self.no_upscale.get()}
        if mode == "Preset":
            w, h = PRESETS[self.preset.get()]
            return {"resize_mode": "preset", "width": w, "height": h, **common}

        def parse(entry, name):
            txt = entry.get().strip()
            if not txt:
                return None
            if not txt.isdigit() or int(txt) <= 0:
                raise ValidationError(f"{name} must be a positive whole number.")
            return int(txt)

        return {"resize_mode": "custom", "width": parse(self.width_entry, "Width"),
                "height": parse(self.height_entry, "Height"), **common}
