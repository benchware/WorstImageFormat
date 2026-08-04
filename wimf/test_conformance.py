import base64
import hashlib
import json
from pathlib import Path

import pytest

from . import hybrid

MANIFEST = Path(__file__).parents[1] / "tests" / "conformance" / "vectors.json"


@pytest.mark.parametrize("name", json.loads(MANIFEST.read_text(encoding="utf-8"))["vectors"])
def test_committed_wim2_decoder_vector(name):
    vector = json.loads(MANIFEST.read_text(encoding="utf-8"))["vectors"][name]
    container = base64.b64decode(vector["wimf_base64"], validate=True)
    assert hashlib.sha256(container).hexdigest() == vector["container_sha256"]
    parsed = hybrid.parse_v2(container)
    actual_modes = {}
    for entry in parsed["entries"]:
        mode = hybrid.MODE_NAMES[entry[4]]
        actual_modes[mode] = actual_modes.get(mode, 0) + 1
    expected_modes = vector["modes"] if "modes" in vector else {vector["mode"]: 1}
    assert actual_modes == expected_modes
    assert parsed["metadata"]["conformance"] == name

    native_backend = hybrid.native
    backends = [None] + ([native_backend] if native_backend is not None else [])
    try:
        for selected in backends:
            hybrid.native = selected
            pixels, info = hybrid.decode_v2(container)
            assert hashlib.sha256(pixels).hexdigest() == vector["pixels_sha256"]
            assert (info["width"], info["height"], info["channels"], info["bit_depth"]) == (
                vector["width"],
                vector["height"],
                vector["channels"],
                vector["bit_depth"],
            )
    finally:
        hybrid.native = native_backend


def test_conformance_vector_payload_corruption_is_rejected():
    vector = json.loads(MANIFEST.read_text(encoding="utf-8"))["vectors"]["predictive"]
    damaged = bytearray(base64.b64decode(vector["wimf_base64"], validate=True))
    damaged[-1] ^= 1
    with pytest.raises(ValueError, match="checksum"):
        hybrid.decode_v2(bytes(damaged))


def test_reserved_progressive_layer_count_is_rejected():
    vector = json.loads(MANIFEST.read_text(encoding="utf-8"))["vectors"]["predictive"]
    damaged = bytearray(base64.b64decode(vector["wimf_base64"], validate=True))
    metadata_size = int.from_bytes(damaged[18:22], "little")
    first_entry = 26 + metadata_size
    damaged[first_entry + 10] = 2
    native_backend = hybrid.native
    try:
        hybrid.native = None
        with pytest.raises(ValueError, match="tile index"):
            hybrid.parse_v2(bytes(damaged))
    finally:
        hybrid.native = native_backend


def test_multitile_roi_crosses_four_edge_tiles_exactly():
    vector = json.loads(MANIFEST.read_text(encoding="utf-8"))["vectors"]["odd-multitile"]
    container = base64.b64decode(vector["wimf_base64"], validate=True)
    pixels, _ = hybrid.decode_v2(container, roi=(120, 120, 11, 9))
    assert len(pixels) == 11 * 9 * 3
    assert hashlib.sha256(pixels).hexdigest() == "6b1a74fccb68a06683884cf82d72205d4863706b2c66baf0e23a5573b86a7ae2"


def test_multitile_encoding_is_deterministic_across_thread_counts():
    vector = json.loads(MANIFEST.read_text(encoding="utf-8"))["vectors"]["odd-multitile"]
    container = base64.b64decode(vector["wimf_base64"], validate=True)
    pixels, _ = hybrid.decode_v2(container)
    outputs = [
        hybrid.encode_v2(
            pixels,
            vector["width"],
            vector["height"],
            vector["channels"],
            bit_depth=vector["bit_depth"],
            lossless=True,
            codec="predictive",
            preset="Extreme",
            metadata={"conformance": "thread-parity"},
            threads=threads,
        )
        for threads in (1, 2, 4)
    ]
    assert outputs[0] == outputs[1] == outputs[2]
