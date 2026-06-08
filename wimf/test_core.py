import os
import numpy as np
from PIL import Image
import wimf
import pytest
import struct

def test_lossless_roundtrip():
    """Verify bit-perfect lossless encoding and decoding."""
    arr = np.random.randint(0, 256, (64, 64, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    wimf.save('test_ll.wimf', img, lossless=True)
    
    loaded = wimf.open('test_ll.wimf')
    os.remove('test_ll.wimf')
    
    assert np.array_equal(arr, loaded.to_numpy())

def test_lossy_dimensions():
    """Verify lossy encoding preserves image structure."""
    arr = np.random.randint(0, 256, (128, 128, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    wimf.save('test_lossy.wimf', img, quality=5)
    
    loaded = wimf.open('test_lossy.wimf')
    os.remove('test_lossy.wimf')
    
    assert loaded.size == (128, 128)

def test_metadata_persistence():
    """Verify metadata is saved and loaded correctly."""
    arr = np.random.randint(0, 256, (16, 16, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    wimf.save('test_meta.wimf', img, quality=5, author="CI_Tester", custom="Data")
    
    info = wimf.info('test_meta.wimf')
    os.remove('test_meta.wimf')
    
    assert info['author'] == "CI_Tester"
    assert info['custom'] == "Data"

def test_parity_protection():
    """Verify anti_rot (parity) encoding creates valid ROT files."""
    arr = np.random.randint(0, 256, (16, 16, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    wimf.save('test_parity.wimf', img, lossless=True, anti_rot=True)
    
    with open('test_parity.wimf', 'rb') as f:
        magic = f.read(4)
        
    os.remove('test_parity.wimf')
    assert magic == b"ROT!"

def test_cpp_extension_loaded():
    """Ensure the C++ backend is the active processing engine."""
    from wimf import core
    assert core.HAS_CPP is True, "C++ extension failed to load in CI environment."

def test_tiled_mode_10():
    """Verify large images trigger and survive Mode 10 tiling."""
    arr = np.random.randint(0, 256, (600, 600, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    wimf.save('test_tiled.wimf', img, quality=3)
    
    loaded = wimf.open('test_tiled.wimf')
    os.remove('test_tiled.wimf')
    
    assert loaded.size == (600, 600)
