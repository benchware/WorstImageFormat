"""Persistent Studio settings and the rotating tip pool."""

import json
from pathlib import Path

from .studio_theme import THEME_NAMES

SETTINGS_FILE = Path.home() / ".wimf-studio-settings.json"

QUALITY_PRESETS = ("Fast", "Balanced", "Extreme")
CODECS = ("auto", "raw", "predictive", "palette", "wavelet")
CORE_MODES = ("auto", "native", "python")

TIPS = (
    "Scroll on any image to zoom, drag to pan, and double-click to snap back to fit.",
    "The Difference view exaggerates error 8x - even great encodes light up a little.",
    "Quality 7 with the Balanced preset is a great starting point for most images.",
    "Lossless mode ignores the quality slider and always reconstructs pixels bit-exact.",
    "Codec 'auto' lets WIMF pick raw, predictive, palette or wavelet per tile.",
    "The Inspect tab draws a live tile map - uncheck a codec to spotlight the others.",
    "Region decode reads only the tiles inside a rectangle, so it is nearly instant.",
    "Anti-rot parity travels inside the file and repairs damage automatically on load.",
    "Codec Lab can corrupt a copy on purpose to prove the strict decoder catches it.",
    "Metadata edits rewrite the container without recompressing a single tile.",
    "Base64 transport copies your WIMF file as plain text ready for code or HTML.",
    "Chrono history keeps several states inside one file - browse them in Protection.",
    "Ctrl+E encodes, Ctrl+S saves, Ctrl+0 fits every pane, F1 reopens the guide.",
    "Threads left empty lets WIMF pick the ideal worker count for your CPU.",
)

DEFAULTS = {
    "theme": "dark",
    "show_welcome": True,
    "show_tips": True,
    "confirm_close": True,
    "quality": 7,
    "preset": "Balanced",
    "codec": "auto",
    "threads": "",
    "core": "auto",
}


class StudioSettings:
    """JSON-backed settings with defaults, light validation, and explicit saves."""

    def __init__(self, data):
        self._data = dict(data)

    @classmethod
    def load(cls):
        data = dict(DEFAULTS)
        try:
            stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            stored = {}
        if isinstance(stored, dict):
            for key, default in DEFAULTS.items():
                if key not in stored:
                    continue
                value = stored[key]
                if key == "theme":
                    data[key] = value if value in THEME_NAMES else default
                elif key == "preset":
                    data[key] = value if value in QUALITY_PRESETS else default
                elif key == "codec":
                    data[key] = value if value in CODECS else default
                elif key == "core":
                    data[key] = value if value in CORE_MODES else default
                elif key == "quality":
                    data[key] = value if isinstance(value, int) and 1 <= value <= 10 else default
                elif key == "threads":
                    data[key] = str(value) if value is not None else default
                elif isinstance(default, bool):
                    data[key] = bool(value)
        return cls(data)

    def save(self):
        try:
            SETTINGS_FILE.write_text(json.dumps(self._data, indent=2, sort_keys=True), encoding="utf-8")
        except OSError:
            pass

    def reset(self):
        self._data = dict(DEFAULTS)
        self.save()

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self._data[key] = value

    def palette(self):
        from .studio_theme import resolve

        return resolve(self._data["theme"])
