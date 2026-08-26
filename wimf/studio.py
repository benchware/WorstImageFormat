"""WIMF Studio: lightweight Tkinter encoder, inspector, and codec lab."""

import argparse
import ctypes
import json
import math
import random
import sys
import tkinter as tk
import webbrowser
from collections import Counter
from pathlib import Path
from tkinter import filedialog, ttk

import numpy as np
from PIL import Image, ImageEnhance, ImageTk

import wimf

from . import hybrid as _hybrid
from .diagnostics import AREAS, corrupt, diagnose, unsafe_preview
from .studio_assets import logo_image
from .studio_model import EncodeSettings, JobController, StudioDocument
from .studio_settings import (
    CODECS,
    CORE_MODES,
    DEFAULTS,
    QUALITY_PRESETS,
    SETTINGS_FILE,
    TIPS,
    StudioSettings,
)
from .studio_theme import FONTS, PALETTES, SIZES, SPACING, THEME_NAMES, mix_hex

try:
    import sv_ttk  # modern flat dark/light ttk theme (pip install sv-ttk)
except ImportError:
    sv_ttk = None

MODE_COLORS = {"raw": "#9aa0a6", "predictive": "#34a853", "palette": "#fbbc04", "wavelet": "#4285f4"}
RECENT_FILE = Path.home() / ".wimf-studio-recent.json"
ISSUES_URL = "https://github.com/benchware/WorstImageFormat/issues/new/choose"

ZOOM_MIN, ZOOM_MAX, ZOOM_STEP, FIT_MAX = 0.01, 32.0, 1.25, 8.0
WINDOW_MIN = SIZES["window_min"]

_ORIGINAL_NATIVE = _hybrid.native

WELCOME_STEPS = (
    ("Open", "Load any PNG/JPEG/WebP image - or an existing .wimf file (Ctrl+O)."),
    ("Encode", "Keep the defaults and press Encode (Ctrl+E). It runs in the background."),
    ("Compare", "Source, Decoded and an 8x-exaggerated Difference appear side by side."),
    ("Inspect", "The tile map shows which codec every tile picked, with region decode."),
    ("Save", "Write your .wimf file (Ctrl+S). Protection and history travel inside it."),
)


def _fallback_palette():
    from .studio_theme import resolve

    return resolve("dark")


def _enable_dpi_awareness():
    """Opt into per-monitor v2 DPI awareness before Tk starts, so nothing renders blurry."""
    if sys.platform != "win32":
        return
    try:
        context = ctypes.c_void_p(-4)  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        ctypes.windll.user32.SetProcessDpiAwarenessContext(context)
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _apply_window_chrome(root, *, dark=True, background="#1c1c1c", accent="#4cc2ff", fg="#f0f0f0"):
    """Best-effort Windows 10/11 chrome: themed title bar, caption colors, accent frame, round corners."""
    if sys.platform != "win32":
        return
    try:
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        if not hwnd:
            hwnd = ctypes.windll.user32.GetAncestor(root.winfo_id(), 2)  # GA_ROOT
    except Exception:
        return

    def dwm(attribute, value):
        try:
            raw = value.lstrip("#") if isinstance(value, str) else ""
            packed = value if not raw else int(raw[4:6] + raw[2:4] + raw[0:2], 16)  # COLORREF is 0x00BBGGRR
            data = ctypes.c_int(packed)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(data), ctypes.sizeof(data))
        except Exception:
            pass

    for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (20 on current builds, 19 on 1809-era)
        dwm(attribute, 1 if dark else 0)
    dwm(35, background)  # DWMWA_CAPTION_COLOR: title bar melts into the app header
    dwm(36, fg)  # DWMWA_TEXT_COLOR: caption glyphs match the theme text
    dwm(34, accent)  # DWMWA_BORDER_COLOR: crisp accent outline around the window
    dwm(33, 2)  # DWMWA_WINDOW_CORNER_PREFERENCE: DWMWCP_ROUND (ignored pre-Win11)


def _sync_scaling(root):
    """Make Tk's point-to-pixel factor match the real monitor DPI (fixes tiny or blurry UI)."""
    try:
        dpi = root.winfo_fpixels("1i")
        target = dpi / 72.0
        if abs(float(root.tk.call("tk", "scaling")) - target) > max(0.4, target * 0.05):
            root.tk.call("tk", "scaling", target)
    except Exception:
        pass


def _safe(style, name, **options):
    try:
        style.configure(name, **options)
    except tk.TclError:
        pass


def _safe_map(style, name, **options):
    try:
        style.map(name, **options)
    except tk.TclError:
        pass


def _configure_named_styles(style, palette):
    """Typography and the accent button; Sun Valley owns every other widget color."""
    for name, font in (
        ("HeaderTitle.TLabel", FONTS["header_title"]),
        ("Heading.TLabel", FONTS["heading"]),
        ("CardTitle.TLabel", FONTS["card_title"]),
        ("Hint.TLabel", FONTS["body"]),
        ("Pane.TLabel", FONTS["body"]),
        ("TButton", FONTS["body"]),
        ("Tool.TButton", FONTS["body"]),
        ("Accent.TButton", (FONTS["body_strong"][0], 10, "bold")),
        ("TNotebook.Tab", FONTS["heading"]),
    ):
        _safe(style, name, font=font)
    _safe(style, "Tool.TButton", padding=(SPACING["md"], SPACING["xs"] + 1))
    _safe(style, "Accent.TButton", padding=(SPACING["lg"], SPACING["sm"] + 1))
    _safe(style, "TButton", padding=(SPACING["md"], SPACING["xs"] + 1))
    _safe(style, "TNotebook.Tab", padding=(SPACING["lg"], SPACING["sm"]))
    if sv_ttk is None:
        # Readable minimal fallback when Sun Valley is not installed: keep the
        # platform clam look, add our fonts plus a flat accent button.
        _safe(style, "Hint.TLabel", foreground=palette["muted"])
        _safe(
            style,
            "Accent.TButton",
            background=palette["accent"],
            foreground=palette["accent_text"],
            borderwidth=0,
            relief="flat",
        )
        _safe_map(
            style,
            "Accent.TButton",
            background=[
                ("disabled", palette["border_soft"]),
                ("pressed", mix_hex(palette["accent"], "#000000", 0.18)),
                ("active", mix_hex(palette["accent"], "#ffffff", 0.14)),
            ],
        )


class ToolTip:
    """Small hover tooltip; colors are pulled live so theme switches just work."""

    def __init__(self, widget, text, palette_provider):
        self.widget = widget
        self.text = text
        self.palette_provider = palette_provider
        self._job = None
        self._tip = None
        widget.bind("<Enter>", lambda _event: self._schedule(), add="+")
        widget.bind("<Leave>", lambda _event: self._hide(), add="+")
        widget.bind("<ButtonPress>", lambda _event: self._hide(), add="+")

    def _schedule(self):
        self._hide()
        self._job = self.widget.after(550, self._show)

    def _show(self):
        if self._tip is not None or not self.text:
            return
        palette = self.palette_provider()
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.attributes("-topmost", True)
        body = tk.Label(
            tip,
            text=self.text,
            justify="left",
            wraplength=340,
            background=palette["tip_bg"],
            foreground=palette["tip_fg"],
            highlightthickness=1,
            highlightbackground=palette["border"],
            padx=9,
            pady=6,
            font=("Segoe UI", 9),
        )
        body.pack()
        x = self.widget.winfo_rootx() + 14
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        tip.wm_geometry(f"+{x}+{y}")
        self._tip = tip

    def _hide(self):
        if self._job is not None:
            self.widget.after_cancel(self._job)
            self._job = None
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


class Card(tk.Frame):
    """Bordered section box with an uppercase title rule, like grouped boxes in native apps."""

    def __init__(self, parent, title="", palette_provider=None, padding=(SPACING["lg"], SPACING["md"])):
        self.palette_provider = palette_provider
        palette = palette_provider() if palette_provider else _fallback_palette()
        super().__init__(
            parent, background=palette["surface"], highlightbackground=palette["border"], highlightthickness=1
        )
        inner = ttk.Frame(self, padding=padding, style="Card.TFrame")
        inner.pack(fill="both", expand=True)
        if title:
            head = ttk.Frame(inner, style="Card.TFrame")
            head.pack(fill="x", pady=(0, SPACING["sm"]))
            ttk.Label(head, text=title.upper(), style="CardTitle.TLabel").pack(side="left")
            ttk.Separator(head, orient="horizontal").pack(
                side="left", fill="x", expand=True, padx=(SPACING["md"], 0), pady=SPACING["sm"] + 1
            )
            body = ttk.Frame(inner, style="Card.TFrame")
            body.pack(fill="both", expand=True)
        else:
            body = inner
        self.body = body

    def refresh(self):
        if self.palette_provider is None:
            return
        palette = self.palette_provider()
        self.configure(background=palette["surface"], highlightbackground=palette["border"])


class TitleBar(tk.Frame):
    """Custom themed title bar: logo, title, actions and drawn min/max/close controls."""

    GLYPHS = {"min": "\u2013", "max": "\u25a1", "close": "\u00d7"}
    CLOSE_HOVER = "#e81123"

    def __init__(
        self,
        app,
        window,
        *,
        title,
        subtitle=None,
        actions=(),
        controls=(),
        height=44,
        logo=True,
        on_minimize=None,
        on_maximize=None,
        on_close=None,
    ):
        super().__init__(window, height=height, background=app.palette["pane_bg"])
        self.app = app
        self.window = window
        self._on_minimize = on_minimize
        self._on_maximize = on_maximize
        self._on_close = on_close
        self._controls = controls
        self._drag = None
        self.pack_propagate(False)

        self._logo_canvas = None
        if logo:
            self._logo_canvas = tk.Canvas(
                self, width=26, height=26, background=app.palette["pane_bg"], highlightthickness=0
            )
            self._logo_canvas.pack(side="left", padx=(SPACING["lg"], SPACING["md"]), pady=(0, 1))
        text_frame = tk.Frame(self, background=app.palette["pane_bg"])
        text_frame.pack(side="left")
        self._title_label = tk.Label(
            text_frame,
            text=title,
            background=app.palette["pane_bg"],
            foreground=app.palette["fg"],
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        self._title_label.pack(anchor="w")
        self._subtitle_label = None
        if subtitle:
            self._subtitle_label = tk.Label(
                text_frame,
                text=subtitle,
                background=app.palette["pane_bg"],
                foreground=app.palette["muted"],
                font=("Segoe UI", 8),
                anchor="w",
            )
            self._subtitle_label.pack(anchor="w")
        self._spacer = tk.Label(self, text="", background=app.palette["pane_bg"])
        self._spacer.pack(side="left", fill="both", expand=True)
        for label, command in actions:
            ttk.Button(self, text=label, style="Tool.TButton", command=command).pack(
                side="left", padx=(0, 6), pady=(0, 1)
            )
        self._buttons = {}
        for kind in reversed(controls):
            button = tk.Label(
                self,
                text=self.GLYPHS[kind],
                background=app.palette["pane_bg"],
                foreground=app.palette["fg"],
                font=("Segoe UI", 12),
                width=4,
                pady=2,
            )
            button.pack(side="right", fill="y")
            handler = {"min": on_minimize, "max": on_maximize, "close": on_close}[kind]
            button.bind("<Button-1>", lambda _event, callback=handler: callback() if callback else None)
            button.bind("<Enter>", lambda _event, k=kind, b=button: self._hover(k, b, True))
            button.bind("<Leave>", lambda _event, k=kind, b=button: self._hover(k, b, False))
            self._buttons[kind] = button
        for widget in (self, text_frame, self._spacer, self._title_label, self._subtitle_label, self._logo_canvas):
            if widget is None:
                continue
            widget.bind("<ButtonPress-1>", self._press)
            widget.bind("<B1-Motion>", self._motion)
            if on_maximize is not None:
                widget.bind("<Double-Button-1>", lambda _event: on_maximize())
        self.restyle()
        app.themable.append(self.restyle)
        self.bind("<Destroy>", self._on_destroy, add="+")

    def _hover(self, kind, button, entered):
        if entered:
            if kind == "close":
                button.configure(background=self.CLOSE_HOVER, foreground="#ffffff")
            else:
                button.configure(background=self._hover_bg, foreground=self.app.palette["fg"])
        else:
            button.configure(background=self.app.palette["pane_bg"], foreground=self.app.palette["fg"])

    def _press(self, event):
        if getattr(self.app, "_maximized", False):
            self.app._toggle_maximize()
            self._drag = (self.window.winfo_width() // 2, 14)
        else:
            self._drag = (event.x_root - self.window.winfo_x(), event.y_root - self.window.winfo_y())

    def _motion(self, event):
        if self._drag is None:
            return
        self.window.geometry(f"+{event.x_root - self._drag[0]}+{event.y_root - self._drag[1]}")

    def restyle(self):
        palette = self.app.palette
        self._hover_bg = mix_hex(palette["surface"], palette["border"], 0.5)
        self.configure(background=palette["pane_bg"])
        for widget in (self._title_label, self._subtitle_label, self._spacer):
            if widget is not None:
                widget.configure(background=palette["pane_bg"])
        self._title_label.configure(foreground=palette["fg"])
        if self._subtitle_label is not None:
            self._subtitle_label.configure(foreground=palette["muted"])
        if self._logo_canvas is not None:
            self._logo_canvas.configure(background=palette["pane_bg"])
            self._logo_canvas.delete("all")
            photo = ImageTk.PhotoImage(logo_image(26, palette["fg"]))
            self.app._keep_photo(photo)
            self._logo_canvas.create_image(0, 0, image=photo, anchor="nw")
        for kind, button in self._buttons.items():
            button.configure(background=palette["pane_bg"], foreground=palette["fg"])

    def _on_destroy(self, event):
        if event.widget is self and self.restyle in self.app.themable:
            self.app.themable.remove(self.restyle)


class StudioDialog(tk.Toplevel):
    """Themed replacement for native message boxes: bordered frame, title strip, accent actions."""

    def __init__(
        self, app, *, title, message=None, detail=None, buttons, checkbox=None, default=0, rows=None, code_detail=None
    ):
        self.app = app
        self.result = None
        self.checkbox_value = None
        self._theme_refs = []
        self._button_refs = {}
        palette = app.palette
        super().__init__(app.root)
        self.withdraw()
        self.overrideredirect(True)
        self.transient(app.root)
        self.configure(background=palette["surface"], highlightbackground=palette["border"], highlightthickness=1)
        TitleBar(
            app,
            self,
            title=title,
            controls=("close",),
            height=38,
            on_close=lambda: self._finish(None),
        ).pack(fill="x")
        body = tk.Frame(self, background=palette["surface"])
        body.pack(fill="both", expand=True, padx=16)
        message_label = None
        if message:
            message_label = tk.Label(
                body,
                text=message,
                background=palette["surface"],
                foreground=palette["fg"],
                font=("Segoe UI", 10),
                justify="left",
                wraplength=430,
                anchor="w",
            )
            message_label.pack(fill="x", pady=(12, 0))
        if detail:
            tk.Label(
                body,
                text=detail,
                background=palette["surface"],
                foreground=palette["muted"],
                font=("Segoe UI", 9),
                justify="left",
                wraplength=430,
                anchor="w",
            ).pack(fill="x", pady=(6, 0))
        row_widgets = []
        if rows:
            grid = tk.Frame(body, background=palette["surface"])
            grid.pack(fill="x", pady=(12, 0))
            for index, (key, value) in enumerate(rows):
                tk.Label(
                    grid,
                    text=key,
                    background=palette["surface"],
                    foreground=palette["muted"],
                    font=("Segoe UI", 9),
                    anchor="w",
                ).grid(row=index, column=0, sticky="w", pady=2, padx=(0, 18))
                tk.Label(
                    grid,
                    text=str(value),
                    background=palette["surface"],
                    foreground=palette["fg"],
                    font=("Consolas", 9),
                    anchor="w",
                ).grid(row=index, column=1, sticky="w", pady=2)
                row_widgets.append(grid)
        code_text = None
        if code_detail:
            code_text = tk.Text(
                body,
                height=min(20, code_detail.count("\n") + 2),
                wrap="none",
                relief="flat",
                borderwidth=0,
                highlightthickness=1,
                highlightbackground=palette["border"],
                background=palette["tip_bg"],
                foreground=palette["tip_fg"],
                font=("Consolas", 9),
                padx=10,
                pady=8,
            )
            code_text.insert("1.0", code_detail)
            code_text.configure(state="disabled")
            code_text.pack(fill="x", pady=(12, 0))
        if checkbox:
            self._checkbox_var = tk.BooleanVar(value=checkbox[1])
            ttk.Checkbutton(body, text=checkbox[0], variable=self._checkbox_var).pack(anchor="w", pady=(10, 0))
        button_row = tk.Frame(body, background=palette["surface"])
        button_row.pack(fill="x", pady=(16, 14))
        for index, (label, value, kind) in enumerate(buttons):
            button = ttk.Button(
                button_row,
                text=label.replace("&&", "&"),
                style="Accent.TButton" if kind == "accent" else "TButton",
                command=lambda picked=value: self._finish(picked) if not callable(picked) else picked(),
            )
            button.pack(side="right", padx=(8, 0))
            self._button_refs[label] = button
            if index == default:
                self._default_value = value
        self.bind("<Escape>", lambda _event: self._finish(None))
        self.bind("<Return>", lambda _event: self._finish(getattr(self, "_default_value", None)))
        self.protocol("WM_DELETE_WINDOW", lambda: self._finish(None))
        self.update_idletasks()
        width, height = self.winfo_reqwidth(), self.winfo_reqheight()
        parent = app.root
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 3)
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.update_idletasks()
        self.lift()
        self.focus_set()
        try:
            self.grab_set()
        except Exception:
            pass
        fade_in(self, 150, 12)
        app.dialogs.append(self)
        self.bind("<Destroy>", self._on_destroy, add="+")

        def restyle():
            live = self.app.palette
            self.configure(background=live["surface"], highlightbackground=live["border"])
            body.configure(background=live["surface"])
            button_row.configure(background=live["surface"])
            if message_label is not None:
                message_label.configure(background=live["surface"], foreground=live["fg"])
            for grid in row_widgets:
                for child in grid.winfo_children():
                    if isinstance(child, tk.Label):
                        mono = str(child.cget("font")).lower().startswith("consolas") or "consolas" in str(
                            child.cget("font")
                        )
                        child.configure(
                            background=live["surface"],
                            foreground=live["muted"] if not mono else live["fg"],
                        )
            if code_text is not None:
                code_text.configure(
                    background=live["tip_bg"], foreground=live["tip_fg"], highlightbackground=live["border"]
                )

        self._theme_refs.append(restyle)

    def _on_destroy(self, event):
        if event.widget is self and self in self.app.dialogs:
            self.app.dialogs.remove(self)

    def _finish(self, value):
        if hasattr(self, "_checkbox_var"):
            self.checkbox_value = self._checkbox_var.get()
        self.result = value
        try:
            self.grab_release()
        except Exception:
            pass
        fade_out(self, 90, self.destroy)
        self.after(220, lambda: _destroy_quietly(self))

    def flash_button(self, label, temporary, revert, ms=1200):
        button = self._button_refs.get(label)
        if button is None:
            return

        def restore():
            try:
                button.configure(text=revert)
            except tk.TclError:
                pass

        button.configure(text=temporary)
        self.after(ms, restore)

    def refresh_theme(self):
        for callback in self._theme_refs:
            callback()


def _destroy_quietly(window):
    try:
        window.destroy()
    except tk.TclError:
        pass


def fade_in(window, duration=160, slide=0, steps=6):
    """Fade (and optionally slide) a window in; silently no-ops where alpha is unsupported."""
    try:
        window.attributes("-alpha", 0)
    except tk.TclError:
        return
    interval = max(10, duration // steps)
    base_y = window.winfo_y()

    def step(index):
        alpha = min(1.0, (index + 1) / steps)
        try:
            window.attributes("-alpha", alpha)
            if slide:
                window.geometry(f"+{window.winfo_x()}+{base_y - round(slide * (1 - alpha))}")
        except tk.TclError:
            return
        if alpha < 1:
            window.after(interval, step, index + 1)

    window.after(interval, step, 0)


def fade_out(window, duration=100, on_done=None, steps=5):
    try:
        window.attributes("-alpha", 1)
    except tk.TclError:
        if on_done is not None:
            on_done()
        return
    interval = max(10, duration // steps)

    def step(index):
        alpha = max(0.0, 1 - (index + 1) / steps)
        try:
            window.attributes("-alpha", alpha)
        except tk.TclError:
            return
        if alpha > 0:
            window.after(interval, step, index + 1)
        elif on_done is not None:
            on_done()

    window.after(interval, step, 0)


class WelcomeWindow(tk.Toplevel):
    """Rich first-run window: numbered quick start, tips, and a 'show on startup' toggle."""

    def __init__(self, app):
        self.app = app
        palette = app.palette
        super().__init__(app.root)
        self.withdraw()
        self.title("Welcome to WIMF Studio")
        self.overrideredirect(True)
        self.configure(background=palette["pane_bg"], highlightbackground=palette["border"], highlightthickness=1)
        self.transient(app.root)
        self._theme_refs = []
        TitleBar(
            app,
            self,
            title="Welcome to WIMF Studio",
            subtitle=f"Version {wimf.__version__} - WIM2 hybrid image codec",
            controls=("close",),
            height=48,
            on_close=self.destroy,
        ).pack(fill="x")
        body = tk.Frame(self, background=palette["pane_bg"])
        body.pack(fill="both", expand=True, padx=SPACING["xl"])
        steps_label = tk.Label(
            body,
            text="GET STARTED IN FIVE STEPS",
            background=palette["pane_bg"],
            foreground=palette["muted"],
            font=("Segoe UI", 8, "bold"),
            anchor="w",
        )
        steps_label.pack(anchor="w", pady=(14, 8))
        self._step_widgets = []
        for index, (step_title, step_text) in enumerate(WELCOME_STEPS, start=1):
            row = tk.Frame(body, background=palette["pane_bg"])
            row.pack(fill="x", pady=4)
            circle = tk.Canvas(row, width=26, height=26, background=palette["pane_bg"], highlightthickness=0)
            circle.pack(side="left", padx=(0, 12))
            circle.create_oval(2, 2, 24, 24, fill=palette["accent"], width=0)
            circle.create_text(13, 13, text=str(index), fill=palette["accent_text"], font=("Segoe UI", 10, "bold"))
            text_frame = tk.Frame(row, background=palette["pane_bg"])
            text_frame.pack(side="left", fill="x", expand=True)
            step_label = tk.Label(
                text_frame,
                text=step_title,
                background=palette["pane_bg"],
                foreground=palette["fg"],
                font=("Segoe UI", 10, "bold"),
                anchor="w",
            )
            step_label.pack(anchor="w")
            detail_label = tk.Label(
                text_frame,
                text=step_text,
                background=palette["pane_bg"],
                foreground=palette["muted"],
                font=("Segoe UI", 9),
                anchor="w",
                wraplength=460,
                justify="left",
            )
            detail_label.pack(anchor="w")
            self._step_widgets.append((row, circle, index, text_frame, step_label, detail_label))
        footer = tk.Frame(self, background=palette["pane_bg"])
        footer.pack(fill="x", padx=SPACING["xl"], pady=(SPACING["lg"], 0))
        hint = tk.Label(
            footer,
            text="Mouse: scroll to zoom, drag to pan, double-click to fit. Everything runs in the background; Cancel stops it.",
            background=palette["pane_bg"],
            foreground=palette["muted"],
            font=("Segoe UI", 9),
            wraplength=470,
            justify="left",
            anchor="w",
        )
        hint.pack(fill="x")
        self._checkbox_var = tk.BooleanVar(value=app.settings["show_welcome"])
        checkbox = ttk.Checkbutton(footer, text="Show this window when Studio starts", variable=self._checkbox_var)
        checkbox.pack(anchor="w", pady=(10, 0))
        self._checkbox_var.trace_add("write", lambda *_args: self._persist())
        buttons = tk.Frame(self, background=palette["pane_bg"])
        buttons.pack(fill="x", padx=SPACING["xl"], pady=(SPACING["lg"], SPACING["xl"]))
        ttk.Button(buttons, text="Open an image...", style="Accent.TButton", command=self._open_image).pack(
            side="right"
        )
        ttk.Button(buttons, text="Explore on my own", command=self.destroy).pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda _event: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.update_idletasks()
        width, height = self.winfo_reqwidth(), self.winfo_reqheight()
        height = min(height, app.root.winfo_screenheight() - 120)
        x = app.root.winfo_rootx() + max(0, (app.root.winfo_width() - width) // 2)
        y = app.root.winfo_rooty() + max(0, (app.root.winfo_height() - height) // 4)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.deiconify()
        self.update_idletasks()
        self.lift()
        fade_in(self, 170, 14)
        app.dialogs.append(self)
        self.bind("<Destroy>", self._on_destroy, add="+")

        def pane_bg():
            return app.palette["pane_bg"]

        def restyle_steps():
            live = app.palette
            for row, circle, index, text_frame, step_label, detail_label in self._step_widgets:
                for widget in (row, circle, text_frame):
                    widget.configure(background=live["pane_bg"])
                circle.delete("all")
                circle.create_oval(2, 2, 24, 24, fill=live["accent"], width=0)
                circle.create_text(13, 13, text=str(index), fill=live["accent_text"], font=("Segoe UI", 10, "bold"))
                step_label.configure(background=live["pane_bg"], foreground=live["fg"])
                detail_label.configure(background=live["pane_bg"], foreground=live["muted"])

        self._theme_refs += [
            lambda: self.configure(background=pane_bg(), highlightbackground=app.palette["border"]),
            lambda: [widget.configure(background=pane_bg()) for widget in (body, footer, buttons)],
            lambda: steps_label.configure(background=pane_bg(), foreground=app.palette["muted"]),
            lambda: hint.configure(background=pane_bg(), foreground=app.palette["muted"]),
            restyle_steps,
        ]

    def _persist(self):
        self.app.settings["show_welcome"] = self._checkbox_var.get()
        self.app.settings.save()

    def _open_image(self):
        self.destroy()
        self.app.open_file()

    def _on_destroy(self, event):
        if event.widget is self and self in self.app.dialogs:
            self.app.dialogs.remove(self)

    def refresh_theme(self):
        for callback in self._theme_refs:
            callback()


class SettingsWindow(tk.Toplevel):
    """Themed settings surface: appearance, behavior, encoding defaults, and the codec core."""

    def __init__(self, app):
        self.app = app
        self._cards = []
        self._label_refs = []
        palette = app.palette
        super().__init__(app.root)
        self.withdraw()
        self.title("WIMF Studio Settings")
        self.overrideredirect(True)
        self.configure(background=palette["pane_bg"], highlightbackground=palette["border"], highlightthickness=1)
        self.transient(app.root)
        self._theme_refs = []
        TitleBar(
            app,
            self,
            title="Settings",
            subtitle=f"Stored in {SETTINGS_FILE.name} - changes apply immediately.",
            controls=("close",),
            height=48,
            on_close=self.destroy,
        ).pack(fill="x")
        container = tk.Frame(self, background=palette["pane_bg"])
        container.pack(fill="both", expand=True, padx=SPACING["xl"], pady=(SPACING["md"], SPACING["lg"]))

        appearance = self._card(container, "Appearance")
        appearance.pack(fill="x", pady=(0, 8))
        row = tk.Frame(appearance.body, background=palette["surface"])
        row.pack(fill="x")
        self._label_refs.append(self._make_label(row, "Theme"))
        self.theme_choice = tk.StringVar(value=PALETTES[app.settings["theme"]]["label"].capitalize())
        theme_box = ttk.Combobox(
            row,
            state="readonly",
            width=24,
            textvariable=self.theme_choice,
            values=[PALETTES[name]["label"].capitalize() for name in THEME_NAMES],
        )
        theme_box.pack(side="left")
        theme_box.bind("<<ComboboxSelected>>", self._on_theme)
        self.theme_note = tk.Label(
            row, text="", background=palette["surface"], foreground=palette["muted"], font=("Segoe UI", 9)
        )
        self.theme_note.pack(side="left", padx=(12, 0))
        self._sync_theme_note()

        behavior = self._card(container, "Behavior")
        behavior.pack(fill="x", pady=(0, 8))
        self.welcome_var = tk.BooleanVar(value=app.settings["show_welcome"])
        self.tips_var = tk.BooleanVar(value=app.settings["show_tips"])
        self.confirm_var = tk.BooleanVar(value=app.settings["confirm_close"])
        for label, variable, command in (
            ("Show the welcome window on startup", self.welcome_var, self._on_flag),
            ("Show rotating tips on the encode tab", self.tips_var, self._on_flag),
            ("Ask before closing with unsaved changes", self.confirm_var, self._on_flag),
        ):
            ttk.Checkbutton(behavior.body, text=label, variable=variable, command=command).pack(anchor="w", pady=2)

        encoding = self._card(container, "Encoding defaults")
        encoding.pack(fill="x", pady=(0, 8))
        grid = encoding.body
        self.quality_value = tk.IntVar(value=app.settings["quality"])
        self.preset_value = tk.StringVar(value=app.settings["preset"])
        self.codec_value = tk.StringVar(value=app.settings["codec"])
        self.threads_value = tk.StringVar(value=app.settings["threads"])
        quality_spin = ttk.Spinbox(grid, from_=1, to=10, width=6, textvariable=self.quality_value)
        preset_box = ttk.Combobox(
            grid, state="readonly", width=14, textvariable=self.preset_value, values=QUALITY_PRESETS
        )
        codec_box = ttk.Combobox(grid, state="readonly", width=14, textvariable=self.codec_value, values=CODECS)
        threads_entry = ttk.Entry(grid, width=8, textvariable=self.threads_value)
        for row_index, (label, widget) in enumerate(
            (("Quality", quality_spin), ("Preset", preset_box), ("Codec", codec_box), ("Threads", threads_entry))
        ):
            self._label_refs.append(self._make_label(grid, label, grid_row=row_index))
            widget.grid(row=row_index, column=1, sticky="w", pady=3)
        grid.columnconfigure(1, weight=1)
        ttk.Button(grid, text="Apply and save as default", style="Accent.TButton", command=self._apply_encoding).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0)
        )

        core = self._card(container, "Codec core")
        core.pack(fill="x", pady=(0, 8))
        core_row = tk.Frame(core.body, background=palette["surface"])
        core_row.pack(fill="x")
        self._label_refs.append(self._make_label(core_row, "Engine"))
        self.core_choice = tk.StringVar(value=app.settings["core"])
        core_box = ttk.Combobox(core_row, state="readonly", width=12, textvariable=self.core_choice, values=CORE_MODES)
        core_box.pack(side="left")
        core_box.bind("<<ComboboxSelected>>", self._on_core)
        self.core_note = tk.Label(
            core.body,
            text=self._backend_text(),
            background=palette["surface"],
            foreground=palette["muted"],
            font=("Segoe UI", 9),
            justify="left",
            anchor="w",
        )
        self.core_note.pack(fill="x", pady=(8, 0))

        reset_row = tk.Frame(container, background=palette["pane_bg"])
        reset_row.pack(fill="x")
        ttk.Button(reset_row, text="Reset all settings", command=self._reset_all).pack(side="right")

        self.bind("<Escape>", lambda _event: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.update_idletasks()
        width = max(self.winfo_reqwidth(), 560)
        height = min(self.winfo_reqheight(), app.root.winfo_screenheight() - 100)
        x = app.root.winfo_rootx() + max(0, (app.root.winfo_width() - width) // 2)
        y = app.root.winfo_rooty() + max(0, (app.root.winfo_height() - height) // 4)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.deiconify()
        self.update_idletasks()
        self.lift()
        fade_in(self, 170, 14)
        app.dialogs.append(self)
        self.bind("<Destroy>", self._on_destroy, add="+")
        self._theme_refs.append(self._restyle)

    def _restyle(self):
        live = self.app.palette
        self.configure(background=live["pane_bg"], highlightbackground=live["border"])
        for widget in self.winfo_children():
            if isinstance(widget, tk.Frame):
                widget.configure(background=live["pane_bg"])
        for label in self._label_refs:
            label.configure(background=live["surface"], foreground=live["fg"])
        for note in (self.theme_note, self.core_note):
            note.configure(background=live["surface"], foreground=live["muted"])
        for card in self._cards:
            card.refresh()

    def _card(self, parent, title):
        card = Card(parent, title, self.app._palette)
        self._cards.append(card)
        return card

    def _make_label(self, parent, text, grid_row=None):
        label = tk.Label(
            parent,
            text=text,
            background=self.app.palette["surface"],
            foreground=self.app.palette["fg"],
            font=("Segoe UI", 9),
        )
        if grid_row is None:
            label.pack(side="left", padx=(0, 10))
        else:
            label.grid(row=grid_row, column=0, sticky="w", padx=(0, 10), pady=3)
        return label

    def _backend_text(self):
        native = bool(wimf.runtime_info().get("native"))
        active = "native C++ core" if native else "Python reference core"
        preference = self.app.settings["core"]
        suffix = "" if preference in ("auto", "native") else " (forced in Settings)"
        return f"Active backend: {active}{suffix}. auto/native use the C++ core when the extension is installed."

    def _sync_theme_note(self):
        self.theme_note.configure(text="Applies instantly.")

    def _on_theme(self, _event):
        for theme_id, theme in PALETTES.items():
            if theme["label"].capitalize() == self.theme_choice.get():
                self.app.set_theme(theme_id)
                self._sync_theme_note()
                self._restyle()
                return

    def _on_flag(self):
        self.app.settings["show_welcome"] = self.welcome_var.get()
        self.app.settings["show_tips"] = self.tips_var.get()
        self.app.settings["confirm_close"] = self.confirm_var.get()
        self.app.settings.save()
        self.app.set_tips_enabled(self.tips_var.get())

    def _apply_encoding(self):
        settings = self.app.settings
        try:
            quality = max(1, min(10, int(self.quality_value.get())))
        except Exception:
            quality = DEFAULTS["quality"]
        settings["quality"] = quality
        settings["preset"] = self.preset_value.get()
        settings["codec"] = self.codec_value.get()
        settings["threads"] = self.threads_value.get().strip()
        settings.save()
        self.app.quality.set(quality)
        self.app.preset.set(settings["preset"])
        self.app.codec.set(settings["codec"])
        self.app.threads.set(settings["threads"])
        self.app.status.set("Encoding defaults applied to this session and saved.")

    def _on_core(self, _event):
        mode = self.core_choice.get()
        self.app._apply_core_preference(mode)
        self.core_note.configure(text=self._backend_text())

    def _reset_all(self):
        dialog = StudioDialog(
            self.app,
            title="Reset settings",
            message="Restore every setting to its default?",
            detail="Theme, behavior toggles, encoding defaults and the core preference will be reset.",
            buttons=(("Cancel", False, ""), ("Reset", True, "accent")),
        )
        if dialog.result is not True:
            return
        self.app.settings.reset()
        self.app._apply_core_preference(self.app.settings["core"], save=False)
        self.app.set_theme(self.app.settings["theme"])
        self.app.set_tips_enabled(self.app.settings["show_tips"])
        self.theme_choice.set(PALETTES[self.app.settings["theme"]]["label"].capitalize())
        self.welcome_var.set(self.app.settings["show_welcome"])
        self.tips_var.set(self.app.settings["show_tips"])
        self.confirm_var.set(self.app.settings["confirm_close"])
        self.quality_value.set(self.app.settings["quality"])
        self.preset_value.set(self.app.settings["preset"])
        self.codec_value.set(self.app.settings["codec"])
        self.threads_value.set(self.app.settings["threads"])
        self.core_choice.set(self.app.settings["core"])
        self.core_note.configure(text=self._backend_text())
        self._sync_theme_note()
        self._restyle()
        self.app.status.set("Settings restored to defaults.")

    def _on_destroy(self, event):
        if event.widget is self and self in self.app.dialogs:
            self.app.dialogs.remove(self)

    def refresh_theme(self):
        for callback in self._theme_refs:
            callback()
        self.app._reapply_chrome(self)


class ImagePane(tk.Frame):
    """Framed image viewport with zoom controls, drag panning, anchored wheel zoom and auto-fit."""

    BUTTON_WIDTHS = {"-": 3, "+": 3, "Fit": 5, "1:1": 5}

    def __init__(self, parent, title, palette_provider, empty_hint="No image loaded."):
        self.palette_provider = palette_provider
        palette = palette_provider() if palette_provider else _fallback_palette()
        super().__init__(
            parent, background=palette["surface"], highlightbackground=palette["border"], highlightthickness=1
        )
        self.empty_title = title
        self.empty_hint = empty_hint

        header = ttk.Frame(self, padding=(SPACING["md"], SPACING["xs"]), style="Card.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text=title, style="Heading.TLabel").pack(side="left")
        self.zoom_label = tk.Label(
            header,
            text="-",
            width=6,
            anchor="e",
            background=palette["surface"],
            foreground=palette["muted"],
            font=("Segoe UI", 9),
        )
        self.zoom_label.pack(side="right", padx=(8, 0))
        for text, command, tip in (
            ("-", lambda: self.zoom_by(-1), "Zoom out"),
            ("+", lambda: self.zoom_by(+1), "Zoom in"),
            ("Fit", self.fit, "Fit to window (double-click)"),
            ("1:1", self.actual, "Actual size"),
        ):
            button = ttk.Button(
                header, text=text, width=self.BUTTON_WIDTHS[text], style="Tool.TButton", command=command
            )
            button.pack(side="right", padx=(4, 0))
            ToolTip(button, tip, palette_provider)

        ttk.Separator(self).pack(fill="x")
        canvas = tk.Canvas(
            self,
            background=palette["pane_bg"],
            highlightthickness=1,
            highlightbackground=palette["border_soft"],
        )
        canvas.pack(fill="both", expand=True, padx=SPACING["sm"], pady=(SPACING["xs"], SPACING["sm"]))
        self.canvas = canvas
        self.image = None
        self.photo = None
        self.overlays = []
        self.zoom = 1.0
        self.auto_fit = True
        self._origin = (0, 0)
        self._shown = (0, 0)
        self._resize_job = None
        self._render_job = None
        self._refine_job = None
        self._anchor = None
        self._cache_key = None
        self._rev = 0

        canvas.bind("<MouseWheel>", self._on_wheel)
        canvas.bind("<Button-4>", lambda event: self._zoom_at(event.x, event.y, +1))
        canvas.bind("<Button-5>", lambda event: self._zoom_at(event.x, event.y, -1))
        canvas.bind("<ButtonPress-1>", lambda event: canvas.scan_mark(event.x, event.y))
        canvas.bind("<B1-Motion>", lambda event: canvas.scan_dragto(event.x, event.y, gain=1))
        canvas.bind("<Double-Button-1>", self._on_double_click)
        canvas.bind("<Configure>", self._on_resize)

    def apply_palette(self, palette):
        self.configure(background=palette["surface"], highlightbackground=palette["border"])
        self.canvas.configure(background=palette["pane_bg"], highlightbackground=palette["border_soft"])
        self.zoom_label.configure(background=palette["surface"], foreground=palette["muted"])
        self.redraw()

    def set_image(self, image, overlays=None):
        self.image = image.copy() if image is not None else None
        self.overlays = list(overlays or [])
        self._rev += 1
        self.fit()

    def set_overlays(self, overlays):
        self.overlays = list(overlays)
        self._rev += 1
        self._render_now()

    def _cancel_render_jobs(self):
        for attribute in ("_render_job", "_refine_job"):
            job = getattr(self, attribute)
            if job is not None:
                self.after_cancel(job)
                setattr(self, attribute, None)

    def _render_now(self):
        self._cancel_render_jobs()
        self.redraw(final=True)

    def fit(self):
        self.auto_fit = True
        if self.image is None:
            self._render_now()
            return
        self.update_idletasks()
        view_w = max(8, self.canvas.winfo_width() - 4)
        view_h = max(8, self.canvas.winfo_height() - 4)
        scale = min(view_w / max(1, self.image.width), view_h / max(1, self.image.height))
        self.zoom = max(ZOOM_MIN, min(FIT_MAX, scale))
        self._render_now()

    def actual(self):
        self.auto_fit = False
        self.zoom = 1.0
        self._render_now()

    def zoom_by(self, direction):
        if self.image is None:
            return
        self._zoom_at(self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2, direction)

    def redraw(self, final=True):
        if self.image is None:
            self._draw_empty()
            return
        canvas = self.canvas
        width = max(1, round(self.image.width * self.zoom))
        height = max(1, round(self.image.height * self.zoom))
        view_w, view_h = max(1, canvas.winfo_width()), max(1, canvas.winfo_height())
        origin_x = self._clamped_origin(self._origin[0], width, view_w)
        origin_y = self._clamped_origin(self._origin[1], height, view_h)
        upscale = self.zoom >= 1
        source_x0 = max(0, min(self.image.width - 1, int(math.floor(-origin_x / self.zoom))))
        source_y0 = max(0, min(self.image.height - 1, int(math.floor(-origin_y / self.zoom))))
        source_x1 = max(source_x0 + 1, min(self.image.width, int(math.ceil((view_w - origin_x) / self.zoom))))
        source_y1 = max(source_y0 + 1, min(self.image.height, int(math.ceil((view_h - origin_y) / self.zoom))))
        box = (source_x0, source_y0, source_x1, source_y1)
        out_w = max(1, round((source_x1 - source_x0) * self.zoom))
        out_h = max(1, round((source_y1 - source_y0) * self.zoom))
        key = (self._rev, out_w, out_h, upscale, final, box)
        if key != self._cache_key:
            if upscale:
                method = Image.Resampling.NEAREST
            else:
                method = Image.Resampling.LANCZOS if final else Image.Resampling.BILINEAR
            region = self.image.crop(box)
            self.photo = ImageTk.PhotoImage(region.resize((out_w, out_h), method))
            self._cache_key = key
        canvas.delete("all")
        canvas.create_image(
            origin_x + source_x0 * self.zoom, origin_y + source_y0 * self.zoom, image=self.photo, anchor="nw"
        )
        line_width = 2 if upscale else 1
        for overlay in self.overlays:
            x, y, tile_w, tile_h, color = overlay[:5]
            canvas.create_rectangle(
                origin_x + x * self.zoom,
                origin_y + y * self.zoom,
                origin_x + (x + tile_w) * self.zoom,
                origin_y + (y + tile_h) * self.zoom,
                outline=color,
                width=line_width,
            )
        canvas.configure(scrollregion=(0, 0, max(width, view_w), max(height, view_h)))
        self._origin = (origin_x, origin_y)
        self._shown = (width, height)
        self.zoom_label.configure(text=f"{round(self.zoom * 100)}%")
        if self._anchor is not None:
            anchor_x, anchor_y, event_x, event_y = self._anchor
            self._anchor = None
            canvas.xview_moveto(min(1.0, max(0.0, (anchor_x * width - event_x) / max(1, width))))
            canvas.yview_moveto(min(1.0, max(0.0, (anchor_y * height - event_y) / max(1, height))))

    @staticmethod
    def _clamped_origin(previous, shown, view):
        if shown <= view:
            return max(0, (view - shown) // 2)
        return min(max(0, previous), shown - view)

    def _draw_empty(self):
        canvas = self.canvas
        canvas.delete("all")
        palette = self.palette_provider() if self.palette_provider else _fallback_palette()
        view_w, view_h = max(1, canvas.winfo_width()), max(1, canvas.winfo_height())
        center_x, center_y = view_w // 2, view_h // 2
        canvas.create_text(
            center_x,
            center_y - 10,
            text=self.empty_title,
            fill=palette["fg"],
            font=("Segoe UI", 11, "bold"),
        )
        canvas.create_text(
            center_x,
            center_y + 16,
            text=self.empty_hint,
            fill=palette["muted"],
            font=("Segoe UI", 9),
            width=max(120, view_w - 24),
        )
        self._origin = (0, 0)
        self._shown = (0, 0)
        self._cache_key = None
        self.zoom_label.configure(text="-")

    def _on_resize(self, _event):
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(80, self._resize_done)

    def _resize_done(self):
        self._resize_job = None
        if self.image is None:
            self._cancel_render_jobs()
            self._draw_empty()
        elif self.auto_fit:
            self.fit()
        else:
            self._render_now()

    def _on_wheel(self, event):
        self._zoom_at(event.x, event.y, 1 if event.delta > 0 else -1)

    def _zoom_at(self, x, y, direction):
        if self.image is None:
            return
        new_zoom = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom * (ZOOM_STEP if direction > 0 else 1 / ZOOM_STEP)))
        if math.isclose(new_zoom, self.zoom):
            return
        old_w, old_h = max(1, self._shown[0]), max(1, self._shown[1])
        anchor_x = (self.canvas.canvasx(x) - self._origin[0]) / old_w
        anchor_y = (self.canvas.canvasy(y) - self._origin[1]) / old_h
        self.auto_fit = False
        self.zoom = new_zoom
        self._anchor = (anchor_x, anchor_y, x, y)
        if self._refine_job is not None:
            self.after_cancel(self._refine_job)
        self._refine_job = self.after(160, self._refine_render)
        if self._render_job is None:
            self._render_job = self.after_idle(self._preview_render)

    def _preview_render(self):
        self._render_job = None
        self.redraw(final=False)

    def _refine_render(self):
        self._refine_job = None
        if self._render_job is None:
            self.redraw(final=True)

    def _on_double_click(self, _event):
        if self.image is None:
            return
        if math.isclose(self.zoom, 1.0):
            self.fit()
        else:
            self.actual()


def _display_array(array):
    value = np.asarray(array)
    if value.dtype != np.uint8:
        maximum = max(1, int(value.max(initial=1)))
        value = np.rint(value.astype(np.float64) * (255 / maximum)).astype(np.uint8)
    if value.ndim == 3 and value.shape[2] == 1:
        value = value[..., 0]
    if value.ndim == 3 and value.shape[2] > 4:
        value = value[..., :3]
    return Image.fromarray(value)


class WIMFStudio:
    def __init__(self, root, path=None):
        self.root = root
        self.root.title("WIMF Studio")
        self.settings = StudioSettings.load()
        self.theme_id = self.settings["theme"]
        self.dark = PALETTES[self.theme_id]["dark"]
        self.palette = self.settings.palette()
        self.document = StudioDocument()
        self.jobs = JobController()
        self.recent = self._load_recent()
        self.cards = []
        self.themable = []
        self.dialogs = []
        self._photo_refs = []
        self.progress_mode = "idle"
        self.tile_vars = {}
        self._tile_overlays = []
        self._tile_modes = []
        self._build_style()
        self._build_menu()
        self._build_ui()
        self._apply_core_preference(self.settings["core"], save=False)
        self.tabs.bind("<<NotebookTabChanged>>", lambda _event: self.root.after_idle(self._refit_visible))
        self.root.bind("<Map>", lambda _event: self._reapply_chrome())
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(80, self._poll_jobs)
        if path:
            self.open_path(path)

    # ------------------------------------------------------------ theming

    def _palette(self):
        return self.palette

    def _card(self, parent, title="", padding=(12, 10)):
        card = Card(parent, title, self._palette, padding)
        self.cards.append(card)
        return card

    def _tip(self, widget, text):
        ToolTip(widget, text, self._palette)

    def _build_style(self):
        ttk.Style(self.root)
        screen_w, screen_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        width = int(min(1500, max(WINDOW_MIN[0], screen_w * 0.74)))
        height = int(min(950, max(WINDOW_MIN[1], screen_h * 0.8)))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 3)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(*WINDOW_MIN)
        _sync_scaling(self.root)
        self._apply_theme(self.theme_id)

    def _apply_theme(self, theme_id):
        if theme_id not in THEME_NAMES:
            theme_id = "dark"
        self.theme_id = theme_id
        self.dark = PALETTES[theme_id]["dark"]
        self.palette = self.settings.palette()
        style = ttk.Style(self.root)
        if sv_ttk is not None:
            desired = "dark" if self.dark else "light"
            if sv_ttk.get_theme() != desired:
                sv_ttk.set_theme(desired)
        elif "clam" in style.theme_names():
            style.theme_use("clam")
        _configure_named_styles(style, self.palette)
        self.root.configure(background=self.palette["pane_bg"])
        self._reapply_chrome()
        for card in self.cards:
            card.refresh()
        for pane in getattr(self, "image_panes", []):
            pane.apply_palette(self.palette)
        for callback in list(self.themable):
            try:
                callback()
            except tk.TclError:
                self.themable.remove(callback)
        for dialog in list(self.dialogs):
            dialog.refresh_theme()
        for menu in list(getattr(self, "_theme_menus", [])):
            try:
                self._style_menu_tree(menu)
            except tk.TclError:
                self._theme_menus.remove(menu)
        self._update_iconphoto()
        if hasattr(self, "theme_label"):
            self.theme_label.configure(text=PALETTES[theme_id]["label"].capitalize())

    def _reapply_chrome(self, window=None):
        _apply_window_chrome(
            window or self.root,
            dark=self.dark,
            background=self.palette["pane_bg"],
            accent=self.palette["accent"],
            fg=self.palette["fg"],
        )

    # ------------------------------------------------------ window controls

    def _update_iconphoto(self):
        photo = ImageTk.PhotoImage(logo_image(32, self.palette["accent"]))
        self._keep_photo(photo)
        try:
            self.root.iconphoto(False, photo)
        except Exception:
            pass

    def _keep_photo(self, photo):
        self._photo_refs.append(photo)

    def toggle_theme(self):
        target = "light" if self.dark else "dark"
        self.settings["theme"] = target
        self.settings.save()
        self._apply_theme(target)

    def set_theme(self, theme_id):
        self.settings["theme"] = theme_id
        self.settings.save()
        self._apply_theme(theme_id)

    # ------------------------------------------------------------ settings

    def _apply_core_preference(self, mode, save=True):
        if mode == "python":
            _hybrid.native = None
        else:
            _hybrid.native = _ORIGINAL_NATIVE
        if save:
            self.settings["core"] = mode
            self.settings.save()

    def open_settings(self):
        for dialog in list(self.dialogs):
            if isinstance(dialog, SettingsWindow):
                dialog.deiconify()
                dialog.lift()
                dialog.focus_set()
                return
        SettingsWindow(self)

    def set_tips_enabled(self, enabled):
        self.settings["show_tips"] = enabled
        self.settings.save()
        if not enabled:
            if getattr(self, "tip_card", None) is not None:
                self.tip_card.pack_forget()
            return
        if getattr(self, "tip_card", None) is None:
            self._build_tip_card()
        if getattr(self, "compare_top", None) is not None:
            self.tip_card.pack(before=self.compare_top, fill="x", padx=10, pady=(10, 0))

    # --------------------------------------------------------------- menu

    def _build_menu(self):
        self._theme_menus = []
        self.app_menu = self._make_menu(self.root, postcommand=lambda: self._style_menu_tree(self.app_menu))
        file_menu = self._make_menu(self.app_menu)
        file_menu.add_command(label="Open...", command=self.open_file, accelerator="Ctrl+O")
        self.recent_menu = self._make_menu(file_menu, postcommand=lambda: self._fill_recent(self.recent_menu))
        file_menu.add_cascade(label="Open Recent", menu=self.recent_menu)
        file_menu.add_separator()
        file_menu.add_command(label="Save WIMF", command=self.save, accelerator="Ctrl+S")
        file_menu.add_command(
            label="Save WIMF As...", command=lambda: self.save(as_new=True), accelerator="Ctrl+Shift+S"
        )
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.close, accelerator="Alt+F4")
        self.app_menu.add_cascade(label="File", menu=file_menu)
        view_menu = self._make_menu(self.app_menu)
        view_menu.add_command(label="Settings...", command=self.open_settings, accelerator="Ctrl+,")
        view_menu.add_separator()
        view_menu.add_command(label="Fit all images", command=self.fit_all, accelerator="Ctrl+0")
        view_menu.add_command(label="Actual size", command=self.actual_all, accelerator="Ctrl+1")
        view_menu.add_command(label="Runtime information", command=self.show_runtime)
        view_menu.add_separator()
        view_menu.add_command(label="Toggle light/dark", command=self.toggle_theme, accelerator="Ctrl+T")
        self.app_menu.add_cascade(label="View", menu=view_menu)
        help_menu = self._make_menu(self.app_menu)
        help_menu.add_command(label="Welcome & Quick Start...", command=self.show_welcome, accelerator="F1")
        help_menu.add_command(label="Report a Bug...", command=self.report_bug)
        help_menu.add_command(label="About WIMF Studio", command=self.show_about)
        self.app_menu.add_cascade(label="Help", menu=help_menu)
        self._style_menu_tree(self.app_menu)

    def _make_menu(self, parent, postcommand=None):
        menu = tk.Menu(parent, tearoff=False, postcommand=postcommand)
        self._theme_menus.append(menu)
        return menu

    def _style_menu_tree(self, menu):
        palette = self.palette
        hover = palette["menu_hover"]
        try:
            end = menu.index("end") or 0
            for index in range(end + 1):
                if menu.type(index) == "cascade":
                    self._style_menu_tree(self.root.nametowidget(str(menu.entrycget(index, "menu"))))
        except tk.TclError:
            pass
        try:
            menu.configure(
                background=palette["surface"],
                foreground=palette["fg"],
                activebackground=hover,
                activeforeground=palette["fg"],
                disabledforeground=palette["muted"],
                borderwidth=0,
                relief="flat",
            )
        except tk.TclError:
            pass
        self.root.bind("<Control-o>", lambda _event: self.open_file())
        self.root.bind("<Control-s>", lambda _event: self.save())
        self.root.bind("<Control-S>", lambda _event: self.save(as_new=True))
        self.root.bind("<Control-e>", lambda _event: self.start_encode())
        self.root.bind("<Control-E>", lambda _event: self.start_encode())
        self.root.bind("<Control-t>", lambda _event: self.toggle_theme())
        self.root.bind("<Control-T>", lambda _event: self.toggle_theme())
        self.root.bind("<Control-comma>", lambda _event: self.open_settings())
        self.root.bind("<Control-0>", lambda _event: self.fit_all())
        self.root.bind("<Control-1>", lambda _event: self.actual_all())
        self.root.bind("<F1>", lambda _event: self.show_welcome())

    def fit_all(self):
        for pane in self.image_panes:
            pane.fit()

    def actual_all(self):
        for pane in self.image_panes:
            pane.actual()

    # ------------------------------------------------------------ main UI

    def _build_ui(self):
        self._build_header()

        ttk.Separator(self.root).pack(fill="x")

        toolbar = ttk.Frame(self.root, padding=(SPACING["lg"], SPACING["md"]))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Open", command=self.open_file).pack(side="left")
        recent_button = ttk.Menubutton(toolbar, text="Recent", direction="below")
        recent_toolbar_menu = tk.Menu(
            recent_button, tearoff=False, postcommand=lambda: self._fill_recent(recent_toolbar_menu)
        )
        recent_button.configure(menu=recent_toolbar_menu)
        recent_button.pack(side="left", padx=(SPACING["sm"], 0))
        self._tip(recent_button, "Reopen recently used files.")
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=SPACING["lg"], pady=SPACING["xs"])
        ttk.Button(toolbar, text="Save", command=self.save).pack(side="left")
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=SPACING["lg"], pady=SPACING["xs"])
        ttk.Button(toolbar, text="Encode", style="Accent.TButton", command=self.start_encode).pack(side="left")
        self.cancel_button = ttk.Button(toolbar, text="Cancel", command=self.jobs.cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=(SPACING["sm"], 0))
        self._tip(self.cancel_button, "Stop the running operation.")
        self.progress = ttk.Progressbar(toolbar, mode="indeterminate")
        self.progress.pack(side="right", fill="x", expand=True, padx=(SPACING["lg"], 0))

        ttk.Separator(self.root).pack(fill="x")

        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=SPACING["lg"], pady=(SPACING["sm"], 0))
        self.compare_tab = ttk.Frame(self.tabs)
        self.inspect_tab = ttk.Frame(self.tabs)
        self.protection_tab = ttk.Frame(self.tabs)
        self.lab_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.compare_tab, text="Encode & Compare")
        self.tabs.add(self.inspect_tab, text="Inspect")
        self.tabs.add(self.protection_tab, text="Protection & History")
        self.tabs.add(self.lab_tab, text="Codec Lab")
        self.image_panes = []
        self.tab_panes = {}
        self._build_compare()
        self._build_inspect()
        self._build_protection()
        self._build_lab()

        ttk.Separator(self.root).pack(fill="x", pady=(SPACING["sm"], 0))

        statusbar = ttk.Frame(self.root, padding=(SPACING["lg"], SPACING["sm"] + 2))
        statusbar.pack(fill="x")
        self.status = tk.StringVar(value="Ready - open an image or WIMF file (Ctrl+O). Press F1 for the quick guide.")
        ttk.Label(statusbar, textvariable=self.status, style="Pane.TLabel", anchor="w").pack(
            side="left", fill="x", expand=True
        )
        ttk.Label(statusbar, text=f"WIMF {wimf.__version__}", style="Hint.TLabel").pack(side="right")

    def _refit_visible(self):
        frame = self.tabs.nametowidget(self.tabs.select())
        for pane in self.tab_panes.get(frame, []):
            pane.fit()

    def _build_header(self):
        """In-app brand header; the window buttons live in the native title bar above it."""
        palette = self.palette
        header = tk.Frame(self.root, background=palette["pane_bg"])
        header.pack(fill="x")
        logo = tk.Canvas(header, width=30, height=30, background=palette["pane_bg"], highlightthickness=0)
        logo.pack(side="left", padx=(SPACING["lg"] - 2, SPACING["md"]), pady=SPACING["md"])
        titles = tk.Frame(header, background=palette["pane_bg"])
        titles.pack(side="left")
        title_label = tk.Label(
            titles,
            text="WIMF Studio",
            background=palette["pane_bg"],
            foreground=palette["fg"],
            font=("Segoe UI", 12, "bold"),
            anchor="w",
        )
        title_label.pack(anchor="w")
        subtitle_label = tk.Label(
            titles,
            text="WIM2 hybrid image codec workbench",
            background=palette["pane_bg"],
            foreground=palette["muted"],
            font=("Segoe UI", 8),
            anchor="w",
        )
        subtitle_label.pack(anchor="w")
        actions = tk.Frame(header, background=palette["pane_bg"])
        actions.pack(side="right", padx=SPACING["lg"])
        menu_button = ttk.Menubutton(actions, text="Menu", style="Tool.TButton", direction="below", menu=self.app_menu)
        menu_button.pack(side="left", padx=(0, SPACING["sm"]), pady=SPACING["md"])
        self._tip(menu_button, "File, view and help commands.")
        settings_button = ttk.Button(actions, text="Settings", style="Tool.TButton", command=self.open_settings)
        settings_button.pack(side="left", padx=(0, SPACING["sm"]), pady=SPACING["md"])
        self._tip(settings_button, "Themes, behavior, encoding defaults and the codec core (Ctrl+,).")
        guide_button = ttk.Button(actions, text="Quick guide", style="Tool.TButton", command=self.show_welcome)
        guide_button.pack(side="left", pady=SPACING["md"])
        self._tip(guide_button, "Open the welcome window with the quick start (F1).")

        def restyle():
            live = self.palette
            for widget in (header, titles, actions):
                widget.configure(background=live["pane_bg"])
            logo.configure(background=live["pane_bg"])
            logo.delete("all")
            photo = ImageTk.PhotoImage(logo_image(30, live["fg"]))
            self._keep_photo(photo)
            logo.create_image(0, 0, image=photo, anchor="nw")
            title_label.configure(background=live["pane_bg"], foreground=live["fg"])
            subtitle_label.configure(background=live["pane_bg"], foreground=live["muted"])

        restyle()
        self.themable.append(restyle)

    def _build_tip_card(self):
        self.tip_card = self._card(self.compare_tab, padding=(12, 8))
        self.tip_card.pack(fill="x", padx=SPACING["lg"], pady=(SPACING["lg"], 0))
        row = self.tip_card.body
        chip = tk.Label(
            row,
            text="TIP",
            background=self.palette["accent"],
            foreground=self.palette["accent_text"],
            font=("Segoe UI", 8, "bold"),
            padx=7,
            pady=2,
        )
        chip.pack(side="left", padx=(0, 10))
        self.tip_text = tk.StringVar(value="")
        ttk.Label(row, textvariable=self.tip_text, anchor="w", justify="left").pack(side="left", fill="x", expand=True)
        shuffle_button = ttk.Button(row, text="Shuffle", style="Tool.TButton", command=self.shuffle_tip)
        shuffle_button.pack(side="left", padx=(8, 4))
        dismiss_button = ttk.Button(row, text="x", width=3, style="Tool.TButton", command=self.dismiss_tips)
        dismiss_button.pack(side="left")
        self._tip(shuffle_button, "Show another random tip.")
        self._tip(dismiss_button, "Hide tips (re-enable in Settings).")
        self._used_tips = []
        self.shuffle_tip()
        self.themable.append(
            lambda: chip.configure(background=self.palette["accent"], foreground=self.palette["accent_text"])
        )

    def shuffle_tip(self):
        remaining = [tip for tip in TIPS if tip not in self._used_tips]
        if not remaining:
            self._used_tips = []
            remaining = list(TIPS)
        tip = random.choice(remaining)
        self._used_tips.append(tip)
        self.tip_text.set(tip)

    def dismiss_tips(self):
        self.settings["show_tips"] = False
        self.settings.save()
        self.tip_card.pack_forget()
        self.status.set("Tips hidden - re-enable them in Settings (Ctrl+,).")

    def _build_compare(self):
        if self.settings["show_tips"]:
            self._build_tip_card()
        self.compare_top = ttk.Frame(
            self.compare_tab, padding=(SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["xs"])
        )
        self.compare_top.pack(fill="x")

        settings_card = self._card(self.compare_top, "Encode settings")
        settings_card.pack(side="left", fill="both", expand=True)
        grid = settings_card.body
        self.quality = tk.IntVar(value=7)
        self.lossless = tk.BooleanVar()
        self.preset = tk.StringVar(value="Balanced")
        self.codec = tk.StringVar(value="auto")
        self.threads = tk.StringVar(value="")
        quality_spin = ttk.Spinbox(grid, from_=1, to=10, width=6, textvariable=self.quality)
        preset_box = ttk.Combobox(
            grid, width=14, state="readonly", textvariable=self.preset, values=("Fast", "Balanced", "Extreme")
        )
        codec_box = ttk.Combobox(
            grid,
            width=14,
            state="readonly",
            textvariable=self.codec,
            values=("auto", "raw", "predictive", "palette", "wavelet"),
        )
        threads_entry = ttk.Entry(grid, width=8, textvariable=self.threads)
        rows = (
            ("Quality (1-10)", quality_spin, "Higher keeps more detail but produces larger files."),
            ("Preset", preset_box, "Speed versus search effort: Fast, Balanced or Extreme."),
            ("Codec", codec_box, "auto lets WIMF pick the best mode per tile."),
            ("Threads", threads_entry, "Worker threads for encoding. Leave empty for automatic."),
        )
        for row, (label, widget, tip) in enumerate(rows):
            ttk.Label(grid, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
            widget.grid(row=row, column=1, sticky="w", pady=SPACING["xs"])
            self._tip(widget, tip)
        lossless_check = ttk.Checkbutton(grid, text="Lossless (perfect reconstruction)", variable=self.lossless)
        lossless_check.grid(row=len(rows), column=0, columnspan=2, sticky="w", pady=(8, 0))
        self._tip(lossless_check, "Ignores quality and compresses slower, but decodes bit-exact.")
        grid.columnconfigure(1, weight=1)

        action_card = self._card(self.compare_top, "Run")
        action_card.pack(side="left", fill="y", padx=(10, 0))
        encode_button = ttk.Button(action_card.body, text="Encode", style="Accent.TButton", command=self.start_encode)
        encode_button.pack(fill="x", pady=(2, 6))
        self._tip(encode_button, "Compress the loaded image and measure quality (Ctrl+E).")
        ttk.Button(action_card.body, text="Cancel", command=self.jobs.cancel, state="disabled").pack(fill="x")
        ttk.Label(
            action_card.body,
            text="Runs in the background.\nCompare panels update\nautomatically.",
            style="Hint.TLabel",
            justify="center",
        ).pack(pady=(12, 0))

        results_card = self._card(self.compare_tab, "Results", padding=(12, 8))
        results_card.pack(fill="x", padx=SPACING["lg"], pady=(SPACING["sm"], SPACING["md"]))
        self.metrics_text = tk.StringVar(value="No comparison yet - encode to measure size, MSE and PSNR.")
        metrics_label = ttk.Label(results_card.body, textvariable=self.metrics_text, anchor="w", justify="left")
        metrics_label.pack(fill="x")
        self._tip(metrics_label, "Encoded size, ratio, error metrics, timings and per-mode tile counts.")
        self.compare_tab.bind(
            "<Configure>", lambda event: metrics_label.configure(wraplength=max(360, event.width - 64))
        )

        panes = ttk.Panedwindow(self.compare_tab, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=SPACING["lg"], pady=(0, SPACING["lg"]))
        self.source_pane = ImagePane(panes, "Source", self._palette, "File > Open... (Ctrl+O)")
        self.decoded_pane = ImagePane(panes, "Decoded", self._palette, "Run Encode to see the result here.")
        self.difference_pane = ImagePane(panes, "Difference", self._palette, "Exaggerated 8x after an encode.")
        compare_panes = [self.source_pane, self.decoded_pane, self.difference_pane]
        for pane in compare_panes:
            panes.add(pane, weight=1)
        self.image_panes.extend(compare_panes)
        self.tab_panes[self.compare_tab] = compare_panes

    def _build_inspect(self):
        split = ttk.Panedwindow(self.inspect_tab, orient="horizontal")
        split.pack(fill="both", expand=True, padx=SPACING["lg"], pady=SPACING["lg"])

        left = ttk.Frame(split)
        split.add(left, weight=4)
        legend_card = self._card(left, "Tile overlays", padding=(12, 7))
        legend_card.pack(fill="x", pady=(0, SPACING["sm"]))
        self.legend_body = ttk.Frame(legend_card.body)
        self.legend_body.pack(fill="x")
        self.inspect_pane = ImagePane(left, "Tile map", self._palette, "Encode or open a WIMF file to draw tiles.")
        self.inspect_pane.pack(fill="both", expand=True)
        self.image_panes.append(self.inspect_pane)
        self.tab_panes[self.inspect_tab] = [self.inspect_pane]

        right = ttk.Frame(split)
        split.add(right, weight=1)
        roi_card = self._card(right, "Region decode")
        roi_card.pack(fill="x")
        self.roi_x, self.roi_y = tk.IntVar(value=0), tk.IntVar(value=0)
        self.roi_w, self.roi_h = tk.IntVar(value=256), tk.IntVar(value=256)
        cells = (
            ("X", self.roi_x, "Left edge of the region to decode."),
            ("Y", self.roi_y, "Top edge of the region to decode."),
            ("Width", self.roi_w, "Region width in pixels."),
            ("Height", self.roi_h, "Region height in pixels."),
        )
        for index, (label, variable, tip) in enumerate(cells):
            row, column = divmod(index, 2)
            ttk.Label(roi_card.body, text=label).grid(row=row * 2, column=column, sticky="w", padx=(0, 8), pady=(4, 0))
            spin = ttk.Spinbox(roi_card.body, from_=0, to=1000000, width=9, textvariable=variable)
            spin.grid(row=row * 2 + 1, column=column, sticky="ew", padx=(0, 8), pady=2)
            self._tip(spin, tip)
        roi_card.body.columnconfigure(0, weight=1)
        roi_card.body.columnconfigure(1, weight=1)
        decode_button = ttk.Button(roi_card.body, text="Decode region only", command=self.decode_roi)
        decode_button.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self._tip(decode_button, "Fast partial decode: reads just the tiles inside this rectangle.")

        meta_card = self._card(right, "Metadata (JSON)")
        meta_card.pack(fill="both", expand=True, pady=(SPACING["sm"], 0))
        self.metadata_text = tk.Text(
            meta_card.body,
            width=30,
            height=14,
            wrap="none",
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.palette["border"],
            font=("Consolas", 9),
            undo=True,
        )
        self.metadata_text.pack(fill="both", expand=True)
        apply_button = ttk.Button(meta_card.body, text="Apply metadata", command=self.apply_metadata)
        apply_button.pack(fill="x", pady=(8, 0))
        self._tip(apply_button, "Rewrites metadata without recompressing any tile payloads.")

        def recolor_meta():
            self.metadata_text.configure(
                background=self.palette["surface"],
                foreground=self.palette["fg"],
                insertbackground=self.palette["fg"],
                highlightbackground=self.palette["border"],
            )

        self.themable.append(recolor_meta)
        recolor_meta()

    def _build_protection(self):
        container = ttk.Frame(self.protection_tab, padding=SPACING["lg"])
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1, uniform="protect")
        container.columnconfigure(1, weight=1, uniform="protect")
        container.rowconfigure(0, weight=1)

        anti_card = self._card(container, "Anti-rot protection")
        anti_card.grid(row=0, column=0, sticky="nsew", padx=(0, SPACING["sm"]))
        self.anti_rot = tk.BooleanVar()
        check = ttk.Checkbutton(
            anti_card.body, text="Enable anti-rot protection on next encode", variable=self.anti_rot
        )
        check.pack(anchor="w")
        self._tip(check, "Stores an AROT parity extension so corrupted files can be repaired automatically.")
        ttk.Label(
            anti_card.body,
            text="Parity travels inside the file. On load, WIMF verifies every tile checksum and repairs silently.",
            style="Hint.TLabel",
            wraplength=380,
            justify="left",
        ).pack(anchor="w", pady=(6, 10))
        ttk.Separator(anti_card.body).pack(fill="x", pady=6)
        self.protection_text = tk.StringVar(value="No WIMF document loaded.")
        ttk.Label(anti_card.body, textvariable=self.protection_text, justify="left").pack(anchor="w")

        history_card = self._card(container, "Chrono history")
        history_card.grid(row=0, column=1, sticky="nsew", padx=(SPACING["sm"], 0))
        ttk.Label(
            history_card.body,
            text="WIMF can keep chronological states inside one file. Browse and export any snapshot.",
            style="Hint.TLabel",
            wraplength=380,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))
        row = ttk.Frame(history_card.body)
        row.pack(anchor="w", fill="x")
        ttk.Label(row, text="State").pack(side="left")
        self.history_index = tk.IntVar(value=0)
        self.history_spin = ttk.Spinbox(row, from_=0, to=0, width=6, textvariable=self.history_index)
        self.history_spin.pack(side="left", padx=6)
        self._tip(self.history_spin, "Snapshot number to inspect.")
        ttk.Button(row, text="Show state", command=self.show_history).pack(side="left")
        ttk.Button(row, text="Export PNG...", command=self.export_history).pack(side="left", padx=6)

    def _build_lab(self):
        controls = ttk.Frame(self.lab_tab, padding=(SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["xs"]))
        controls.pack(fill="x")

        experiment_card = self._card(controls, "Corruption experiment")
        experiment_card.pack(side="left", fill="both", expand=True)
        self.lab_seed = tk.IntVar(value=0)
        self.lab_count = tk.IntVar(value=1)
        self.lab_area = tk.StringVar(value="payload")
        seed_spin = ttk.Spinbox(experiment_card.body, from_=0, to=2**31 - 1, width=10, textvariable=self.lab_seed)
        count_spin = ttk.Spinbox(experiment_card.body, from_=1, to=100, width=6, textvariable=self.lab_count)
        area_box = ttk.Combobox(
            experiment_card.body, state="readonly", width=12, values=AREAS, textvariable=self.lab_area
        )
        rows = (
            ("Seed", seed_spin, "Deterministic randomness: same seed, same damage."),
            ("Mutations", count_spin, "How many bytes to flip or overwrite."),
            ("Area", area_box, "Which container area to attack (header, payload, parity...)."),
        )
        for row_index, (label, widget, tip) in enumerate(rows):
            ttk.Label(experiment_card.body, text=label).grid(row=row_index, column=0, sticky="w", padx=(0, 10), pady=3)
            widget.grid(row=row_index, column=1, sticky="w", pady=3)
            self._tip(widget, tip)
        experiment_card.body.columnconfigure(1, weight=1)
        run_button = ttk.Button(
            experiment_card.body, text="Corrupt copy", style="Accent.TButton", command=self.run_corruption
        )
        run_button.grid(row=len(rows), column=0, columnspan=2, sticky="ew", pady=(10, 2))
        self._tip(run_button, "Damages a copy of the encoded file and tests strict recovery against it.")

        transport_card = self._card(controls, "Base64 transport")
        transport_card.pack(side="left", fill="both", expand=True, padx=(SPACING["lg"], 0))
        buttons = (
            ("Copy Base64", lambda: self.copy_base64(), "Copy the whole WIMF file as wrapped Base64 text."),
            (
                "Copy data URL",
                lambda: self.copy_base64(data_url=True),
                "Copy as a data: URL ready to paste into HTML/CSS.",
            ),
            ("Paste Base64", self.paste_base64, "Import a WIMF file from Base64 text on the clipboard."),
            ("Export damaged...", self.export_damaged, "Save the last corrupted copy produced above."),
        )
        for index, (text, command, tip) in enumerate(buttons):
            row, column = divmod(index, 2)
            button = ttk.Button(transport_card.body, text=text, command=command)
            button.grid(row=row, column=column, sticky="ew", padx=3, pady=3)
            self._tip(button, tip)
        transport_card.body.columnconfigure(0, weight=1)
        transport_card.body.columnconfigure(1, weight=1)

        self.lab_status = tk.StringVar(
            value="Strict decoder stays enabled - previews mark failed tiles with a checkerboard."
        )
        ttk.Label(self.lab_tab, textvariable=self.lab_status, style="Hint.TLabel").pack(
            anchor="w", padx=SPACING["xl"], pady=(0, SPACING["sm"])
        )

        panes = ttk.Panedwindow(self.lab_tab, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=SPACING["lg"], pady=(0, SPACING["lg"]))
        self.lab_original = ImagePane(panes, "Original", self._palette, "Shows the currently loaded source image.")
        self.lab_preview = ImagePane(
            panes, "UNSAFE corruption preview", self._palette, "Run 'Corrupt copy' to preview damage."
        )
        self.lab_recovered = ImagePane(
            panes, "Strict decode / recovery", self._palette, "Result of the strict decoder on the damaged copy."
        )
        lab_panes = [self.lab_original, self.lab_preview, self.lab_recovered]
        for pane in lab_panes:
            panes.add(pane, weight=1)
        self.image_panes.extend(lab_panes)
        self.tab_panes[self.lab_tab] = lab_panes

    # -------------------------------------------------------- recent files

    def _load_recent(self):
        try:
            values = json.loads(RECENT_FILE.read_text(encoding="utf-8"))
            return [value for value in values if isinstance(value, str) and Path(value).exists()][:10]
        except (OSError, ValueError):
            return []

    def _fill_recent(self, menu):
        menu.delete(0, "end")
        if not self.recent:
            menu.add_command(label="No recent files", state="disabled")
            return
        for path in self.recent:
            menu.add_command(label=path, command=lambda value=path: self._open_recent(value))

    def _open_recent(self, path):
        if self.confirm_discard():
            self.open_path(path)

    def _remember(self, path):
        value = str(Path(path).resolve())
        self.recent = [value] + [item for item in self.recent if item != value][:9]
        try:
            RECENT_FILE.write_text(json.dumps(self.recent), encoding="utf-8")
        except OSError:
            pass

    # --------------------------------------------------------- document IO

    def _dialog(self, **kwargs):
        dialog = StudioDialog(self, **kwargs)
        dialog.wait_window()
        return dialog

    def info(self, title, message, detail=None):
        self._dialog(title=title, message=message, detail=detail, buttons=(("Close", True, "accent"),))

    def error(self, title, message):
        self._dialog(title=title, message=message, buttons=(("Close", True, "accent"),))

    def confirm_discard(self):
        if not self.document.dirty:
            return True
        if not self.settings["confirm_close"]:
            return True
        dialog = self._dialog(
            title="Unsaved changes",
            message="The current WIMF document has unsaved changes.",
            detail="What would you like to do before continuing?",
            buttons=(("Cancel", "cancel", ""), ("Save changes", "save", "accent"), ("Discard changes", "discard", "")),
            checkbox=("Always discard without asking", False),
        )
        if dialog.checkbox_value and dialog.result in ("discard", "cancel"):
            self.settings["confirm_close"] = False
            self.settings["close_discard"] = dialog.result == "discard"
            self.settings.save()
        if dialog.result in (None, "cancel"):
            return False
        if dialog.result == "save":
            self.save()
            return not self.document.dirty
        return True

    def open_file(self):
        if not self.confirm_discard():
            return
        path = filedialog.askopenfilename(
            parent=self.root,
            filetypes=(
                ("Images", "*.wimf *.wif *.awif *.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),
                ("All files", "*.*"),
            ),
        )
        if path:
            self.open_path(path)

    def open_path(self, path):
        try:
            self.document = StudioDocument.open(path)
            self._remember(path)
            self._refresh_document()
            name = Path(path).name
            self.status.set(f"Opened {name} - press Encode (Ctrl+E) to compress, then compare Source vs Decoded.")
            self.root.title(f"WIMF Studio - {name}")
        except Exception as error:
            self.error("Open failed", f"The file could not be opened.\n\n{error}")

    def _refresh_document(self):
        source = _display_array(self.document.source) if self.document.source is not None else None
        decoded = _display_array(self.document.decoded) if self.document.decoded is not None else None
        self.source_pane.set_image(source)
        self.decoded_pane.set_image(decoded)
        self.difference_pane.set_image(None)
        self.lab_original.set_image(source)
        self.lab_preview.set_image(None)
        self.lab_recovered.set_image(None)

        overlays, modes = [], []
        if self.document.encoded and self.document.details.get("format") == "WIM2":
            from .hybrid import MODE_NAMES, parse_v2

            for entry in parse_v2(self.document.encoded)["entries"]:
                name = MODE_NAMES[entry[4]]
                overlays.append((entry[0], entry[1], entry[2], entry[3], MODE_COLORS[name]))
                modes.append(name)
        self._tile_overlays, self._tile_modes = overlays, modes
        self.inspect_pane.set_image(decoded if decoded is not None else source, overlays)
        self._rebuild_tile_legend(modes)

        self.metadata_text.delete("1.0", "end")
        self.metadata_text.insert("1.0", json.dumps(self.document.metadata, indent=2, sort_keys=True))
        details = self.document.details
        self.protection_text.set(
            f"Protected: {'yes' if details.get('protected') else 'no'}\n"
            f"Repaired while opening: {'yes' if details.get('repaired') else 'no'}\n"
            f"Chrono states: {details.get('history_states', 1)}"
        )
        states = max(0, int(details.get("history_states", 1)) - 1)
        self.history_spin.configure(to=states)
        if self.history_index.get() > states:
            self.history_index.set(states)
        self.metrics_text.set("No comparison yet - encode to measure size, MSE and PSNR.")

    def _rebuild_tile_legend(self, modes):
        for child in self.legend_body.winfo_children():
            child.destroy()
        self.tile_vars.clear()
        counts = Counter(modes)
        ordered = [name for name in MODE_COLORS if counts[name]]
        if not ordered:
            ttk.Label(self.legend_body, text="Encode a WIM2 file to see per-tile codec overlays.").pack(side="left")
            return
        for name in ordered:
            var = tk.BooleanVar(value=True)
            self.tile_vars[name] = var
            tk.Canvas(
                self.legend_body,
                width=12,
                height=12,
                bg=MODE_COLORS[name],
                highlightthickness=1,
                highlightbackground=self.palette["border"],
            ).pack(side="left", padx=(0, 4))
            ttk.Checkbutton(
                self.legend_body, text=f"{name} ({counts[name]})", variable=var, command=self._apply_tile_filter
            ).pack(side="left", padx=(0, 12))
        ttk.Label(self.legend_body, text=f"{len(modes)} tiles", style="Hint.TLabel").pack(side="right")

    def _apply_tile_filter(self):
        overlays = [
            overlay
            for overlay, mode in zip(self._tile_overlays, self._tile_modes, strict=True)
            if self.tile_vars[mode].get()
        ]
        self.inspect_pane.set_overlays(overlays)

    # -------------------------------------------------------------- encode

    def start_encode(self):
        try:
            threads = int(self.threads.get()) if self.threads.get().strip() else None
            settings = EncodeSettings(
                self.quality.get(),
                self.lossless.get(),
                self.preset.get(),
                self.codec.get(),
                threads,
                self.anti_rot.get(),
            )
            self.jobs.submit("encode", self.document.encode, settings)
            self.status.set("Encoding in the background...")
        except Exception as error:
            self.error("Encode failed", f"The encode could not be started.\n\n{error}")

    def _finish_encode(self, payload):
        self.document.apply_encode_result(payload)
        self._refresh_document()
        difference = self.document.metrics["difference"]
        shown = ImageEnhance.Contrast(_display_array(difference)).enhance(8)
        self.difference_pane.set_image(shown)
        psnr = self.document.metrics["psnr"]
        modes = ", ".join(
            f"{name[0].upper()}:{count}" for name, count in self.document.details.get("tile_modes", {}).items() if count
        )
        self.metrics_text.set(
            f"{self.document.metrics['encoded_bytes']:,} B ({self.document.metrics['ratio']:.3f}x) | "
            f"MSE {self.document.metrics['mse']:.3f} | "
            f"max {self.document.metrics['maximum_error']} | "
            f"PSNR {'inf' if math.isinf(psnr) else f'{psnr:.2f} dB'} | "
            f"enc {self.document.metrics['encode_seconds']:.3f}s / dec {self.document.metrics['decode_seconds']:.3f}s"
            f" | {modes}"
        )
        self.status.set("Encode completed - use File > Save (Ctrl+S) to write the .wimf file.")

    def _poll_jobs(self):
        token = self.jobs.token
        if self.jobs.running and token is not None and token.total:
            if self.progress_mode != "determinate":
                self.progress.stop()
                self.progress.configure(mode="determinate", maximum=max(1, token.total))
                self.progress_mode = "determinate"
            completed = int(token.completed)
            if completed != self._last_progress:
                self.progress.configure(value=completed)
                self._last_progress = completed
            stage = f"{token.stage}: {token.completed}/{token.total}"
            if stage != self._last_stage:
                self.status.set(stage)
                self._last_stage = stage
        while True:
            try:
                kind, name, payload = self.jobs.events.get_nowait()
            except Exception:
                break
            if kind == "started":
                if self.progress_mode != "indeterminate":
                    self.progress.configure(mode="indeterminate", value=0)
                    self.progress.start(12)
                    self.progress_mode = "indeterminate"
                self._last_progress = -1
                self._last_stage = ""
                self.cancel_button.configure(state="normal")
                self.status.set(f"Running {name}...")
            else:
                self.progress.stop()
                self.progress_mode = "idle"
                self._last_progress = -1
                self._last_stage = ""
                self.progress.configure(mode="determinate", value=0)
                self.cancel_button.configure(state="disabled")
                if kind == "completed" and name == "encode":
                    self._finish_encode(payload)
                elif kind == "failed":
                    self.error(f"{name.title()} failed", payload)
                    self.status.set(payload)
                else:
                    self.status.set("Operation cancelled")
        self.root.after(80, self._poll_jobs)

    # ---------------------------------------------------------------- save

    def save(self, as_new=False):
        if not self.document.encoded:
            self.info("Nothing to save", "Encode the document first - press Encode (Ctrl+E).")
            return
        path = (
            None
            if as_new or not self.document.path or self.document.path.suffix.lower() not in (".wimf", ".wif")
            else self.document.path
        )
        if path is None:
            selected = filedialog.asksaveasfilename(
                parent=self.root, defaultextension=".wimf", filetypes=(("WIMF", "*.wimf"),)
            )
            if not selected:
                return
            path = Path(selected)
        Path(path).write_bytes(self.document.encoded)
        self.document.path = Path(path)
        self.document.dirty = False
        self._remember(path)
        self.status.set(f"Saved {path}")

    # ----------------------------------------------- metadata, ROI, history

    def apply_metadata(self):
        try:
            metadata = json.loads(self.metadata_text.get("1.0", "end"))
            if not isinstance(metadata, dict):
                raise ValueError("metadata must be a JSON object")
            self.document.metadata = metadata
            if self.document.encoded and self.document.details.get("format") == "WIM2":
                self.document.encoded = wimf.rewrite_metadata(self.document.encoded, metadata)
                self.document.details = wimf.inspect(self.document.encoded)
                self.status.set("Metadata updated without recompressing tile payloads.")
            else:
                self.status.set("Metadata changed; encode to create a WIMF container.")
            self.document.dirty = True
        except Exception as error:
            self.error("Invalid metadata", f"The metadata is not valid JSON for this container.\n\n{error}")

    def decode_roi(self):
        try:
            if not self.document.encoded:
                raise ValueError("encode or open a WIMF file first")
            reference = self.document.decoded if self.document.decoded is not None else self.document.source
            if reference is None:
                raise ValueError("nothing to decode")
            height, width = reference.shape[0], reference.shape[1]
            x, y = self.roi_x.get(), self.roi_y.get()
            roi_w, roi_h = self.roi_w.get(), self.roi_h.get()
            if roi_w <= 0 or roi_h <= 0:
                raise ValueError("region width and height must be positive")
            if x < 0 or y < 0 or x + roi_w > width or y + roi_h > height:
                raise ValueError(f"region exceeds the image bounds ({width} x {height})")
            image = wimf.decode(self.document.encoded, roi=(x, y, roi_w, roi_h))
            self.inspect_pane.set_image(image.pil)
            self.status.set(f"Decoded region {roi_w} x {roi_h} at ({x}, {y}).")
        except Exception as error:
            self.error("Region decode failed", f"The region could not be decoded.\n\n{error}")

    # ------------------------------------------------------------ codec lab

    def run_corruption(self):
        try:
            if not self.document.encoded:
                raise ValueError("encode or open a WIMF file first")
            damaged = corrupt(
                self.document.encoded, seed=self.lab_seed.get(), count=self.lab_count.get(), area=self.lab_area.get()
            )
            self.damaged = damaged
            report = diagnose(damaged)
            preview, failed = unsafe_preview(damaged)
            self.lab_preview.set_image(_display_array(preview))
            if report["strict_ok"]:
                recovered = wimf.decode(damaged)
                self.lab_recovered.set_image(recovered.pil)
            else:
                self.lab_recovered.set_image(None)
            recovery = "repaired" if report.get("repaired") else ("valid" if report["strict_ok"] else "rejected")
            self.lab_status.set(f"Strict: {recovery} | failed source tiles: {len(failed)}")
        except Exception as error:
            self.lab_status.set(f"Rejected: {error}")

    def copy_base64(self, data_url=False):
        if not self.document.encoded:
            self.info("No WIMF data", "Encode or open a WIMF file first.")
            return
        value = wimf.to_data_url(self.document.encoded) if data_url else wimf.to_base64(self.document.encoded, wrap=76)
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.lab_status.set(f"Copied {len(value):,} Base64 characters")

    def paste_base64(self):
        try:
            value = self.root.clipboard_get()
            payload = wimf.from_data_url(value) if value.lstrip().startswith("data:") else wimf.from_base64(value)
            if not wimf.is_wimf(payload):
                raise ValueError("clipboard Base64 is not WIMF")
            image = wimf.decode(payload)
            self.document = StudioDocument(
                source=image.to_numpy().copy(),
                encoded=payload,
                decoded=image.to_numpy().copy(),
                metadata=dict(image.metadata),
                details=wimf.inspect(payload),
                dirty=True,
            )
            self._refresh_document()
            self.lab_status.set(f"Imported {len(payload):,} WIMF bytes from Base64")
        except Exception as error:
            self.error("Base64 import failed", f"The clipboard text is not a valid WIMF payload.\n\n{error}")

    def export_damaged(self):
        if not getattr(self, "damaged", None):
            self.info("No damaged copy", "Run a corruption experiment first - press Corrupt copy.")
            return
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".wimf", filetypes=(("WIMF", "*.wimf"),))
        if path:
            Path(path).write_bytes(self.damaged)

    # ------------------------------------------------------ history, help

    def show_history(self):
        try:
            decoder = wimf.WIMFDecoder(self.document.encoded)
            self.inspect_pane.set_image(decoder.decode_chrono_state(self.history_index.get()).pil)
            self.tabs.select(self.inspect_tab)
        except Exception as error:
            self.error("History decode failed", f"The snapshot could not be decoded.\n\n{error}")

    def export_history(self):
        try:
            decoder = wimf.WIMFDecoder(self.document.encoded)
            image = decoder.decode_chrono_state(self.history_index.get()).pil
            path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".png")
            if path:
                image.save(path)
        except Exception as error:
            self.error("History export failed", f"The snapshot could not be exported.\n\n{error}")

    def show_runtime(self):
        info = wimf.runtime_info()
        native = bool(info.get("native"))
        policies = ", ".join(info.get("execution_policies", []) or ["-"])
        rows = (
            ("Codec version", info.get("codec_version", "-")),
            ("Backend", "Native C++ core" if native else "Python reference core"),
            ("SIMD path", info.get("simd", "-")),
            ("Native orchestration", "yes" if info.get("native_orchestration") else "no"),
            ("Hardware threads", info.get("hardware_threads", "-")),
            ("Effective threads", info.get("effective_threads", "-")),
            ("Zstandard", info.get("zstandard_version", "-")),
            ("Architecture", info.get("architecture", "-")),
            ("Execution policies", policies),
        )
        payload = json.dumps(info, indent=2, default=str)

        def copy_json():
            self.root.clipboard_clear()
            self.root.clipboard_append(payload)
            self.status.set("Runtime information copied to the clipboard as JSON.")
            for dialog in list(self.dialogs):
                if isinstance(dialog, StudioDialog):
                    dialog.flash_button("Copy JSON", "Copied!", "Copy JSON")

        self._dialog(
            title="WIMF runtime",
            message="Active codec engine and environment.",
            rows=rows,
            code_detail=payload,
            buttons=(("Close", True, "accent"), ("Copy JSON", copy_json, "")),
            default=0,
        )

    def show_welcome(self):
        for dialog in list(self.dialogs):
            if isinstance(dialog, WelcomeWindow):
                dialog.deiconify()
                dialog.lift()
                dialog.focus_set()
                return
        WelcomeWindow(self)

    def show_about(self):
        self.info(
            "About WIMF Studio",
            f"WIMF Studio {wimf.__version__}",
            detail="Encoder, inspector and corruption lab for the WIM2 hybrid image codec.",
        )

    def report_bug(self):
        details = {
            "wimf_version": wimf.__version__,
            "runtime": wimf.runtime_info(),
            "document": self.document.details,
        }
        report = "WIMF bug report diagnostics\n\n" + json.dumps(details, indent=2, default=str)
        self.root.clipboard_clear()
        self.root.clipboard_append(report)
        webbrowser.open(ISSUES_URL)
        self.info(
            "Report a Bug",
            "Runtime diagnostics were copied to your clipboard.",
            detail="Paste them into the GitHub issue and attach a minimal sample file when possible.",
        )

    def close(self):
        if self.confirm_discard():
            self.jobs.close()
            self.root.destroy()


def launch(path=None):
    _enable_dpi_awareness()
    root = tk.Tk()
    app = WIMFStudio(root, path)
    root.attributes("-alpha", 0)
    if app.settings["show_welcome"] and not path:
        root.after(400, app.show_welcome)
    root.after(60, lambda: fade_in(root, 200, 0))
    root.mainloop()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Open WIMF Studio.")
    parser.add_argument("path", nargs="?")
    args = parser.parse_args(argv)
    launch(args.path)


if __name__ == "__main__":
    main()
