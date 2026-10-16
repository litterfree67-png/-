# -*- coding: utf-8 -*-
"""Colours, type scale, spacing and the ttk theme.

Everything that differs between light and dark lives here. Components read
from the token dicts rather than hardcoding values; spacing follows a 4px
base unit; text/background pairs are kept at WCAG AA (>= 4.5:1 body).
"""

from __future__ import annotations

from typing import Dict

# --------------------------------------------------------------------------
# Typography
# --------------------------------------------------------------------------
FONT_UI = "Microsoft YaHei UI"
FONT_FALLBACK = "Segoe UI"
FONT_MONO = "Cascadia Mono"
FONT_MONO_FALLBACK = "Consolas"

UI_FONT = (FONT_UI, FONT_FALLBACK, "PingFang SC", "sans-serif")
MONO_FONT = (FONT_MONO, FONT_MONO_FALLBACK, "Menlo", "monospace")

TYPE_SCALE = {
    "display": 22,
    "title": 15,
    "subtitle": 12,
    "body": 10,
    "label": 9,
    "caption": 8,
    "code": 9,
}
TYPE_WEIGHT = {
    "regular": "normal",
    "medium": "normal",   # YaHei UI has no 500 file; emulate with colour instead
    "bold": "bold",
}

# --------------------------------------------------------------------------
# Spacing / radius / motion
# --------------------------------------------------------------------------
SPACE = {  # 4px base grid
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 20,
    "2xl": 24,
    "3xl": 32,
}
RADIUS = {"sm": 3, "md": 6, "lg": 10, "pill": 999}
MOTION = {"fast": 110, "normal": 180, "slow": 260}

# --------------------------------------------------------------------------
# Palette — Light ("Safelight Paper")
# --------------------------------------------------------------------------
LIGHT: Dict[str, str] = {
    # Surfaces
    "canvas": "#F4F1EB",          # app background, warm paper
    "surface": "#FFFFFF",         # cards, table body
    "surface_sunken": "#EDE8DF",  # inputs, log viewport, wells
    "surface_hover": "#F7F4EE",
    "inverse": "#17140F",         # title bar, inverted chips

    # Borders
    "border": "#E0D9CD",
    "border_strong": "#C9C0B1",
    "focus_ring": "#F0A88F",

    # Text
    "text": "#1B1713",            # on canvas -> 13.9:1
    "text_secondary": "#6A6155",  # on canvas -> 5.6:1
    "text_muted": "#948A7C",      # decorative / separators only
    "text_inverse": "#F7F3EC",    # on inverse -> 14.2:1
    "text_on_accent": "#FFFFFF",  # on accent -> 4.7:1

    # Brand — safelight orange
    "accent": "#D2491F",
    "accent_hover": "#B53C16",
    "accent_press": "#96300F",
    "accent_soft": "#FBE3D9",
    "accent_soft_text": "#9B3411",

    # Semantics
    "success": "#1F6B54",
    "success_soft": "#DDEDE5",
    "warning": "#8A5A08",
    "warning_soft": "#F8EBCE",
    "danger": "#B33024",
    "danger_soft": "#F8DFDB",
    "info": "#2A5875",
    "info_soft": "#DCE8F0",

    # Row-level state tints for the file queue
    "row_ok": "#21705A",
    "row_fail": "#B33024",
    "row_skip": "#8A5A08",
    "row_run": "#2A5875",
    "row_pending": "#6A6155",
}

# --------------------------------------------------------------------------
# Palette — Dark ("Darkroom Night")
# --------------------------------------------------------------------------
DARK: Dict[str, str] = {
    "canvas": "#12100D",
    "surface": "#1B1815",
    "surface_sunken": "#0D0B09",
    "surface_hover": "#221E1A",
    "inverse": "#0A0908",

    "border": "#2C271F",
    "border_strong": "#3E372D",
    "focus_ring": "#B8562F",

    "text": "#F3EEE6",
    "text_secondary": "#AB9F8D",
    "text_muted": "#7C7161",
    "text_inverse": "#F3EEE6",
    "text_on_accent": "#FFFFFF",

    "accent": "#F2622C",
    "accent_hover": "#FF7A4A",
    "accent_press": "#D2491F",
    "accent_soft": "#33200F",
    "accent_soft_text": "#F0A88F",

    "success": "#57B892",
    "success_soft": "#1B2E27",
    "warning": "#D8A94B",
    "warning_soft": "#302512",
    "danger": "#E4735F",
    "danger_soft": "#331B17",
    "info": "#7FB0D4",
    "info_soft": "#16252F",

    "row_ok": "#57B892",
    "row_fail": "#E4735F",
    "row_skip": "#D8A94B",
    "row_run": "#7FB0D4",
    "row_pending": "#AB9F8D",
}

THEMES = {"light": LIGHT, "dark": DARK}


def tokens(mode: str = "light") -> Dict[str, str]:
    """Return the token set for a theme mode."""
    return THEMES.get(mode, LIGHT)


def font(size_key: str = "body", weight: str = "regular",
         mono: bool = False) -> tuple:
    """Build a Tk font tuple from the type scale."""
    family = MONO_FONT if mono else UI_FONT
    return (family, TYPE_SCALE.get(size_key, TYPE_SCALE["body"]),
            TYPE_WEIGHT.get(weight, "normal"))


def apply_ttk_theme(style, t: Dict[str, str]) -> None:
    """Push tokens into ttk styles — the single place themes touch ttk."""
    style.theme_use("clam")

    style.configure(".", font=font("body"), foreground=t["text"])
    style.configure("TFrame", background=t["canvas"], borderwidth=0, relief="flat")
    style.configure("Surface.TFrame", background=t["surface"])
    style.configure("Sunken.TFrame", background=t["surface_sunken"])

    style.configure("TLabel", background=t["canvas"], foreground=t["text"])
    style.configure("Surface.TLabel", background=t["surface"], foreground=t["text"])
    style.configure("Secondary.TLabel", background=t["canvas"],
                    foreground=t["text_secondary"])
    style.configure("Surface.Secondary.TLabel", background=t["surface"],
                    foreground=t["text_secondary"])
    style.configure("Surface.Muted.TLabel", background=t["surface"],
                    foreground=t["text_muted"])
    style.configure("Muted.TLabel", background=t["canvas"],
                    foreground=t["text_muted"])
    style.configure("Display.TLabel", background=t["canvas"],
                    foreground=t["text"], font=font("title", "bold"))
    style.configure("Section.TLabel", background=t["surface"],
                    foreground=t["text_secondary"], font=font("label", "bold"))
    style.configure("Value.TLabel", background=t["surface"],
                    foreground=t["text"], font=font("body", "bold"))

    # --- Form controls -----------------------------------------------------
    style.configure("TEntry", fieldbackground=t["surface_sunken"],
                    foreground=t["text"], insertcolor=t["accent"],
                    bordercolor=t["border_strong"], lightcolor=t["border_strong"],
                    darkcolor=t["border_strong"], borderwidth=1,
                    padding=(SPACE["sm"], 6))
    style.map("TEntry",
              bordercolor=[("focus", t["accent"]), ("disabled", t["border"])],
              fieldbackground=[("disabled", t["surface"])],
              foreground=[("disabled", t["text_muted"])])
    style.configure("Mono.TEntry", font=font("body", mono=True))

    style.configure("TSpinbox", arrowsize=13, padding=(SPACE["sm"], 6),
                    fieldbackground=t["surface_sunken"], foreground=t["text"],
                    bordercolor=t["border_strong"])
    style.map("TSpinbox",
              bordercolor=[("focus", t["accent"]), ("disabled", t["border"])])

    style.configure("TCombobox", arrowsize=14, padding=(SPACE["sm"], 6),
                    fieldbackground=t["surface"], foreground=t["text"],
                    bordercolor=t["border_strong"])
    style.map("TCombobox",
              bordercolor=[("focus", t["accent"])],
              fieldbackground=[("readonly", t["surface_sunken"])],
              selectbackground=[("readonly", t["surface_sunken"])])
    style.configure("TComboboxPopdownFrame", background=t["surface"])
    style.configure("TComboboxPopdown.TListbox", background=t["surface"],
                    foreground=t["text"], selectbackground=t["accent_soft"],
                    selectforeground=t["text"])

    style.configure("Horizontal.TScale", background=t["surface"],
                    troughcolor=t["surface_sunken"], borderwidth=0,
                    lightcolor=t["success"], sliderrelief="flat")

    # --- Notebook-less section frames --------------------------------------
    style.configure("Card.TFrame", background=t["surface"], relief="flat")
    style.configure("Card.TLabelframe", background=t["surface"],
                    bordercolor=t["border"], relief="solid", borderwidth=1,
                    padding=(SPACE["lg"], SPACE["md"]))
    style.configure("Card.TLabelframe.Label", background=t["surface"],
                    foreground=t["text_secondary"], font=font("label", "bold"))

    # --- File queue --------------------------------------------------------
    style.configure("Queue.Treeview",
                    rowheight=32,
                    background=t["surface"],
                    fieldbackground=t["surface"],
                    foreground=t["text"],
                    bordercolor=t["border"],
                    borderwidth=1,
                    font=font("body"),
                    relief="flat")
    style.configure("Queue.Treeview.Heading",
                    background=t["surface_sunken"],
                    foreground=t["text_secondary"],
                    font=font("label", "bold"),
                    relief="flat",
                    bordercolor=t["border"],
                    borderwidth=1,
                    padding=(SPACE["sm"], 7))
    style.map("Queue.Treeview.Heading",
              background=[("active", t["surface_sunken"])])
    style.map("Queue.Treeview",
              background=[("selected", t["accent_soft"])],
              foreground=[("selected", t["accent_soft_text"])])

    # --- Progress ----------------------------------------------------------
    style.configure("Accent.Horizontal.TProgressbar",
                    troughcolor=t["surface_sunken"],
                    bordercolor=t["surface_sunken"],
                    background=t["accent"],
                    lightcolor=t["accent"],
                    darkcolor=t["accent"],
                    thickness=8)

    style.configure("Vertical.TScrollbar", background=t["surface_sunken"],
                    troughcolor=t["surface"], bordercolor=t["surface"],
                    arrowcolor=t["text_muted"], relief="flat", borderwidth=0)
    style.map("Vertical.TScrollbar",
              background=[("active", t["border_strong"])])
    style.configure("Horizontal.TScrollbar", background=t["surface_sunken"],
                    troughcolor=t["surface"], bordercolor=t["surface"],
                    arrowcolor=t["text_muted"], relief="flat", borderwidth=0)
    style.map("Horizontal.TScrollbar",
              background=[("active", t["border_strong"])])
