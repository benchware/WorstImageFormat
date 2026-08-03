import numpy as np
from PIL import Image

import wimf
from wimf.hybrid import decode_v2, encode_v2, parse_v2


def test_v2_lossless_rgb_odd_dimensions(tmp_path):
    arr = np.random.default_rng(1).integers(0, 256, (133, 259, 3), dtype=np.uint8)
    path = tmp_path / "odd.wimf"
    wimf.save(path, Image.fromarray(arr), lossless=True)
    assert path.read_bytes()[:4] == b"WIM2"
    assert np.array_equal(wimf.open(path).to_numpy(), arr)


def test_v2_palette_and_mixed_modes():
    arr = np.zeros((128, 256, 3), dtype=np.uint8)
    arr[:, :128, 0] = 255
    arr[:, 128:] = np.random.default_rng(2).integers(0, 256, (128, 128, 3), dtype=np.uint8)
    data = encode_v2(arr.tobytes(), 256, 128, 3, lossless=True, preset="Extreme")
    info = parse_v2(data)
    assert len({entry[4] for entry in info["entries"]}) >= 2
    decoded, _ = decode_v2(data)
    assert np.array_equal(np.frombuffer(decoded, np.uint8).reshape(arr.shape), arr)


def test_v2_roi_only_returns_requested_region():
    arr = np.random.default_rng(3).integers(0, 256, (200, 200, 4), dtype=np.uint8)
    data = encode_v2(arr.tobytes(), 200, 200, 4, lossless=True)
    decoded, _ = decode_v2(data, roi=(90, 70, 80, 60))
    got = np.frombuffer(decoded, np.uint8).reshape(60, 80, 4)
    assert np.array_equal(got, arr[70:130, 90:170])


def test_v2_checksum_rejects_corruption():
    arr = np.zeros((16, 16, 3), dtype=np.uint8)
    data = bytearray(encode_v2(arr.tobytes(), 16, 16, 3, lossless=True))
    info = parse_v2(data)
    offset = info["entries"][0][8]
    data[offset] ^= 1
    try:
        decode_v2(bytes(data))
    except ValueError as exc:
        assert "checksum" in str(exc)
    else:
        raise AssertionError("corrupt tile was accepted")


def test_explicit_v1_output(tmp_path):
    arr = np.zeros((16, 16, 3), dtype=np.uint8)
    path = tmp_path / "legacy.wimf"
    wimf.save(path, Image.fromarray(arr), lossless=True, format_version=1)
    assert path.read_bytes()[:4] == b"WIMF"
    assert np.array_equal(wimf.open(path).to_numpy(), arr)


def test_threaded_output_is_deterministic():
    arr = np.random.default_rng(10).integers(0, 256, (257, 259, 3), dtype=np.uint8)
    single = encode_v2(arr.tobytes(), 259, 257, 3, lossless=True, threads=1)
    threaded = encode_v2(arr.tobytes(), 259, 257, 3, lossless=True, threads=4)
    assert single == threaded


def test_runtime_info_contract():
    details = wimf.runtime_info()
    assert isinstance(details["native"], bool)
    assert details["architecture"]
    assert details["simd"]
    assert details["hardware_threads"] >= 1


def test_native_predictive_parity_when_available():
    try:
        from wimf import wimf_v2_cpp
    except ImportError:
        return
    arr = np.random.default_rng(11).integers(0, 256, (65, 131, 4), dtype=np.uint8)
    packed = wimf_v2_cpp.encode_predictive(arr, 131, 65, 4, 1)
    decoded = wimf_v2_cpp.decode_predictive(packed, 131, 65, 4, 1)
    assert np.array_equal(np.frombuffer(decoded, np.uint8).reshape(arr.shape), arr)
