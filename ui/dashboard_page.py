from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

from core.utils import format_bytes, format_saved
from .theme import COLORS, button, font
from .widgets import Card, PageHeader, StatCard, card_title, make_tree, muted, tree_with_scroll


class DashboardPage(ctk.CTkFrame):
    ACTIONS = [("Compress images", "compressor", "primary"), ("Convert format", "converter", "secondary"),
               ("Resize images", "resizer", "secondary"), ("Batch process", "batch", "secondary"),
               ("Compare", "compare", "secondary"), ("Inspect", "inspector", "secondary")]

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="s")
        self.grid_rowconfigure(3, weight=1)
        PageHeader(self, "Dashboard", "Overview").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))
        self.cards = {
            "saved": StatCard(self, "Storage saved", "0 B", COLORS["success"]),
            "avg": StatCard(self, "Average reduction", "0%", COLORS["accent_text"]),
            "ok": StatCard(self, "Images processed", "0", COLORS["text"]),
            "failed": StatCard(self, "Failed", "0", COLORS["danger"]),
        }
        for i, c in enumerate(self.cards.values()):
            c.grid(row=1, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0 if i == 3 else 6))

        qa = Card(self)
        qa.grid(row=2, column=0, columnspan=4, sticky="ew", pady=12)
        card_title(qa, "Quick actions").pack(anchor="w", padx=16, pady=(12, 6))
        row = ctk.CTkFrame(qa, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 14))
        for text, page, kind in self.ACTIONS:
            button(row, text, lambda p=page: app.navigate(p), kind, width=140).pack(side="left", padx=4)

        recent = Card(self)
        recent.grid(row=3, column=0, columnspan=3, sticky="nsew", padx=(0, 6))
        recent.grid_rowconfigure(1, weight=1)
        recent.grid_columnconfigure(0, weight=1)
        card_title(recent, "Recent operations").grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))
        self.tree = tree_with_scroll(recent, lambda p: make_tree(p, [
            ("time", "When", 140, "w", False), ("op", "Operation", 90, "w", False),
            ("file", "File", 220, "w", True), ("saved", "Saved", 70, "e", False),
            ("status", "Status", 80, "w", False)], "browse"))
        self.tree._holder.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        act = Card(self)
        act.grid(row=3, column=3, sticky="nsew", padx=(6, 0))
        card_title(act, "Activity").pack(anchor="w", padx=16, pady=(12, 6))
        self.activity = ctk.CTkFrame(act, fg_color="transparent")
        self.activity.pack(fill="x", padx=16)

    def on_show(self) -> None:
        db = self.app.db
        s = db.stats()
        self.cards["saved"].set(format_bytes(s["saved"]))
        self.cards["avg"].set(f"{s['avg_pct']:.1f}%")
        self.cards["ok"].set(str(s["ok"]))
        self.cards["failed"].set(str(s["failed"]))

        self.tree.delete(*self.tree.get_children())
        for r in db.recent(12):
            ok = r["status"] == "success"
            self.tree.insert("", "end", tags=(r["status"],), values=(
                r["timestamp"], r["operation"], Path(r["source_path"]).name,
                format_saved(r["orig_size"], r["new_size"]) if ok else "-", r["status"].title()))

        for w in self.activity.winfo_children():
            w.destroy()
        rows = db.breakdown()
        if not rows:
            muted(self.activity, "No activity", wrap=220).pack(anchor="w")
        top = max((r["n"] for r in rows), default=1)
        for r in rows:
            line = ctk.CTkFrame(self.activity, fg_color="transparent")
            line.pack(fill="x", pady=4)
            ctk.CTkLabel(line, text=r["operation"], font=font(13)).pack(side="left")
            ctk.CTkLabel(line, text=f"{r['n']}  ·  {format_bytes(r['saved'])}", font=font(12),
                         text_color=COLORS["muted"]).pack(side="right")
            bar = ctk.CTkProgressBar(self.activity, height=6, progress_color=COLORS["accent_strong"])
            bar.set(r["n"] / top)
            bar.pack(fill="x")
