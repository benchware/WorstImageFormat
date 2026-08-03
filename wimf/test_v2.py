import numpy as np
from PIL import Image

import wimf
from wimf.extensions import parse_extensions
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


def test_v2_chrono_history_is_indexed_and_exact():
    base = np.zeros((65, 131, 4), dtype=np.uint8)
    changed = base.copy()
    changed[7:29, 13:57] = [20, 80, 170, 255]
    final = np.random.default_rng(14).integers(0, 256, base.shape, dtype=np.uint8)
    encoder = wimf.WIMFEncoder(base)
    encoder.add_chrono_state(changed).add_chrono_state(final)
    data = encoder.encode(lossless=True)
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
    protected = encoder.encode(lossless=True)
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
    protected = wimf.WIMFEncoder(arr).set_anti_rot().encode(lossless=True)
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
    protected = wimf.WIMFEncoder(arr).set_anti_rot().encode(lossless=True)
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
    protected = encoder.encode(lossless=True)
    history = parse_extensions(protected)[b"HIST"]
    damaged = bytearray(protected)
    damaged[history["offset"] + history["size"] // 2] ^= 0x80
    decoder = wimf.WIMFDecoder(bytes(damaged))
    assert decoder.was_repaired
    assert np.array_equal(decoder.decode_chrono_state(1).to_numpy(), changed)
