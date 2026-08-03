"""Render actual WIMF Studio states under CI's virtual X display."""

import argparse
import sys
import tkinter as tk
from pathlib import Path

# Running this file directly makes ``tests/`` Python's import root. Add the
# repository root so the in-tree package can be imported in CI.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PIL import ImageGrab

from wimf.studio import WIMFStudio, _display_array
from wimf.studio_model import EncodeSettings, StudioDocument


def capture(root, output):
    root.update_idletasks()
    root.update()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    ImageGrab.grab((x, y, x + root.winfo_width(), y + root.winfo_height())).save(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    root = tk.Tk()
    studio = WIMFStudio(root)
    capture(root, args.output / "studio-empty.png")

    y, x = np.indices((193, 321))
    image = np.stack(((x * 3 + y) & 255, (x + y * 2) & 255, ((x // 16 ^ y // 16) * 255) & 255), axis=2).astype(np.uint8)
    studio.document = StudioDocument(source=image, metadata={"fixture": "Studio CI"})
    result = studio.document.encode(EncodeSettings(quality=5, codec="auto"))
    studio.document.apply_encode_result(result)
    studio._refresh_document()
    studio.difference_pane.set_image(_display_array(studio.document.metrics["difference"] * 8))
    studio.tabs.select(studio.compare_tab)
    capture(root, args.output / "studio-comparison.png")

    studio.tabs.select(studio.inspect_tab)
    capture(root, args.output / "studio-tile-map.png")
    studio.tabs.select(studio.protection_tab)
    capture(root, args.output / "studio-history.png")
    studio.tabs.select(studio.lab_tab)
    studio.run_corruption()
    capture(root, args.output / "studio-codec-lab.png")
    studio.document.dirty = False
    studio.close()


if __name__ == "__main__":
    main()
