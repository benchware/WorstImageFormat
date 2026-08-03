"""WIMF Studio: lightweight Tkinter encoder, inspector, and codec lab."""

import argparse
import json
import math
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import numpy as np
from PIL import Image, ImageEnhance, ImageTk

import wimf

from .diagnostics import AREAS, corrupt, diagnose, unsafe_preview
from .studio_model import EncodeSettings, JobController, StudioDocument

MODE_COLORS = {"raw": "#9aa0a6", "predictive": "#34a853", "palette": "#fbbc04", "wavelet": "#4285f4"}
RECENT_FILE = Path.home() / ".wimf-studio-recent.json"
ISSUES_URL = "https://github.com/benchware/WorstImageFormat/issues/new/choose"


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


class ImagePane(ttk.Frame):
    def __init__(self, parent, title):
        super().__init__(parent)
        ttk.Label(self, text=title, style="Heading.TLabel").pack(anchor="w", padx=6, pady=(4, 0))
        self.canvas = tk.Canvas(self, background="#15171a", highlightthickness=0, width=280, height=220)
        self.canvas.pack(fill="both", expand=True, padx=4, pady=4)
        self.image = None
        self.photo = None
        self.zoom = 1.0
        self.overlays = []
        self.canvas.bind("<MouseWheel>", self._zoom)
        self.canvas.bind("<ButtonPress-1>", lambda event: self.canvas.scan_mark(event.x, event.y))
        self.canvas.bind("<B1-Motion>", lambda event: self.canvas.scan_dragto(event.x, event.y, gain=1))

    def set_image(self, image, overlays=None):
        self.image = image.copy() if image is not None else None
        self.overlays = overlays or []
        self.fit()

    def fit(self):
        if self.image is None:
            self.canvas.delete("all")
            return
        self.update_idletasks()
        self.zoom = min(
            1.0,
            max(
                0.01,
                min(
                    max(1, self.canvas.winfo_width()) / self.image.width,
                    max(1, self.canvas.winfo_height()) / self.image.height,
                ),
            ),
        )
        self.redraw()

    def actual(self):
        self.zoom = 1.0
        self.redraw()

    def _zoom(self, event):
        self.zoom = max(0.01, min(32.0, self.zoom * (1.2 if event.delta > 0 else 1 / 1.2)))
        self.redraw()

    def redraw(self):
        if self.image is None:
            return
        size = (max(1, round(self.image.width * self.zoom)), max(1, round(self.image.height * self.zoom)))
        method = Image.Resampling.LANCZOS if self.zoom < 1 else Image.Resampling.NEAREST
        self.photo = ImageTk.PhotoImage(self.image.resize(size, method))
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        for overlay in self.overlays:
            x, y, width, height, color = overlay
            self.canvas.create_rectangle(
                x * self.zoom, y * self.zoom, (x + width) * self.zoom, (y + height) * self.zoom, outline=color, width=2
            )
        self.canvas.configure(scrollregion=(0, 0, *size))


class WIMFStudio:
    def __init__(self, root, path=None):
        self.root = root
        self.root.title("WIMF Studio")
        self.root.geometry("1180x760")
        self.document = StudioDocument()
        self.jobs = JobController()
        self.recent = self._load_recent()
        self._build_style()
        self._build_menu()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(80, self._poll_jobs)
        if path:
            self.open_path(path)

    def _build_style(self):
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Heading.TLabel", font=("Segoe UI", 10, "bold"))

    def _build_menu(self):
        menu = tk.Menu(self.root)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Open...", command=self.open_file, accelerator="Ctrl+O")
        file_menu.add_command(label="Save WIMF", command=self.save, accelerator="Ctrl+S")
        file_menu.add_command(label="Save WIMF As...", command=lambda: self.save(as_new=True))
        self.recent_menu = tk.Menu(file_menu, tearoff=False)
        file_menu.add_cascade(label="Open Recent", menu=self.recent_menu)
        self._refresh_recent_menu()
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.close)
        menu.add_cascade(label="File", menu=file_menu)
        view_menu = tk.Menu(menu, tearoff=False)
        view_menu.add_command(label="Fit all", command=lambda: [pane.fit() for pane in self.image_panes])
        view_menu.add_command(label="Actual size", command=lambda: [pane.actual() for pane in self.image_panes])
        view_menu.add_command(label="Runtime information", command=self.show_runtime)
        menu.add_cascade(label="View", menu=view_menu)
        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="Report a Bug...", command=self.report_bug)
        menu.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menu)
        self.root.bind("<Control-o>", lambda _event: self.open_file())
        self.root.bind("<Control-s>", lambda _event: self.save())

    def _load_recent(self):
        try:
            values = json.loads(RECENT_FILE.read_text(encoding="utf-8"))
            return [value for value in values if isinstance(value, str) and Path(value).exists()][:10]
        except (OSError, ValueError):
            return []

    def _refresh_recent_menu(self):
        self.recent_menu.delete(0, "end")
        if not self.recent:
            self.recent_menu.add_command(label="No recent files", state="disabled")
        for path in self.recent:
            self.recent_menu.add_command(label=path, command=lambda value=path: self._open_recent(value))

    def _open_recent(self, path):
        if self.confirm_discard():
            self.open_path(path)

    def _remember(self, path):
        value = str(Path(path).resolve())
        self.recent = [value] + [item for item in self.recent if item != value][:9]
        self._refresh_recent_menu()
        try:
            RECENT_FILE.write_text(json.dumps(self.recent), encoding="utf-8")
        except OSError:
            pass

    def _build_ui(self):
        toolbar = ttk.Frame(self.root, padding=6)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Open", command=self.open_file).pack(side="left")
        ttk.Button(toolbar, text="Encode", command=self.start_encode).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Save", command=self.save).pack(side="left")
        self.cancel_button = ttk.Button(toolbar, text="Cancel", command=self.jobs.cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=4)
        self.progress = ttk.Progressbar(toolbar, mode="indeterminate", length=180)
        self.progress.pack(side="right")

        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True)
        self.compare_tab = ttk.Frame(self.tabs)
        self.inspect_tab = ttk.Frame(self.tabs)
        self.protection_tab = ttk.Frame(self.tabs)
        self.lab_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.compare_tab, text="Encode & Compare")
        self.tabs.add(self.inspect_tab, text="Inspect")
        self.tabs.add(self.protection_tab, text="Protection & History")
        self.tabs.add(self.lab_tab, text="Codec Lab")
        self._build_compare()
        self._build_inspect()
        self._build_protection()
        self._build_lab()

        self.status = tk.StringVar(value="Open an image or WIMF file to begin.")
        ttk.Label(self.root, textvariable=self.status, relief="sunken", anchor="w").pack(fill="x")

    def _build_compare(self):
        controls = ttk.Frame(self.compare_tab, padding=6)
        controls.pack(fill="x")
        self.quality = tk.IntVar(value=7)
        self.lossless = tk.BooleanVar()
        self.preset = tk.StringVar(value="Balanced")
        self.codec = tk.StringVar(value="auto")
        self.threads = tk.StringVar(value="")
        for label, widget in (
            ("Quality", ttk.Spinbox(controls, from_=1, to=10, width=4, textvariable=self.quality)),
            (
                "Preset",
                ttk.Combobox(
                    controls,
                    width=10,
                    state="readonly",
                    textvariable=self.preset,
                    values=("Fast", "Balanced", "Extreme"),
                ),
            ),
            (
                "Codec",
                ttk.Combobox(
                    controls,
                    width=10,
                    state="readonly",
                    textvariable=self.codec,
                    values=("auto", "raw", "predictive", "palette", "wavelet"),
                ),
            ),
            ("Threads", ttk.Entry(controls, width=5, textvariable=self.threads)),
        ):
            ttk.Label(controls, text=label).pack(side="left", padx=(6, 2))
            widget.pack(side="left")
        ttk.Checkbutton(controls, text="Lossless", variable=self.lossless).pack(side="left", padx=8)
        ttk.Button(controls, text="Encode", command=self.start_encode).pack(side="left")
        self.metrics_text = tk.StringVar(value="No comparison yet")
        ttk.Label(controls, textvariable=self.metrics_text).pack(side="right")

        panes = ttk.Panedwindow(self.compare_tab, orient="horizontal")
        panes.pack(fill="both", expand=True)
        self.source_pane = ImagePane(panes, "Source")
        self.decoded_pane = ImagePane(panes, "Decoded")
        self.difference_pane = ImagePane(panes, "Difference")
        for pane in (self.source_pane, self.decoded_pane, self.difference_pane):
            panes.add(pane, weight=1)
        self.image_panes = [self.source_pane, self.decoded_pane, self.difference_pane]

    def _build_inspect(self):
        split = ttk.Panedwindow(self.inspect_tab, orient="horizontal")
        split.pack(fill="both", expand=True)
        left = ttk.Frame(split)
        right = ttk.Frame(split, padding=8)
        split.add(left, weight=3)
        split.add(right, weight=1)
        self.inspect_pane = ImagePane(left, "Tile map")
        self.inspect_pane.pack(fill="both", expand=True)
        self.image_panes.append(self.inspect_pane)
        ttk.Label(right, text="ROI: X Y WIDTH HEIGHT", style="Heading.TLabel").pack(anchor="w")
        self.roi = tk.StringVar()
        ttk.Entry(right, textvariable=self.roi).pack(fill="x", pady=4)
        ttk.Button(right, text="Decode ROI", command=self.decode_roi).pack(fill="x")
        ttk.Label(right, text="Metadata (JSON)", style="Heading.TLabel").pack(anchor="w", pady=(14, 2))
        self.metadata_text = tk.Text(right, width=34, height=18, wrap="none")
        self.metadata_text.pack(fill="both", expand=True)
        ttk.Button(right, text="Apply metadata", command=self.apply_metadata).pack(fill="x", pady=4)

    def _build_protection(self):
        panel = ttk.Frame(self.protection_tab, padding=16)
        panel.pack(fill="both", expand=True)
        self.anti_rot = tk.BooleanVar()
        ttk.Checkbutton(panel, text="Enable anti-rot protection on next encode", variable=self.anti_rot).pack(
            anchor="w"
        )
        self.protection_text = tk.StringVar(value="No WIMF document loaded.")
        ttk.Label(panel, textvariable=self.protection_text, justify="left").pack(anchor="w", pady=12)
        row = ttk.Frame(panel)
        row.pack(anchor="w")
        ttk.Label(row, text="Chrono state").pack(side="left")
        self.history_index = tk.IntVar(value=0)
        ttk.Spinbox(row, from_=0, to=0, width=6, textvariable=self.history_index).pack(side="left", padx=6)
        ttk.Button(row, text="Show state", command=self.show_history).pack(side="left")
        ttk.Button(row, text="Export state...", command=self.export_history).pack(side="left", padx=6)

    def _build_lab(self):
        controls = ttk.Frame(self.lab_tab, padding=6)
        controls.pack(fill="x")
        self.lab_seed = tk.IntVar(value=0)
        self.lab_count = tk.IntVar(value=1)
        self.lab_area = tk.StringVar(value="payload")
        ttk.Label(controls, text="Seed").pack(side="left")
        ttk.Spinbox(controls, from_=0, to=2**31 - 1, width=8, textvariable=self.lab_seed).pack(side="left")
        ttk.Label(controls, text="Mutations").pack(side="left", padx=(8, 2))
        ttk.Spinbox(controls, from_=1, to=100, width=5, textvariable=self.lab_count).pack(side="left")
        ttk.Label(controls, text="Area").pack(side="left", padx=(8, 2))
        ttk.Combobox(controls, state="readonly", width=10, values=AREAS, textvariable=self.lab_area).pack(side="left")
        ttk.Button(controls, text="Corrupt copy", command=self.run_corruption).pack(side="left", padx=8)
        ttk.Button(controls, text="Copy Base64", command=self.copy_base64).pack(side="left")
        ttk.Button(controls, text="Copy data URL", command=lambda: self.copy_base64(data_url=True)).pack(
            side="left", padx=4
        )
        ttk.Button(controls, text="Paste Base64", command=self.paste_base64).pack(side="left")
        ttk.Button(controls, text="Export damaged...", command=self.export_damaged).pack(side="left", padx=4)
        self.lab_status = tk.StringVar(value="Strict decoder remains enabled.")
        ttk.Label(controls, textvariable=self.lab_status).pack(side="right")
        panes = ttk.Panedwindow(self.lab_tab, orient="horizontal")
        panes.pack(fill="both", expand=True)
        self.lab_original = ImagePane(panes, "Original")
        self.lab_preview = ImagePane(panes, "UNSAFE CORRUPTION PREVIEW")
        self.lab_recovered = ImagePane(panes, "Strict decode / anti-rot recovery")
        panes.add(self.lab_original, weight=1)
        panes.add(self.lab_preview, weight=1)
        panes.add(self.lab_recovered, weight=1)
        self.image_panes.extend((self.lab_original, self.lab_preview, self.lab_recovered))

    def confirm_discard(self):
        return not self.document.dirty or messagebox.askyesno(
            "Unsaved changes", "Discard unsaved WIMF changes?", parent=self.root
        )

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
            self.status.set(f"Opened {path}")
            self.root.title(f"WIMF Studio - {Path(path).name}")
        except Exception as error:
            messagebox.showerror("Open failed", str(error), parent=self.root)

    def _refresh_document(self):
        source = _display_array(self.document.source) if self.document.source is not None else None
        decoded = _display_array(self.document.decoded) if self.document.decoded is not None else None
        self.source_pane.set_image(source)
        self.decoded_pane.set_image(decoded)
        self.lab_original.set_image(source)
        overlays = []
        if self.document.encoded and self.document.details.get("format") == "WIM2":
            from .hybrid import MODE_NAMES, parse_v2

            for entry in parse_v2(self.document.encoded)["entries"]:
                overlays.append((entry[0], entry[1], entry[2], entry[3], MODE_COLORS[MODE_NAMES[entry[4]]]))
        self.inspect_pane.set_image(decoded if decoded is not None else source, overlays)
        self.metadata_text.delete("1.0", "end")
        self.metadata_text.insert("1.0", json.dumps(self.document.metadata, indent=2, sort_keys=True))
        details = self.document.details
        self.protection_text.set(
            f"Protected: {'yes' if details.get('protected') else 'no'}\n"
            f"Repaired while opening: {'yes' if details.get('repaired') else 'no'}\n"
            f"Chrono states: {details.get('history_states', 1)}"
        )

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
        except Exception as error:
            messagebox.showerror("Encode failed", str(error), parent=self.root)

    def _poll_jobs(self):
        if self.jobs.running and self.jobs.token is not None and self.jobs.token.total:
            self.progress.stop()
            self.progress.configure(
                mode="determinate", maximum=max(1, self.jobs.token.total), value=self.jobs.token.completed
            )
            self.status.set(f"{self.jobs.token.stage}: {self.jobs.token.completed}/{self.jobs.token.total}")
        while True:
            try:
                kind, name, payload = self.jobs.events.get_nowait()
            except Exception:
                break
            if kind == "started":
                self.progress.configure(mode="indeterminate", value=0)
                self.progress.start(12)
                self.cancel_button.configure(state="normal")
                self.status.set(f"Running {name}...")
            else:
                self.progress.stop()
                self.progress.configure(mode="determinate", value=0)
                self.cancel_button.configure(state="disabled")
                if kind == "completed" and name == "encode":
                    self.document.apply_encode_result(payload)
                    difference = self.document.metrics["difference"]
                    shown = ImageEnhance.Contrast(_display_array(difference)).enhance(8)
                    self.difference_pane.set_image(shown)
                    self._refresh_document()
                    psnr = self.document.metrics["psnr"]
                    modes = ", ".join(
                        f"{name[0].upper()}:{count}"
                        for name, count in self.document.details.get("tile_modes", {}).items()
                        if count
                    )
                    self.metrics_text.set(
                        f"{self.document.metrics['encoded_bytes']:,} B ({self.document.metrics['ratio']:.3f}x) | "
                        f"MSE {self.document.metrics['mse']:.3f} | "
                        f"max {self.document.metrics['maximum_error']} | PSNR {'inf' if math.isinf(psnr) else f'{psnr:.2f} dB'} | "
                        f"enc {self.document.metrics['encode_seconds']:.3f}s / dec {self.document.metrics['decode_seconds']:.3f}s | {modes}"
                    )
                    self.status.set("Encode completed")
                elif kind == "failed":
                    messagebox.showerror(f"{name.title()} failed", payload, parent=self.root)
                    self.status.set(payload)
                else:
                    self.status.set("Operation cancelled")
        self.root.after(80, self._poll_jobs)

    def save(self, as_new=False):
        if not self.document.encoded:
            messagebox.showinfo("Nothing to save", "Encode the document first.", parent=self.root)
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
            messagebox.showerror("Invalid metadata", str(error), parent=self.root)

    def decode_roi(self):
        try:
            if not self.document.encoded:
                raise ValueError("encode or open a WIMF file first")
            roi = tuple(map(int, self.roi.get().split()))
            if len(roi) != 4:
                raise ValueError("ROI requires X Y WIDTH HEIGHT")
            image = wimf.decode(self.document.encoded, roi=roi)
            self.inspect_pane.set_image(image.pil)
        except Exception as error:
            messagebox.showerror("ROI decode failed", str(error), parent=self.root)

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
            messagebox.showinfo("No WIMF data", "Encode or open a WIMF file first.", parent=self.root)
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
            messagebox.showerror("Base64 import failed", str(error), parent=self.root)

    def export_damaged(self):
        if not getattr(self, "damaged", None):
            messagebox.showinfo("No damaged copy", "Run a corruption experiment first.", parent=self.root)
            return
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".wimf", filetypes=(("WIMF", "*.wimf"),))
        if path:
            Path(path).write_bytes(self.damaged)

    def show_history(self):
        try:
            decoder = wimf.WIMFDecoder(self.document.encoded)
            self.inspect_pane.set_image(decoder.decode_chrono_state(self.history_index.get()).pil)
        except Exception as error:
            messagebox.showerror("History decode failed", str(error), parent=self.root)

    def export_history(self):
        try:
            decoder = wimf.WIMFDecoder(self.document.encoded)
            image = decoder.decode_chrono_state(self.history_index.get()).pil
            path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".png")
            if path:
                image.save(path)
        except Exception as error:
            messagebox.showerror("History export failed", str(error), parent=self.root)

    def show_runtime(self):
        messagebox.showinfo("WIMF runtime", json.dumps(wimf.runtime_info(), indent=2), parent=self.root)

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
        messagebox.showinfo(
            "Report a Bug",
            "Runtime diagnostics were copied to your clipboard. Paste them into the GitHub issue and attach a minimal sample file when possible.",
            parent=self.root,
        )

    def close(self):
        if self.confirm_discard():
            self.jobs.close()
            self.root.destroy()


def launch(path=None):
    root = tk.Tk()
    WIMFStudio(root, path)
    root.mainloop()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Open WIMF Studio.")
    parser.add_argument("path", nargs="?")
    args = parser.parse_args(argv)
    launch(args.path)


if __name__ == "__main__":
    main()
