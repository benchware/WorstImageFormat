"""Headless-safe command entry point for WIMF Studio."""

import argparse


def main(argv=None):
    parser = argparse.ArgumentParser(description="Open WIMF Studio.")
    parser.add_argument("path", nargs="?")
    args = parser.parse_args(argv)
    try:
        from .studio import launch
    except ImportError as error:
        parser.error(f"WIMF Studio requires Tkinter: {error}")
    launch(args.path)


if __name__ == "__main__":
    main()
