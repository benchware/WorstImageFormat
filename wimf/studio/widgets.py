"""Studio widget toolkit: window chrome, fades, tooltips, cards, title bars and image panes."""

import ctypes
import math
import sys
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from ..studio_assets import logo_image
from ..studio_theme import FONTS, SPACING, mix_hex, sv_ttk

ZOOM_MIN, ZOOM_MAX, ZOOM_STEP, FIT_MAX = 0.01, 32.0, 1.25, 8.0


def _fallback_palette():
    from ..studio_theme import resolve

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


def _destroy_quietly(window):
    try:
        window.destroy()
    except tk.TclError:
        pass
