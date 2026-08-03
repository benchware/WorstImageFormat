"""Compatibility entry point for the former standalone viewer."""

from .studio import WIMFStudio as WIMFViewer
from .studio import launch
from .studio_cli import main

__all__ = ["WIMFViewer", "launch", "main"]


if __name__ == "__main__":
    main()
