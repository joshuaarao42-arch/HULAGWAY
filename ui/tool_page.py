from __future__ import annotations

from tkinter import filedialog, messagebox

import customtkinter as ctk

from core.batch import BatchProcessor, BatchSummary
from core.image_ops import (BACKGROUNDS, COMPRESS_INPUT, FORMAT_LABEL, LABEL_FORMAT, SUPPORTED_INPUT,
                            ProcessOptions, ProcessResult, ValidationError, make_thumbnail,
                            validate_output_dir)
from core.utils import format_bytes, open_path
from .theme import COLORS, button, font
from .widgets import (Card, FileSelector, ImageView, PageHeader, QualityControl, ResizeControls,
                      ResultsTable, card_title, muted)


class ToolPage(ctk.CTkFrame):
    title = ""
    subtitle = ""
    operation = "Batch"
    suffix = "_optimized"
    extensions = SUPPORTED_INPUT
    allow_folder = False
    show_summary_dialog = False

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._processor = None
        self._running = False
        self._token = 0
        self.grid_columnconfigure(0, weight=3, uniform="c")
        self.grid_columnconfigure(1, weight=2, uniform="c")
        self.grid_rowconfigure(1, weight=3)
        self.grid_rowconfigure(3, weight=2)

        PageHeader(self, self.title, self.subtitle).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(0, weight=1)
        left.grid_columnconfigure(0, weight=3)
        left.grid_columnconfigure(1, weight=2)
        self.selector = FileSelector(left, self.extensions, on_change=self._files_changed,
                                     on_select=self._preview, allow_folder=self.allow_folder)
        self.selector.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        pv = Card(left)
        pv.grid(row=0, column=1, sticky="nsew")
        pv.grid_rowconfigure(1, weight=1)
        pv.grid_columnconfigure(0, weight=1)
        card_title(pv, "Preview").grid(row=0, column=0, sticky="w", padx=14, pady=(10, 4))
        self.preview = ImageView(pv, "Select an image")
        self.preview.grid(row=1, column=0, sticky="nsew", padx=12)
        self.preview_info = muted(pv, "", wrap=220)
        self.preview_info.grid(row=2, column=0, sticky="ew", padx=14, pady=(6, 10))

        self.settings = ctk.CTkScrollableFrame(self, fg_color=COLORS["card"], corner_radius=14,
                                               label_text="Settings", label_font=font(14, "bold"),
                                               label_fg_color=COLORS["card"], label_text_color=COLORS["text"])
        self.settings.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
        self.build_settings(self.settings)

        bar = Card(self)
        bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=10)
        bar.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(bar, text="Save to", font=font(13), text_color=COLORS["text"]).grid(row=0, column=0, padx=(14, 8), pady=(12, 4))
        self.out_var = ctk.StringVar(value=str(app.output_dir))
        entry = ctk.CTkEntry(bar, textvariable=self.out_var, height=32)
        entry.grid(row=0, column=1, sticky="ew", pady=(12, 4))
        entry.bind("<FocusOut>", lambda _e: self._commit_output())
        button(bar, "Browse", self._browse, "secondary", width=90).grid(row=0, column=2, padx=6, pady=(12, 4))
        button(bar, "Open folder", self._open_output, "secondary", width=100).grid(row=0, column=3, padx=(0, 14), pady=(12, 4))
        self.progress = ctk.CTkProgressBar(bar, progress_color=COLORS["accent_strong"], height=10)
        self.progress.set(0)
        self.progress.grid(row=1, column=0, columnspan=2, sticky="ew", padx=(14, 8), pady=(4, 12))
        self.status = muted(bar, "Ready")
        self.status.grid(row=1, column=2, columnspan=1, sticky="w", padx=6, pady=(4, 12))
        btns = ctk.CTkFrame(bar, fg_color="transparent")
        btns.grid(row=1, column=3, padx=(0, 14), pady=(4, 12))
        self.cancel_btn = button(btns, "Cancel", self._cancel, "danger", width=70)
        self.start_btn = button(btns, "Start", self._start, "primary", width=100)
        self.start_btn.pack(side="right")

        self.table = ResultsTable(self, on_open=self._open_compare)
        self.table.grid(row=3, column=0, columnspan=2, sticky="nsew")

    def build_settings(self, parent) -> None:
        raise NotImplementedError

    def collect_options(self) -> ProcessOptions:
        raise NotImplementedError

    def workers(self):
        return None

    def label(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=font(13), text_color=COLORS["text"]).pack(anchor="w", pady=(10, 2), padx=8)

    def add_format_menu(self, parent, values, default, label="Output format", command=None):
        self.label(parent, label)
        menu = ctk.CTkOptionMenu(parent, values=values, command=command, fg_color=COLORS["card_alt"],
                                 button_color=COLORS["border"], width=200)
        menu.set(default)
        menu.pack(anchor="w", padx=8)
        return menu

    def add_check(self, parent, text, default=False):
        var = ctk.BooleanVar(value=default)
        ctk.CTkCheckBox(parent, text=text, variable=var, font=font(12), checkbox_width=18,
                        checkbox_height=18).pack(anchor="w", padx=8, pady=(8, 0))
        return var

    def add_quality(self, parent, default):
        q = QualityControl(parent, default)
        q.pack(fill="x", padx=8, pady=(12, 0))
        return q

    def add_resize(self, parent, default_mode="Original"):
        rc = ResizeControls(parent, default_mode)
        rc.pack(fill="x", padx=8, pady=(12, 0))
        return rc

    def add_background(self, parent):
        self.label(parent, "Background")
        menu = ctk.CTkOptionMenu(parent, values=list(BACKGROUNDS), fg_color=COLORS["card_alt"],
                                 button_color=COLORS["border"], width=200)
        menu.pack(anchor="w", padx=8)
        return menu

    @staticmethod
    def format_value(menu):
        v = menu.get()
        return LABEL_FORMAT.get(v)   # None for "Keep original"

    def on_show(self) -> None:
        self.out_var.set(str(self.app.output_dir))

    def _files_changed(self) -> None:
        if not self.selector.files:
            self.preview.set_image(None)
            self.preview_info.configure(text="")

    def _preview(self, path) -> None:
        self._token += 1
        token = self._token
        self.preview.message("Loading")

        def done(res):
            if token != self._token:
                return
            thumb, size, fmt = res
            self.preview.set_image(thumb)
            self.preview_info.configure(text=f"{path.name}\n{fmt} · {size[0]}×{size[1]} · {format_bytes(path.stat().st_size)}")

        def fail(exc):
            if token == self._token:
                self.preview.message("Cannot preview this file")
                self.preview_info.configure(text=str(exc))

        self.app.bridge.run_async(lambda: make_thumbnail(path, (480, 480)), done, fail)

    def _browse(self) -> None:
        folder = filedialog.askdirectory(title="Choose output folder", initialdir=self.out_var.get() or None)
        if folder:
            self.out_var.set(folder)
            self._commit_output()

    def _commit_output(self) -> None:
        try:
            self.app.set_output_dir(validate_output_dir(self.out_var.get()))
        except ValidationError:
            pass  # reported when the user starts processing

    def _open_output(self) -> None:
        try:
            folder = validate_output_dir(self.out_var.get())
        except ValidationError as exc:
            messagebox.showerror("Output folder", str(exc))
            return
        open_path(folder)

    def _open_compare(self, result: ProcessResult) -> None:
        if result.dest and result.dest.exists():
            self.app.open_compare(result.src, result.dest)
        else:
            messagebox.showinfo("Compare", "No output file exists for this row")

    def _set_running(self, running: bool) -> None:
        self._running = running
        if running:
            self.start_btn.configure(state="disabled", text="Working")
            self.cancel_btn.configure(state="normal", text="Cancel")
            self.cancel_btn.pack(side="right", padx=(0, 6), before=self.start_btn)
        else:
            self.start_btn.configure(state="normal", text="Start")
            self.cancel_btn.pack_forget()

    def _start(self) -> None:
        if self._running:
            return
        files = list(self.selector.files)
        if not files:
            messagebox.showinfo("No images", "Add one or more images first")
            return
        try:
            opts = self.collect_options()
            opts.validate()
            out_dir = validate_output_dir(self.out_var.get())
        except ValidationError as exc:
            messagebox.showerror("Please check your settings", str(exc))
            return
        self.app.set_output_dir(out_dir)
        self.table.clear()
        self.progress.set(0)
        self.status.configure(text=f"0 / {len(files)}", text_color=COLORS["muted"])
        self._set_running(True)
        post = self.app.bridge.post
        self._processor = BatchProcessor(self.workers())
        self._processor.start(files, out_dir, opts,
                              on_progress=lambda d, t, r: post(self._on_progress, d, t, r),
                              on_finished=lambda s: post(self._on_finished, s))

    def _cancel(self) -> None:
        if self._processor:
            self._processor.cancel()
        self.cancel_btn.configure(state="disabled", text="Stopping")

    def _on_progress(self, done: int, total: int, result: ProcessResult) -> None:
        self.table.add(result)
        self.progress.set(done / total)
        self.status.configure(text=f"{done} / {total}")

    def _on_finished(self, s: BatchSummary) -> None:
        self._set_running(False)
        self.app.db.add_results(self.operation, s.results)
        parts = [f"{s.succeeded} done"]
        if s.skipped:
            parts.append(f"{s.skipped} skipped")
        if s.failed:
            parts.append(f"{s.failed} failed")
        if s.cancelled:
            parts.append(f"{s.cancelled} cancelled")
        msg = ", ".join(parts)
        if s.succeeded:
            msg += f" · saved {format_bytes(s.saved_bytes)} ({s.saved_pct:.1f}%)"
        color = COLORS["danger"] if s.failed else COLORS["success"]
        self.status.configure(text=msg, text_color=color)
        if self.show_summary_dialog:
            SummaryDialog(self.winfo_toplevel(), s, self.out_var.get())


class SummaryDialog(ctk.CTkToplevel):
    def __init__(self, master, s: BatchSummary, out_dir: str):
        super().__init__(master)
        self.title("Batch summary")
        self.geometry("520x520")
        self.configure(fg_color=COLORS["bg"])
        self.transient(master)
        head = "Batch cancelled" if s.was_cancelled else "Batch complete"
        ctk.CTkLabel(self, text=head, font=font(22, "bold")).pack(anchor="w", padx=22, pady=(20, 8))
        grid = Card(self)
        grid.pack(fill="x", padx=22)
        rows = [("Images in batch", str(s.total)), ("Processed", str(s.succeeded)),
                ("Skipped already optimal", str(s.skipped)), ("Failed", str(s.failed)),
                ("Original size", format_bytes(s.orig_bytes)), ("New size", format_bytes(s.new_bytes)),
                ("Space saved", f"{format_bytes(s.saved_bytes)} ({s.saved_pct:.1f}%)"),
                ("Time taken", f"{s.elapsed:.1f} s")]
        for i, (k, v) in enumerate(rows):
            ctk.CTkLabel(grid, text=k, text_color=COLORS["muted"], font=font(13)).grid(row=i, column=0, sticky="w", padx=16, pady=3)
            ctk.CTkLabel(grid, text=v, font=font(13, "bold")).grid(row=i, column=1, sticky="e", padx=16, pady=3)
        grid.grid_columnconfigure(1, weight=1)
        problems = [r for r in s.results if r.status == "failed"]
        ctk.CTkLabel(self, text="Errors" if problems else "No errors", font=font(14, "bold")
                     ).pack(anchor="w", padx=22, pady=(14, 4))
        box = ctk.CTkTextbox(self, height=130, fg_color=COLORS["card"], font=font(12))
        box.pack(fill="both", expand=True, padx=22)
        box.insert("end", "\n".join(f"{r.src.name} {r.error}" for r in problems) or "All files were handled without errors")
        box.configure(state="disabled")
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=16)
        button(row, "Open output folder", lambda: open_path(out_dir), width=150).pack(side="left")
        button(row, "Close", self.destroy, "secondary", width=90).pack(side="right")


class CompressorPage(ToolPage):
    title = "Image Compressor"
    subtitle = "Smaller files"
    operation = "Compress"
    suffix = "_compressed"
    extensions = COMPRESS_INPUT

    def build_settings(self, p):
        self.fmt = self.add_format_menu(p, ["Keep original", "JPG", "PNG", "WEBP"], "Keep original")
        self.quality = self.add_quality(p, 80)
        self.png_lossy = self.add_check(p, "Lossy PNG")
        self.strip = self.add_check(p, "Strip metadata")

    def collect_options(self):
        return ProcessOptions(output_format=self.format_value(self.fmt), quality=self.quality.get(),
                              png_lossy=self.png_lossy.get(), strip_metadata=self.strip.get(),
                              skip_if_larger=True, suffix=self.suffix)


class ConverterPage(ToolPage):
    title = "Format Converter"
    subtitle = "Change format"
    operation = "Convert"
    suffix = "_converted"

    def build_settings(self, p):
        self.fmt = self.add_format_menu(p, [FORMAT_LABEL[k] for k in ("PNG", "JPEG", "WEBP", "BMP", "TIFF")],
                                        "WEBP", "Convert to", command=self._fmt_changed)
        self.note = muted(p, "", wrap=300)
        self.note.pack(anchor="w", padx=8, pady=(6, 0))
        self.quality = self.add_quality(p, 90)
        self.bg = self.add_background(p)
        self.strip = self.add_check(p, "Strip metadata")
        self._fmt_changed("WEBP")

    def _fmt_changed(self, value):
        if value in ("JPG", "BMP"):
            self.note.configure(text=f"{value} no transparency")
        else:
            self.note.configure(text=f"{value} transparency kept")

    def collect_options(self):
        return ProcessOptions(output_format=self.format_value(self.fmt), quality=self.quality.get(),
                              background=BACKGROUNDS[self.bg.get()], strip_metadata=self.strip.get(),
                              suffix=self.suffix)


class ResizerPage(ToolPage):
    title = "Image Resizer"
    subtitle = "Resize images"
    operation = "Resize"
    suffix = "_resized"

    def build_settings(self, p):
        self.resize = self.add_resize(p, "Percent")
        self.fmt = self.add_format_menu(p, ["Keep original"] + [FORMAT_LABEL[k] for k in ("PNG", "JPEG", "WEBP", "BMP", "TIFF")],
                                        "Keep original")
        self.quality = self.add_quality(p, 90)
        self.bg = self.add_background(p)
        self.strip = self.add_check(p, "Strip metadata")

    def collect_options(self):
        return ProcessOptions(output_format=self.format_value(self.fmt), quality=self.quality.get(),
                              background=BACKGROUNDS[self.bg.get()], strip_metadata=self.strip.get(),
                              suffix=self.suffix, **self.resize.values())


class BatchPage(ToolPage):
    title = "Batch Processor"
    subtitle = "Many images, one run"
    operation = "Batch"
    suffix = "_batch"
    allow_folder = True
    show_summary_dialog = True

    def build_settings(self, p):
        self.fmt = self.add_format_menu(p, ["Keep original"] + [FORMAT_LABEL[k] for k in ("JPEG", "PNG", "WEBP", "BMP", "TIFF")],
                                        "Keep original")
        self.quality = self.add_quality(p, 80)
        self.png_lossy = self.add_check(p, "Lossy PNG")
        self.resize = self.add_resize(p, "Original")
        self.bg = self.add_background(p)
        self.strip = self.add_check(p, "Strip metadata")
        self.skip = self.add_check(p, "Skip unchanged", True)
        self.label(p, "Parallel workers")
        self.workers_menu = ctk.CTkOptionMenu(p, values=["Auto", "1", "2", "4", "8"], fg_color=COLORS["card_alt"],
                                              button_color=COLORS["border"], width=120)
        self.workers_menu.pack(anchor="w", padx=8, pady=(0, 10))

    def workers(self):
        v = self.workers_menu.get()
        return None if v == "Auto" else int(v)

    def collect_options(self):
        return ProcessOptions(output_format=self.format_value(self.fmt), quality=self.quality.get(),
                              png_lossy=self.png_lossy.get(), background=BACKGROUNDS[self.bg.get()],
                              strip_metadata=self.strip.get(), skip_if_larger=self.skip.get(),
                              suffix=self.suffix, **self.resize.values())
