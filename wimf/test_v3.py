"""WIMF 3.0 (oxygen) native binding tests: roundtrips, inspection, rejection."""

import numpy as np
import pytest

wimf_v3 = pytest.importorskip("wimf.wimf_v3_cpp")


def _image(w, h, ch, kind):
    yy, xx = np.mgrid[0:h, 0:w]
    if kind == "gradient":
        base = ((xx * 255 // max(w - 1, 1)) + (yy * 255 // max(h - 1, 1))) & 255
        return np.repeat(base[..., None], ch, axis=2).astype(np.uint8)
    if kind == "flat":
        return np.full((h, w, ch), 37, dtype=np.uint8)
    rng = np.random.default_rng(w * h + ch)
    return rng.integers(0, 256, (h, w, ch), dtype=np.uint8)


@pytest.mark.parametrize("shape", [(64, 64, 3), (192, 160, 3), (300, 200, 1), (17, 17, 4), (1, 1, 1)])
@pytest.mark.parametrize("kind", ["gradient", "flat", "noise"])
def test_v3_roundtrip(shape, kind):
    image = _image(*shape, kind=kind)
    payload = wimf_v3.encode_image(image.tobytes(), shape[1], shape[0], shape[2])
    decoded = wimf_v3.decode_image(payload)
    assert decoded["width"] == shape[1] and decoded["height"] == shape[0]
    assert decoded["channels"] == shape[2]
    assert decoded["pixels"] == image.tobytes()


def test_v3_metadata_and_inspection():
    image = _image(96, 80, 3, kind="gradient")
    payload = wimf_v3.encode_image(image.tobytes(), 96, 80, 3, metadata=b'{"v":3}')
    info = wimf_v3.parse_container(payload)
    assert info["width"] == 96 and info["height"] == 80
    assert info["metadata"] == b'{"v":3}'
    assert info["tiles"]
    for tile in info["tiles"]:
        assert tile["mode"] in (0, 1)
        assert {tile["mode"], tile["entropy"]} != {1, 0}
    decoded = wimf_v3.decode_image(payload)
    assert decoded["pixels"] == image.tobytes()


def test_v3_max_tile_controls_leaf_count():
    image = _image(200, 200, 3, kind="gradient")
    small = wimf_v3.parse_container(wimf_v3.encode_image(image.tobytes(), 200, 200, 3, max_tile=64))
    big = wimf_v3.parse_container(wimf_v3.encode_image(image.tobytes(), 200, 200, 3, max_tile=512))
    assert len(small["tiles"]) > len(big["tiles"])
    assert small["max_tile"] == 64 and big["max_tile"] == 512


def test_v3_rejects_corruption():
    image = _image(64, 64, 3, kind="gradient")
    payload = bytearray(wimf_v3.encode_image(image.tobytes(), 64, 64, 3))
    payload[0] = ord("X")  # bad magic
    with pytest.raises(ValueError):
        wimf_v3.decode_image(bytes(payload))

    good = bytearray(wimf_v3.encode_image(image.tobytes(), 64, 64, 3))
    good[-1] ^= 0xFF  # payload CRC mismatch
    with pytest.raises(ValueError):
        wimf_v3.decode_image(bytes(good))

    with pytest.raises(ValueError):
        wimf_v3.decode_image(b"WIM2")  # wrong format family


def test_v3_rejects_mismatched_buffer():
    image = _image(32, 32, 3, kind="flat")
    with pytest.raises(ValueError):
        wimf_v3.encode_image(image.tobytes()[:-1], 32, 32, 3)


def test_v3_progressive_decode_and_16bit():
    image = _image(96, 96, 3, kind="gradient")
    payload = wimf_v3.encode_image(image.tobytes(), 96, 96, 3)
    full = wimf_v3.decode_image(payload)
    assert full["pixels"] == image.tobytes()
    rough = wimf_v3.decode_image(payload, target_planes=1)
    assert rough["width"] == 96 and len(rough["pixels"]) == len(image.tobytes())

    # HDR depth enums: u12 rides two-byte little-endian samples.
    yy, xx = np.mgrid[0:40, 0:40]
    deep = (((xx * 1024 + yy * 33) % 4000) + 100).astype("<u2")
    deep = np.repeat(deep[..., None], 3, axis=2)
    blob = wimf_v3.encode_image(deep.tobytes(), 40, 40, 3, depth=2)  # kDepthU12
    out = wimf_v3.decode_image(blob)
    assert out["bit_depth"] == 16
    assert out["pixels"] == deep.tobytes()
    with pytest.raises(ValueError):
        wimf_v3.encode_image(deep.tobytes(), 40, 40, 3, depth=4)  # f16 reserved


def test_wim2_files_still_decode_through_v2():
    import wimf

    arr = _image(48, 48, 3, kind="gradient")
    payload = wimf.encode(arr, lossless=True)
    decoded = wimf.decode(payload)
    assert np.array_equal(decoded.to_numpy(), arr)
