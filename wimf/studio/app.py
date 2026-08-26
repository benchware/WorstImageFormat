"""WIMF Studio application shell: main window, jobs polling and entry points."""

import argparse
import json
import math
import random
import tkinter as tk
import webbrowser
from collections import Counter
from pathlib import Path
from tkinter import filedialog, ttk

from PIL import ImageEnhance, ImageTk

import wimf

from .. import hybrid as _hybrid
from ..diagnostics import AREAS, corrupt, diagnose, unsafe_preview
from ..studio_assets import logo_image
from ..studio_model import EncodeSettings, JobController, StudioDocument
from ..studio_settings import TIPS, StudioSettings
from ..studio_theme import PALETTES, SIZES, SPACING, THEME_NAMES, sv_ttk
from .dialogs import SettingsWindow, StudioDialog, WelcomeWindow
from .images import _display_array
from .widgets import (
    Card,
    ImagePane,
    ToolTip,
    _apply_window_chrome,
    _configure_named_styles,
    _enable_dpi_awareness,
    _sync_scaling,
    fade_in,
)

MODE_COLORS = {"raw": "#9aa0a6", "predictive": "#34a853", "palette": "#fbbc04", "wavelet": "#4285f4"}
RECENT_FILE = Path.home() / ".wimf-studio-recent.json"
ISSUES_URL = "https://github.com/benchware/WorstImageFormat/issues/new/choose"

ZOOM_MIN, ZOOM_MAX, ZOOM_STEP, FIT_MAX = 0.01, 32.0, 1.25, 8.0
WINDOW_MIN = SIZES["window_min"]

_ORIGINAL_NATIVE = _hybrid.native


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
