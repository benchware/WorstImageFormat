"""WIMF Studio design tokens: spacing, sizes, typography and the two Sun Valley palettes.

Every layout value lives here so the whole UI can be retuned from one place.
Visual language follows Fluent / WinUI conventions (the same ones Sun Valley and
GoodbyeDPI UI are built on): soft card strokes, roomy gutters, one accent color.
Design-language credit: GoodbyeDPI UI by Storik4pro (Apache-2.0).
"""

SPACING = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 20,
    "xxl": 24,
}

SIZES = {
    "window_min": (1000, 640),
    "window_default": (1280, 800),
    "content_max": 1040,
    "app_bar": 48,
    "logo_small": 26,
    "logo_medium": 30,
    "dialog_logo": 26,
    "resize_grip": 3,
}

FONT_FAMILY = "Segoe UI"
FONTS = {
    "header_title": (FONT_FAMILY, 12, "bold"),
    "subtitle": (FONT_FAMILY, 8),
    "heading": (FONT_FAMILY, 10, "bold"),
    "card_title": (FONT_FAMILY, 8, "bold"),
    "body": (FONT_FAMILY, 9),
    "body_strong": (FONT_FAMILY, 9, "bold"),
    "mono": ("Consolas", 9),
}

PALETTES = {
    "dark": {
        "label": "Dark",
        "dark": True,
        "pane_bg": "#202020",
        "surface": "#2b2b2b",
        "border": "#3f3f3f",
        "fg": "#f3f3f3",
        "muted": "#a6a6a6",
        "accent": "#4cc2ff",
        "accent_text": "#082032",
        "tip_bg": "#1b1b1b",
        "tip_fg": "#e4e4e4",
        "close_hover": "#e81123",
    },
    "light": {
        "label": "Light",
        "dark": False,
        "pane_bg": "#f3f3f3",
        "surface": "#ffffff",
        "border": "#dddddd",
        "fg": "#1a1a1a",
        "muted": "#5d5d5d",
        "accent": "#005fb8",
        "accent_text": "#ffffff",
        "tip_bg": "#fffce8",
        "tip_fg": "#333333",
        "close_hover": "#e81123",
    },
}

THEME_NAMES = ("dark", "light")


def mix_hex(first, second, ratio):
    """Blend two '#rrggbb' colors; ratio is the weight of ``second``."""
    a, b = first.lstrip("#"), second.lstrip("#")
    return "#" + "".join(
        f"{round(int(a[i : i + 2], 16) * (1 - ratio) + int(b[i : i + 2], 16) * ratio):02x}" for i in (0, 2, 4)
    )


def resolve(name):
    """Return a fully resolved palette for ``name`` ('dark' or 'light')."""
    if name not in PALETTES:
        name = "dark"
    palette = dict(PALETTES[name])
    palette["border_soft"] = mix_hex(palette["border"], palette["surface"], 0.55)
    palette["hover"] = mix_hex(palette["surface"], palette["border"], 0.6)
    palette["menu_hover"] = mix_hex(palette["surface"], palette["border"], 0.5)
    return palette
