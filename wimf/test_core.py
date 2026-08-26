from pathlib import Path

import numpy as np
from PIL import Image

import wimf
from wimf.extensions import parse_extensions


def test_lossless_roundtrip(tmp_path):
    """Verify bit-perfect lossless encoding and decoding."""
    arr = np.random.randint(0, 256, (64, 64, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    out = str(tmp_path / "test_ll.wimf")
    wimf.save(out, img, lossless=True)

    loaded = wimf.open(out)
    assert np.array_equal(arr, loaded.to_numpy())


def test_lossy_dimensions(tmp_path):
    """Verify lossy encoding preserves image structure."""
    arr = np.random.randint(0, 256, (128, 128, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    out = str(tmp_path / "test_lossy.wimf")
    wimf.save(out, img, quality=5)

    loaded = wimf.open(out)
    assert loaded.size == (128, 128)


def test_metadata_persistence(tmp_path):
    """Verify metadata is saved and loaded correctly."""
    arr = np.random.randint(0, 256, (16, 16, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    out = str(tmp_path / "test_meta.wimf")
    wimf.save(out, img, quality=5, author="CI_Tester", custom="Data")

    info = wimf.info(out)
    assert info["author"] == "CI_Tester"
    assert info["custom"] == "Data"


def test_parity_protection(tmp_path):
    """Verify anti_rot encoding creates a protected WIM2 file."""
    arr = np.random.randint(0, 256, (16, 16, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    out = str(tmp_path / "test_parity.wimf")
    wimf.save(out, img, lossless=True, anti_rot=True, format_version=2)

    with open(out, "rb") as f:
        magic = f.read(4)
    assert magic in (b"WIM2", b"WIM3")
    assert b"AROT" in parse_extensions(Path(out).read_bytes())


def test_cpp_extension_loaded():
    """Ensure the C++ backend is the active processing engine."""
    from wimf import core

    assert core.HAS_CPP is True, "C++ extension failed to load in CI environment."


def test_tiled_mode_10(tmp_path):
    """Verify large images trigger and survive Mode 10 tiling."""
    arr = np.random.randint(0, 256, (600, 600, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    out = str(tmp_path / "test_tiled.wimf")
    wimf.save(out, img, quality=3)

    loaded = wimf.open(out)
    assert loaded.size == (600, 600)
