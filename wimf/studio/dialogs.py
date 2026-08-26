"""Themed Studio windows: message dialogs, the welcome flow and the settings surface."""

import tkinter as tk
from tkinter import ttk

import wimf

from ..studio_settings import CODECS, CORE_MODES, DEFAULTS, QUALITY_PRESETS, SETTINGS_FILE
from ..studio_theme import PALETTES, SPACING, THEME_NAMES
from .widgets import Card, TitleBar, _destroy_quietly, fade_in, fade_out

WELCOME_STEPS = (
    ("Open", "Load any PNG/JPEG/WebP image - or an existing .wimf file (Ctrl+O)."),
    ("Encode", "Keep the defaults and press Encode (Ctrl+E). It runs in the background."),
    ("Compare", "Source, Decoded and an 8x-exaggerated Difference appear side by side."),
    ("Inspect", "The tile map shows which codec every tile picked, with region decode."),
    ("Save", "Write your .wimf file (Ctrl+S). Protection and history travel inside it."),
)


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
        self.update()
        width, height = self.winfo_reqwidth(), self.winfo_reqheight()
        parent = app.root
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 3)
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.update()
        self.lift()
        self.focus_set()
        try:
            self.grab_set()
        except Exception:
            pass
        fade_in(self, 150)
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
        self.update()
        width, height = self.winfo_reqwidth(), self.winfo_reqheight()
        height = min(height, app.root.winfo_screenheight() - 120)
        x = app.root.winfo_rootx() + max(0, (app.root.winfo_width() - width) // 2)
        y = app.root.winfo_rooty() + max(0, (app.root.winfo_height() - height) // 4)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.deiconify()
        self.update()
        self.lift()
        fade_in(self, 170)
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
        self.update()
        width = max(self.winfo_reqwidth(), 560)
        height = min(self.winfo_reqheight(), app.root.winfo_screenheight() - 100)
        x = app.root.winfo_rootx() + max(0, (app.root.winfo_width() - width) // 2)
        y = app.root.winfo_rooty() + max(0, (app.root.winfo_height() - height) // 4)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.deiconify()
        self.update()
        self.lift()
        fade_in(self, 170)
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
