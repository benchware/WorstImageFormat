"""Cross-feature acceptance tests for public and compatibility WIMF behavior."""

from pathlib import Path

import numpy as np
import pytest

import wimf
from wimf.diagnostics import corrupt, diagnose
from wimf.extensions import parse_extensions
from wimf.hybrid import decode_v2, parse_v2
from wimf.io import stream_load


@pytest.mark.parametrize("bit_depth,maximum,dtype", [(8, 255, np.uint8), (10, 1023, np.uint16), (16, 65535, np.uint16)])
def test_depth_channel_roundtrip_and_access(bit_depth, maximum, dtype):
    image = np.zeros((19, 23, 5), dtype=dtype)
    image[..., :4] = [20, 70, 130, maximum]
    image[..., 4] = np.arange(23, dtype=dtype) * maximum // 22
    encoder = wimf.WIMFEncoder(image).set_metadata(bit_depth=bit_depth)
    decoded = wimf.decode(encoder.encode(lossless=True))
    assert decoded.pil.mode == "RGBA"
    assert np.array_equal(decoded.to_numpy(), image)
    assert np.array_equal(decoded.depth_map, image[..., 4])


def test_streaming_api_yields_complete_wim2(tmp_path):
    image = np.random.default_rng(50).integers(0, 256, (29, 37, 3), dtype=np.uint8)
    path = tmp_path / "stream.wimf"
    wimf.save(path, image, lossless=True, metadata={"stream": True})
    states = list(stream_load(path))
    assert len(states) == 1
    width, height, pixels, metadata, final = states[0]
    assert (width, height, final, metadata["stream"]) == (37, 29, True, True)
    assert np.array_equal(np.frombuffer(pixels, np.uint8).reshape(image.shape), image)


def test_legacy_metadata_surgical_edit_preserves_pixels(tmp_path):
    image = np.random.default_rng(51).integers(0, 256, (24, 32, 3), dtype=np.uint8)
    path = tmp_path / "legacy.wimf"
    wimf.save(path, image, lossless=True, format_version=1, metadata={"before": 1})
    before = wimf.decode(path).to_numpy()
    with wimf.edit_meta(path) as metadata:
        metadata["after"] = 2
    assert wimf.info(path)["after"] == 2
    assert np.array_equal(wimf.decode(path).to_numpy(), before)


def test_legacy_rot_wrapper_roundtrip():
    image = np.random.default_rng(52).integers(0, 256, (20, 28, 3), dtype=np.uint8)
    payload = wimf.WIMFEncoder(image).set_anti_rot().encode(lossless=True, format_version=1)
    assert payload.startswith(b"ROT!")
    decoder = wimf.WIMFDecoder(payload)
    assert decoder.was_protected
    assert np.array_equal(decoder.decode().to_numpy(), image)


def test_metadata_rewrite_preserves_every_tile_payload_with_history():
    base = np.zeros((65, 129, 4), dtype=np.uint8)
    changed = base.copy()
    changed[7:30, 11:80] = [10, 90, 180, 255]
    encoder = wimf.WIMFEncoder(base).set_anti_rot().add_chrono_state(changed)
    payload = encoder.encode(lossless=True)
    before = parse_v2(payload)
    tile_payloads = [payload[item[8] : item[8] + item[9]] for item in before["entries"]]
    rewritten = wimf.rewrite_metadata(payload, {"edited": True})
    after = parse_v2(rewritten)
    assert tile_payloads == [rewritten[item[8] : item[8] + item[9]] for item in after["entries"]]
    assert {b"HIST", b"AROT"} <= set(parse_extensions(rewritten))
    decoder = wimf.WIMFDecoder(rewritten)
    assert np.array_equal(decoder.decode_chrono_state(1).to_numpy(), changed)


@pytest.mark.parametrize("area", ["header", "metadata", "index", "payload", "extension", "parity"])
def test_deterministic_corruption_targets_all_container_areas(area):
    image = np.random.default_rng(53).integers(0, 256, (129, 257, 3), dtype=np.uint8)
    payload = wimf.encode(image, lossless=True, anti_rot=True, metadata={"purpose": "corruption-target"})
    damaged = corrupt(payload, seed=77, area=area)
    assert damaged == corrupt(payload, seed=77, area=area)
    assert damaged != payload
    report = diagnose(damaged)
    assert not report["strict_ok"] or report.get("repaired", False)


def test_uint16_comparison_and_lossless_bit_depths():
    for bit_depth, maximum in ((10, 1023), (16, 65535)):
        image = np.random.default_rng(bit_depth).integers(0, maximum + 1, (17, 21, 3), dtype=np.uint16)
        payload = wimf.WIMFEncoder(image).set_metadata(bit_depth=bit_depth).encode(lossless=True)
        raw, info = decode_v2(payload)
        decoded = np.frombuffer(raw, "<u2").reshape(image.shape)
        assert info["bit_depth"] == bit_depth and np.array_equal(decoded, image)
        comparison = wimf.compare(image, decoded, bit_depth=bit_depth)
        assert comparison["mse"] == 0 and comparison["maximum_error"] == 0


def test_public_option_validation():
    image = np.zeros((16, 16, 3), dtype=np.uint8)
    for options in (
        {"quality": 0},
        {"quality": 11},
        {"codec": "unknown"},
        {"threads": 0},
        {"format_version": 3},
    ):
        with pytest.raises(ValueError):
            wimf.encode(image, **options)
    with pytest.raises(TypeError):
        wimf.encode(image, metadata="not-a-dict")


def test_codec_name_case_insensitive():
    image = np.zeros((16, 16, 3), dtype=np.uint8)
    reference = wimf.encode(image, lossless=True, codec="auto")
    for name in ("Auto", "AUTO", "Auto (hybrid)", " auto "):
        assert wimf.encode(image, lossless=True, codec=name) == reference
    for name in ("Wavelet", "WAVELET", "PREDICTIVE"):
        assert wimf.encode(image, lossless=True, codec=name).startswith(b"WIM2")
    with pytest.raises(ValueError):
        wimf.encode(image, codec="Not A Codec")


def test_operation_progress_contract_when_native_available():
    token = wimf.operation_token()
    payload = wimf.encode(np.zeros((257, 259, 3), dtype=np.uint8), lossless=True, threads=2, operation_token=token)
    assert payload.startswith(b"WIM2")
    if wimf.runtime_info()["native"]:
        assert token.total > 0 and token.completed == token.total and not token.cancelled


def test_file_detection_for_all_container_magics(tmp_path):
    still = wimf.encode(np.zeros((8, 8, 3), dtype=np.uint8), lossless=True)
    legacy = wimf.encode(np.zeros((8, 8, 3), dtype=np.uint8), lossless=True, format_version=1)
    protected = (
        wimf.WIMFEncoder(np.zeros((8, 8, 3), dtype=np.uint8)).set_anti_rot().encode(lossless=True, format_version=1)
    )
    for name, payload in (("still", still), ("legacy", legacy), ("protected", protected)):
        path = Path(tmp_path) / f"{name}.wimf"
        path.write_bytes(payload)
        assert wimf.is_wimf(payload) and wimf.is_wimf(path)
