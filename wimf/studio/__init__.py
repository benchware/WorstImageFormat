"""WIMF Studio: lightweight Tkinter encoder, inspector, and codec lab (modular UI package)."""

from .app import WIMFStudio, launch, main
from .images import _display_array

__all__ = ["WIMFStudio", "launch", "main", "_display_array"]
