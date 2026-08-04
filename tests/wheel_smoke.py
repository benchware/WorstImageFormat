"""Installed-wheel smoke test used by cibuildwheel and sdist verification."""

import importlib
import importlib.metadata
import os
import subprocess
import sys

import numpy as np

import wimf
from wimf.hybrid import MODE_NAMES, parse_v2


def roundtrip(array, **options):
    payload = wimf.WIMFEncoder(array).encode(**options)
    decoded = wimf.WIMFDecoder(payload).decode().to_numpy()
    return payload, decoded


def main():
    allow_python = os.environ.get("WIMF_SMOKE_ALLOW_PYTHON") == "1"
    try:
        importlib.import_module("wimf.wimf_cpp")
        importlib.import_module("wimf.wimf_v2_cpp")
    except ImportError:
        if not allow_python:
            raise

    runtime = wimf.runtime_info()
    assert runtime["native"] is True or allow_python
    assert runtime["codec_version"] and runtime["zstandard_version"]
    if not allow_python:
        assert runtime["native_orchestration"] is True
        assert {"synchronous", "threaded"} <= set(runtime["execution_policies"])

    rng = np.random.default_rng(20260803)
    rgb = rng.integers(0, 256, (37, 41, 3), dtype=np.uint8)
    _, decoded = roundtrip(rgb, lossless=True)
    assert np.array_equal(decoded, rgb)

    rgba = rng.integers(0, 256, (31, 29, 4), dtype=np.uint8)
    _, decoded = roundtrip(rgba, lossless=True, codec="predictive")
    assert np.array_equal(decoded, rgba)

    gray = rng.integers(0, 256, (23, 27), dtype=np.uint8)
    _, decoded = roundtrip(gray, lossless=True)
    assert np.array_equal(decoded[..., 0], gray)

    colors = np.array([[0, 0, 0], [255, 255, 255], [220, 30, 80], [20, 90, 230]], dtype=np.uint8)
    palette = colors[rng.integers(0, 4, (32, 32))]
    palette_payload, decoded = roundtrip(palette, lossless=True, codec="palette")
    assert np.array_equal(decoded, palette)
    assert MODE_NAMES[parse_v2(palette_payload)["entries"][0][4]] == "palette"

    raw_payload, decoded = roundtrip(rgb, lossless=True, codec="raw")
    assert np.array_equal(decoded, rgb)
    assert MODE_NAMES[parse_v2(raw_payload)["entries"][0][4]] == "raw"
    assert wimf.from_data_url(wimf.to_data_url(raw_payload)) == raw_payload
    comparison = wimf.compare(rgb, decoded)
    assert comparison["maximum_error"] == 0
    rewritten = wimf.rewrite_metadata(raw_payload, {"wheel": True})
    assert wimf.inspect(rewritten)["metadata"]["wheel"] is True

    wavelet_payload, decoded = roundtrip(rgb, lossless=False, quality=5, codec="wavelet")
    assert decoded.shape == rgb.shape and wavelet_payload.startswith(b"WIM2")

    roi_source = rng.integers(0, 256, (135, 129, 3), dtype=np.uint8)
    roi_payload, _ = roundtrip(roi_source, lossless=True)
    roi = wimf.WIMFDecoder(roi_payload).decode(roi=(17, 19, 53, 47)).to_numpy()
    assert np.array_equal(roi, roi_source[19:66, 17:70])

    changed = rgba.copy()
    changed[3:12, 5:18] = [10, 80, 160, 255]
    protected = wimf.WIMFEncoder(rgba).set_anti_rot().add_chrono_state(changed).encode(lossless=True)
    history = wimf.WIMFDecoder(protected)
    assert history.was_protected and history.num_states == 2
    assert np.array_equal(history.decode_chrono_state(1).to_numpy(), changed)

    distribution = importlib.metadata.distribution("wimf")
    scripts = {entry.name for entry in distribution.entry_points if entry.group == "console_scripts"}
    assert {"wimf", "wimf-studio", "wimf-convert", "wimf-view", "wimf-meta", "wimf-cat"} <= scripts
    subprocess.run([sys.executable, "-m", "wimf", "--help"], check=True, capture_output=True)
    subprocess.run([sys.executable, "-m", "wimf", "runtime", "--json"], check=True, capture_output=True)
    subprocess.run([sys.executable, "-m", "wimf.studio_cli", "--help"], check=True, capture_output=True)
    subprocess.run([sys.executable, "-m", "wimf", "base16", "--help"], check=True, capture_output=True)
    subprocess.run([sys.executable, "-m", "wimf", "base32", "--help"], check=True, capture_output=True)
    subprocess.run([sys.executable, "-m", "wimf", "base64", "--help"], check=True, capture_output=True)
    subprocess.run([sys.executable, "-m", "wimf.cli", "--help"], check=True, capture_output=True)
    subprocess.run([sys.executable, "-m", "wimf.meta_tool", "--help"], check=True, capture_output=True)

    print("WIMF installed-wheel smoke test passed", runtime)


if __name__ == "__main__":
    main()
