import numpy as np
import pytest
from PIL import Image

import wimf
from wimf import hybrid
from wimf.extensions import parse_extensions
from wimf.hybrid import decode_v2, encode_v2, parse_v2


@pytest.mark.parametrize("quality", range(1, 11))
@pytest.mark.parametrize("preset", ["Fast", "Balanced", "Extreme"])
def test_all_lossy_quality_and_preset_combinations(quality, preset):
    """Every documented WIM2 lossy quality/preset combination must encode and decode."""
    y, x = np.indices((24, 40))
    image = np.stack(((x * 7 + y) & 255, (x + y * 9) & 255, (x * 3 + y * 5) & 255), axis=2).astype(np.uint8)
    payload = encode_v2(
        image.tobytes(), 40, 24, 3, quality=quality, preset=preset, lossless=False, codec="auto", threads=1
    )
    decoded, info = decode_v2(payload)
    assert len(decoded) == image.size
    assert info["width"] == 40 and info["height"] == 24


def test_varints_decode_v2_marker_free_pairs():
    """reversible == 2 wavelet tiles use strict (run, zigzag) varint pairs.

    Vector: [0, 0, 5, -3] encodes as run=2, zigzag(5)=10, run=0, zigzag(-3)=5;
    the decoder zero-fills the trailing remainder."""
    stream = bytes([2, 10, 0, 5])
    assert list(hybrid._varints_decode_v2(stream, 5)) == [0, 0, 5, -3, 0]
    assert list(hybrid._varints_decode_v2(b"", 3)) == [0, 0, 0]
    with pytest.raises(ValueError):
        hybrid._varints_decode_v2(bytes([9, 1]), 3)
    with pytest.raises(ValueError):
        hybrid._varints_decode_v2(bytes([1]), 3)


def test_v2_lossless_rgb_odd_dimensions(tmp_path):
    arr = np.random.default_rng(1).integers(0, 256, (133, 259, 3), dtype=np.uint8)
    path = tmp_path / "odd.wimf"
    wimf.save(path, Image.fromarray(arr), lossless=True)
    assert path.read_bytes()[:4] in (b"WIM2", b"WIM3")
    assert np.array_equal(wimf.open(path).to_numpy(), arr)


def test_v2_lossless_grayscale_and_la():
    gray = np.random.default_rng(17).integers(0, 256, (37, 53), dtype=np.uint8)
    gray_payload = wimf.WIMFEncoder(gray).encode(lossless=True)
    gray_image = wimf.WIMFDecoder(gray_payload).decode()
    assert gray_image.mode == "L"
    assert np.array_equal(gray_image.to_numpy()[..., 0], gray)

    la = np.empty((31, 47, 2), dtype=np.uint8)
    la[..., 0] = gray[:31, :47]
    la[..., 1] = np.arange(47, dtype=np.uint8)
    la_payload = wimf.WIMFEncoder(la).encode(lossless=True)
    la_image = wimf.WIMFDecoder(la_payload).decode()
    assert la_image.mode == "LA"
    assert np.array_equal(la_image.to_numpy(), la)


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
    assert isinstance(details["native_orchestration"], bool)
    assert details["execution_policies"]
    if details["native"]:
        assert details["native_orchestration"] is True
        assert {"synchronous", "threaded"} <= set(details["execution_policies"])


def test_friendly_memory_api_and_inspection(tmp_path):
    arr = np.random.default_rng(27).integers(0, 256, (31, 37, 4), dtype=np.uint8)
    payload = wimf.encode(arr, lossless=True, metadata={"purpose": "api-test"})
    decoded = wimf.decode(payload)
    assert np.array_equal(decoded.to_numpy(), arr)
    details = wimf.inspect(payload)
    assert details["format"] in ("WIM2", "WIM3")
    assert details["width"] == 37 and details["height"] == 31
    assert details["metadata"]["purpose"] == "api-test"
    assert sum(details["tile_modes"].values()) == 1

    output = tmp_path / "friendly.wimf"
    assert wimf.save(output, arr, lossless=True) == str(output)
    assert wimf.is_wimf(output)


@pytest.mark.parametrize(
    "image",
    [
        pytest.param(np.full((64, 64, 3), 128, dtype=np.uint8), id="flat"),
        pytest.param(
            np.repeat((np.indices((64, 64))[0] * 4)[..., None], 3, axis=2).astype(np.uint8), id="gradient"
        ),
        pytest.param(
            np.clip(
                (np.indices((64, 64))[0] * 4)[..., None] + np.random.default_rng(5).integers(-12, 13, (64, 64, 3)),
                0,
                255,
            ).astype(np.uint8),
            id="grad+noise",
        ),
    ],
)
def test_lossy_size_monotonic_in_quality(image):
    """Roadmap 5b: the quality ladder must be rate-monotonic; higher quality
    never produces a smaller payload than the quality below it."""
    sizes = [len(wimf.encode(image, quality=q, preset="Extreme", threads=1)) for q in range(1, 7)]
    assert all(sizes[i + 1] >= sizes[i] for i in range(len(sizes) - 1)), sizes


def test_native_high_depth_and_forced_mode_roundtrips():
    try:
        from wimf import wimf_v2_cpp  # noqa: F401
    except ImportError:
        return
    rng = np.random.default_rng(24)
    for bit_depth, maximum in ((10, 1023), (16, 65535)):
        random_image = rng.integers(0, maximum + 1, (35, 39, 3), dtype=np.uint16)
        for codec in ("raw", "predictive", "wavelet"):
            payload = encode_v2(
                random_image.astype("<u2").tobytes(),
                39,
                35,
                3,
                bit_depth=bit_depth,
                lossless=True,
                codec=codec,
            )
            decoded, _ = decode_v2(payload)
            assert np.array_equal(np.frombuffer(decoded, "<u2").reshape(random_image.shape), random_image)

        palette = np.zeros((35, 39, 3), dtype="<u2")
        palette[:, ::2] = maximum
        payload = encode_v2(palette.tobytes(), 39, 35, 3, bit_depth=bit_depth, lossless=True, codec="palette")
        decoded, _ = decode_v2(payload)
        assert np.array_equal(np.frombuffer(decoded, "<u2").reshape(palette.shape), palette)


def test_native_and_reference_mode_parity(monkeypatch):
    if hybrid.native is None or not hasattr(hybrid.native, "encode_image"):
        return
    arr = np.random.default_rng(25).integers(0, 256, (67, 71, 3), dtype=np.uint8)
    native_payload = encode_v2(arr.tobytes(), 71, 67, 3, lossless=True, codec="predictive", threads=1)
    monkeypatch.setattr(hybrid, "native", None)
    reference_payload = encode_v2(arr.tobytes(), 71, 67, 3, lossless=True, codec="predictive", threads=1)
    native_decoded, _ = decode_v2(native_payload)
    reference_decoded, _ = decode_v2(reference_payload)
    assert native_decoded == reference_decoded == arr.tobytes()
    assert [entry[4] for entry in parse_v2(native_payload)["entries"]] == [
        entry[4] for entry in parse_v2(reference_payload)["entries"]
    ]
    assert len(native_payload) <= len(reference_payload) * 1.01


def test_native_predictive_parity_when_available():
    try:
        from wimf import wimf_v2_cpp
    except ImportError:
        return
    arr = np.random.default_rng(11).integers(0, 256, (65, 131, 4), dtype=np.uint8)
    packed = wimf_v2_cpp.encode_predictive(arr, 131, 65, 4, 1)
    decoded = wimf_v2_cpp.decode_predictive(packed, 131, 65, 4, 1)
    assert np.array_equal(np.frombuffer(decoded, np.uint8).reshape(arr.shape), arr)


def test_native_complete_entrypoint_accepts_contiguous_numpy():
    try:
        from wimf import wimf_v2_cpp
    except ImportError:
        return
    arr = np.random.default_rng(26).integers(0, 1024, (23, 29, 3), dtype=np.uint16)
    payload, stats = wimf_v2_cpp.encode_image(
        arr,
        29,
        23,
        3,
        10,
        7,
        True,
        "Balanced",
        "predictive",
        128,
    )
    result = wimf_v2_cpp.decode_image(payload)
    assert np.array_equal(np.frombuffer(result["pixels"], "<u2").reshape(arr.shape), arr)
    assert stats["effective_threads"] >= 1


def test_v2_chrono_history_is_indexed_and_exact():
    base = np.zeros((65, 131, 4), dtype=np.uint8)
    changed = base.copy()
    changed[7:29, 13:57] = [20, 80, 170, 255]
    final = np.random.default_rng(14).integers(0, 256, base.shape, dtype=np.uint8)
    encoder = wimf.WIMFEncoder(base)
    encoder.add_chrono_state(changed).add_chrono_state(final)
    data = encoder.encode(lossless=True, format_version=2)
    assert data.startswith(b"WIM2")
    assert b"HIST" in parse_extensions(data)
    decoder = wimf.WIMFDecoder(data)
    assert decoder.num_states == 3
    assert np.array_equal(decoder.decode_chrono_state(0).to_numpy(), base)
    assert np.array_equal(decoder.decode_chrono_state(1).to_numpy(), changed)
    assert np.array_equal(decoder.decode_chrono_state(2).to_numpy(), final)


def test_v2_anti_rot_repairs_two_corrupted_shards():
    arr = np.random.default_rng(15).integers(0, 256, (129, 257, 3), dtype=np.uint8)
    encoder = wimf.WIMFEncoder(arr).set_anti_rot()
    protected = encoder.encode(lossless=True, format_version=2)
    extensions = parse_extensions(protected)
    assert b"AROT" in extensions and not protected.startswith(b"ROT!")
    parity_payload = extensions[b"AROT"]["payload"]
    original_size = int.from_bytes(parity_payload[4:12], "little")
    shard_size = int.from_bytes(parity_payload[16:20], "little")
    damaged = bytearray(protected)
    damaged[min(original_size - 1, shard_size // 2)] ^= 0x55
    damaged[min(original_size - 1, shard_size + shard_size // 2)] ^= 0xAA
    decoder = wimf.WIMFDecoder(bytes(damaged))
    assert decoder.was_protected and decoder.was_repaired
    assert np.array_equal(decoder.decode().to_numpy(), arr)


def test_v2_anti_rot_rejects_three_corrupted_shards():
    arr = np.random.default_rng(16).integers(0, 256, (128, 256, 3), dtype=np.uint8)
    protected = wimf.WIMFEncoder(arr).set_anti_rot().encode(lossless=True, format_version=2)
    parity_payload = parse_extensions(protected)[b"AROT"]["payload"]
    shard_size = int.from_bytes(parity_payload[16:20], "little")
    damaged = bytearray(protected)
    for index in range(3):
        damaged[index * shard_size + shard_size // 2] ^= index + 1
    try:
        wimf.WIMFDecoder(bytes(damaged))
    except ValueError as exc:
        assert "too many corrupted" in str(exc)
    else:
        raise AssertionError("three-shard corruption was repaired unexpectedly")


def test_v2_anti_rot_rejects_damaged_parity():
    arr = np.zeros((64, 64, 3), dtype=np.uint8)
    protected = wimf.WIMFEncoder(arr).set_anti_rot().encode(lossless=True, format_version=2)
    anti_rot = parse_extensions(protected)[b"AROT"]
    damaged = bytearray(protected)
    damaged[anti_rot["offset"] + anti_rot["size"] - 1] ^= 1
    try:
        wimf.WIMFDecoder(bytes(damaged))
    except ValueError as exc:
        assert "anti-rot" in str(exc)
    else:
        raise AssertionError("damaged anti-rot parity was accepted")


def test_v2_anti_rot_protects_history_payload():
    base = np.zeros((32, 48, 3), dtype=np.uint8)
    changed = np.full_like(base, 177)
    encoder = wimf.WIMFEncoder(base).set_anti_rot().add_chrono_state(changed)
    protected = encoder.encode(lossless=True, format_version=2)
    history = parse_extensions(protected)[b"HIST"]
    damaged = bytearray(protected)
    damaged[history["offset"] + history["size"] // 2] ^= 0x80
    decoder = wimf.WIMFDecoder(bytes(damaged))
    assert decoder.was_repaired
    assert np.array_equal(decoder.decode_chrono_state(1).to_numpy(), changed)
