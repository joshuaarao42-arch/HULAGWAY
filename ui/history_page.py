from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core.utils import format_bytes, format_saved, open_path, reveal_in_folder
from .theme import COLORS, button, font
from .widgets import Card, PageHeader, card_title, make_tree, muted, tree_with_scroll


class HistoryPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.rows: dict = {}
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        PageHeader(self, "Processing History", "Saved locally").grid(
            row=0, column=0, sticky="w", pady=(0, 12))

        bar = Card(self)
        bar.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.search = ctk.CTkEntry(bar, placeholder_text="Search by file name or path", width=280)
        self.search.pack(side="left", padx=(14, 8), pady=12)
        self.search.bind("<KeyRelease>", lambda _e: self.refresh())
        self.op = ctk.CTkOptionMenu(bar, values=["All", "Compress", "Convert", "Resize", "Batch"], width=120,
                                    command=lambda _v: self.refresh(), fg_color=COLORS["card_alt"], button_color=COLORS["border"])
        self.op.pack(side="left", padx=4)
        self.status = ctk.CTkOptionMenu(bar, values=["All", "Success", "Skipped", "Failed"], width=110,
                                        command=lambda _v: self.refresh(), fg_color=COLORS["card_alt"], button_color=COLORS["border"])
        self.status.pack(side="left", padx=4)
        button(bar, "Clear all", self.clear_all, "danger", width=90).pack(side="right", padx=14)
        button(bar, "Export CSV", self.export, "secondary", width=100).pack(side="right")

        self.tree = tree_with_scroll(self, lambda p: make_tree(p, [
            ("time", "Date", 150, "w", False), ("op", "Operation", 90, "w", False),
            ("file", "File", 260, "w", True), ("fmt", "Format", 110, "center", False),
            ("orig", "Original", 85, "e", False), ("new", "New", 85, "e", False),
            ("saved", "Saved", 70, "e", False), ("status", "Status", 80, "w", False)], "browse"))
        self.tree._holder.grid(row=2, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._selected)
        self.tree.bind("<Double-1>", lambda _e: self.compare())

        det = Card(self)
        det.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self.detail = ctk.CTkLabel(det, text="Select an entry to see its details", justify="left", anchor="w",
                                   font=font(12), text_color=COLORS["muted"], wraplength=700)
        self.detail.pack(side="left", fill="x", expand=True, padx=14, pady=12)
        for text, cmd, kind in (("Delete", self.delete, "danger"), ("Open folder", self.open_folder, "secondary"),
                                ("Compare", self.compare, "primary")):
            button(det, text, cmd, kind, width=100).pack(side="right", padx=(0, 8), pady=12)

    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.rows.clear()
        for r in self.app.db.search(self.search.get(), self.op.get(), self.status.get()):
            ok = r["status"] == "success"
            fmt = f"{r['src_format'] or '-'} → {r['out_format']}" if r["out_format"] else (r["src_format"] or "-")
            iid = self.tree.insert("", "end", tags=(r["status"],), values=(
                r["timestamp"], r["operation"], Path(r["source_path"]).name, fmt,
                format_bytes(r["orig_size"]) if r["orig_size"] else "-",
                format_bytes(r["new_size"]) if ok else "-",
                format_saved(r["orig_size"], r["new_size"]) if ok else "-", r["status"].title()))
            self.rows[iid] = r
        self.detail.configure(text=f"{len(self.rows)} entries shown" if self.rows else "No history yet")

    def _current(self):
        sel = self.tree.selection()
        return self.rows.get(sel[0]) if sel else None

    def _selected(self, _e) -> None:
        r = self._current()
        if not r:
            return
        lines = [f"Source  {r['source_path']}", f"Output  {r['output_path'] or 'none'}",
                 f"Size  {r['orig_dims'] or 'unknown'}  {r['new_dims'] or 'unknown'}"]
        if r["message"]:
            lines.append(f"Note  {r['message']}")
        self.detail.configure(text="\n".join(lines), text_color=COLORS["text"])

    def compare(self) -> None:
        r = self._current()
        if not r:
            return
        out = Path(r["output_path"]) if r["output_path"] else None
        src = Path(r["source_path"])
        if out and out.exists() and src.exists():
            self.app.open_compare(src, out)
        else:
            messagebox.showinfo("Compare", "The original or the output file no longer exists")

    def open_folder(self) -> None:
        r = self._current()
        if not r:
            return
        target = Path(r["output_path"] or r["source_path"])
        if target.exists():
            reveal_in_folder(target)
        elif target.parent.exists():
            open_path(target.parent)
        else:
            messagebox.showinfo("Open folder", "That location no longer exists")

    def delete(self) -> None:
        r = self._current()
        if r:
            self.app.db.delete(r["id"])
            self.refresh()

    def clear_all(self) -> None:
        if messagebox.askyesno("Clear history", "Delete all history entries Your image files are not touched"):
            self.app.db.clear()
            self.refresh()

    def export(self) -> None:
        dest = filedialog.asksaveasfilename(title="Export history", defaultextension=".csv",
                                            initialfile="hulagway_history.csv", filetypes=[("CSV", "*.csv")])
        if dest:
            try:
                n = self.app.db.export_csv(Path(dest))
                messagebox.showinfo("Exported", f"{n} entries exported")
            except OSError as exc:
                messagebox.showerror("Export failed", str(exc))
