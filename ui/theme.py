from __future__ import annotations

from tkinter import ttk

import customtkinter as ctk

LIGHT_COLORS = {
    "bg": "#FFF9E3", "sidebar": "#FFEDA8", "card": "#FFF6C1", "card_alt": "#FFFDF3",
    "border": "#EBCF73", "track": "#F0DC8C",
    "accent": "#FFE18A", "accent_hover": "#FFD464", "accent_dim": "#FBE7A1",
    "accent_strong": "#EDB92E", "accent_text": "#8A6100", "on_accent": "#4A3A12",
    "success": "#2F8F5B", "warning": "#B7791F", "danger": "#C0392B",
    "text": "#4A3A12", "muted": "#7A6A38",
}
NIGHT_COLORS = {
    "bg": "#090B1A", "sidebar": "#12152D", "card": "#181D3B", "card_alt": "#10142C",
    "border": "#303867", "track": "#292F59",
    "accent": "#C7B8FF", "accent_hover": "#DDD4FF", "accent_dim": "#3A3765",
    "accent_strong": "#8D7CE8", "accent_text": "#C7B8FF", "on_accent": "#17132B",
    "success": "#72D6A0", "warning": "#F2C66D", "danger": "#F27D7D",
    "text": "#F4F1FF", "muted": "#A9AED0",
}
COLORS = dict(NIGHT_COLORS)
CURRENT_MODE = "dark"
RADIUS = 14
PAD = 16
_fonts: dict = {}
FONT_FAMILY = "Aptos"
DISPLAY_FAMILY = "Aptos Display"

_WIDGET_DEFAULTS = {
    "CTkLabel": {"text_color": "text"},
    "CTkCheckBox": {"fg_color": "accent_strong", "hover_color": "accent_hover", "border_color": "border",
                    "checkmark_color": "on_accent", "text_color": "text"},
    "CTkEntry": {"fg_color": "card_alt", "border_color": "border", "text_color": "text",
                 "placeholder_text_color": "muted"},
    "CTkOptionMenu": {"fg_color": "card_alt", "button_color": "accent_dim", "button_hover_color": "accent_hover",
                      "text_color": "text", "dropdown_fg_color": "card_alt",
                      "dropdown_hover_color": "accent_dim", "dropdown_text_color": "text"},
    "CTkSlider": {"fg_color": "track", "progress_color": "accent_strong", "button_color": "accent_strong",
                  "button_hover_color": "accent_text"},
    "CTkProgressBar": {"fg_color": "track", "progress_color": "accent_strong"},
    "CTkSegmentedButton": {"fg_color": "track", "selected_color": "accent", "selected_hover_color": "accent_hover",
                           "unselected_color": "track", "unselected_hover_color": "accent_dim", "text_color": "text"},
    "CTkTextbox": {"fg_color": "card", "text_color": "text"},
    "CTkScrollbar": {"button_color": "border", "button_hover_color": "accent_strong"},
    "CTkSwitch": {"fg_color": "track", "progress_color": "accent_strong", "button_color": "card_alt",
                  "button_hover_color": "accent_hover", "text_color": "text"},
}


def set_mode(mode: str) -> None:
    """Switch between the warm light palette and the violet night palette."""
    global CURRENT_MODE
    CURRENT_MODE = "light" if mode == "light" else "dark"
    COLORS.clear()
    COLORS.update(LIGHT_COLORS if CURRENT_MODE == "light" else NIGHT_COLORS)
    ctk.set_appearance_mode(CURRENT_MODE)
    _fonts.clear()


def setup_theme() -> None:
    set_mode(CURRENT_MODE)
    ctk.set_default_color_theme("blue")
    try:
        theme = ctk.ThemeManager.theme
        for widget, values in _WIDGET_DEFAULTS.items():
            for key, colour in values.items():
                if widget in theme and key in theme[widget] and colour in COLORS:
                    c = COLORS[colour]
                    theme[widget][key] = [c, c]
    except Exception:
        pass


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    """Cached app font."""
    key = (size, weight)
    if key not in _fonts:
        family = DISPLAY_FAMILY if size >= 18 else FONT_FAMILY
        _fonts[key] = ctk.CTkFont(family=family, size=size, weight=weight)
    return _fonts[key]


def style_ttk(root) -> None:
    """Styling for the ttk Treeview/Scrollbar widgets used for tables."""
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure("PP.Treeview", background=COLORS["card_alt"], fieldbackground=COLORS["card_alt"],
                foreground=COLORS["text"], borderwidth=0, rowheight=30, font=("Segoe UI", 10))
    s.map("PP.Treeview", background=[("selected", COLORS["accent_dim"])],
          foreground=[("selected", COLORS["text"])])
    s.configure("PP.Treeview.Heading", background=COLORS["card"], foreground=COLORS["muted"],
                relief="flat", borderwidth=0, font=("Segoe UI", 9, "bold"), padding=(8, 6))
    s.map("PP.Treeview.Heading", background=[("active", COLORS["card"])])
    s.layout("PP.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    s.configure("PP.Vertical.TScrollbar", background=COLORS["border"], troughcolor=COLORS["card_alt"],
                bordercolor=COLORS["card_alt"], arrowcolor=COLORS["muted"], relief="flat")
    s.map("PP.Vertical.TScrollbar", background=[("active", COLORS["accent_strong"])])


def button(parent, text, command, kind: str = "primary", width: int = 120, **kw) -> ctk.CTkButton:
    palette = {
        "primary": (COLORS["accent"], COLORS["accent_hover"], COLORS["on_accent"]),
        "secondary": (COLORS["card_alt"], COLORS["accent_dim"], COLORS["text"]),
        "danger": ("#D9644F", "#C24E3A", "#ffffff"),
        "ghost": ("transparent", COLORS["accent_dim"], COLORS["text"]),
    }
    fg, hover, txt = palette[kind]
    return ctk.CTkButton(parent, text=text, command=command, width=width, height=34, corner_radius=10,
                         fg_color=fg, hover_color=hover, text_color=txt, font=font(13, "bold"), **kw)
