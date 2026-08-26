"""WIMF logo rasterizer: flattens the official SVG path into PIL images (no SVG deps)."""

import re

import numpy as np
from PIL import Image, ImageDraw

LOGO_PATH = (
    "M21,92.59h59.87v31.74c0,11.59,9.4,21,21,21h18.84v56.25h111.34v102.06"
    "c0,11.6-9.4,21-21,21H21c-11.6,0-21-9.4-21-21V113.59c0-11.6,9.4-21,21-21h0Z"
    "M120.71,92.59v52.74h30.57c11.6,0,21-9.41,21-21v-31.74h-51.57v-38.68h-18.84"
    "c-11.6,0-21-9.4-21,21v17.68h39.84Z"
    "M120.71,0h201.58v201.58h-90.24v-87.99c0-11.6-9.41-21-21-21h-38.78v-17.68"
    "c0-11.6-9.4-21-21-21h-30.56V0Z"
)

VIEW_W, VIEW_H = 322.29, 324.64
_TOKEN = re.compile(r"([MmLlHhVvCcZz])|(-?\d*\.?\d+(?:e-?\d+)?)")
_CACHE = {}


def _flatten_path(path=LOGO_PATH, steps=14):
    subpaths, current, start = [], [], None
    pos = (0.0, 0.0)
    tokens = _TOKEN.findall(path)
    index = 0

    def numbers():
        nonlocal index
        values = []
        while index < len(tokens) and tokens[index][1]:
            values.append(float(tokens[index][1]))
            index += 1
        return values

    def cubic(p0, p1, p2, p3):
        for step in range(1, steps + 1):
            t = step / steps
            u = 1 - t
            x = u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0]
            y = u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]
            current.append((x, y))

    while index < len(tokens):
        letter = tokens[index][0]
        index += 1
        if letter in "Zz":
            if current:
                current.append(start)
                subpaths.append(current)
                current, start = [], None
            continue
        relative = letter.islower()
        if letter in "Mm":
            values = numbers()
            if current:
                subpaths.append(current)
                current = []
            for pair in range(0, len(values) - 1, 2):
                if relative:
                    pos = (pos[0] + values[pair], pos[1] + values[pair + 1])
                else:
                    pos = (values[pair], values[pair + 1])
                current.append(pos)
            start = current[0] if current else None
        elif letter in "Ll":
            values = numbers()
            for pair in range(0, len(values) - 1, 2):
                pos = (
                    (pos[0] + values[pair], pos[1] + values[pair + 1])
                    if relative
                    else (values[pair], values[pair + 1])
                )
                current.append(pos)
        elif letter in "Hh":
            for value in numbers():
                pos = (pos[0] + value, pos[1]) if relative else (value, pos[1])
                current.append(pos)
        elif letter in "Vv":
            for value in numbers():
                pos = (pos[0], pos[1] + value) if relative else (pos[0], value)
                current.append(pos)
        elif letter in "Cc":
            values = numbers()
            for offset in range(0, len(values) - 5, 6):
                x1, y1, x2, y2, x, y = values[offset : offset + 6]
                if relative:
                    x1, y1, x2, y2 = pos[0] + x1, pos[1] + y1, pos[0] + x2, pos[1] + y2
                    x, y = pos[0] + x, pos[1] + y
                cubic(pos, (x1, y1), (x2, y2), (x, y))
                pos = (x, y)
    if current:
        subpaths.append(current)
    return subpaths


_SUBPATHS = None


def _subpaths():
    global _SUBPATHS
    if _SUBPATHS is None:
        _SUBPATHS = _flatten_path()
    return _SUBPATHS


def logo_image(size, color="#ffffff", supersample=4):
    """Render the WIMF mark as a square RGBA PIL image of ``size`` pixels."""
    size = max(8, int(size))
    key = (size, color)
    if key in _CACHE:
        return _CACHE[key]
    scale = size * supersample / VIEW_H
    width, height = round(VIEW_W * scale), round(VIEW_H * scale)
    canvas = np.zeros((height, width), dtype=bool)
    for points in _subpaths():
        scaled = [(round(x * scale), round(y * scale)) for x, y in points]
        if len(scaled) < 3:
            continue
        scratch = Image.new("1", (width, height), 0)
        ImageDraw.Draw(scratch).polygon(scaled, fill=1)
        canvas ^= np.array(scratch, dtype=bool)
    red, green, blue = (int(color.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[..., 0], rgba[..., 1], rgba[..., 2] = red, green, blue
    rgba[..., 3] = canvas.astype(np.uint8) * 255
    image = Image.fromarray(rgba, "RGBA").resize((size, size), Image.Resampling.LANCZOS)
    _CACHE[key] = image
    return image
