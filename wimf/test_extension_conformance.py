import base64
import hashlib
import json
import struct
from pathlib import Path

import pytest

from .api import WIMFDecoder
from .extensions import parse_extensions

MANIFEST = Path(__file__).parents[1] / "tests" / "conformance" / "extensions.json"


def _payload(name):
    vector = json.loads(MANIFEST.read_text(encoding="utf-8"))["extensions"][name]
    payload = base64.b64decode(vector["wimf_base64"], validate=True)
    assert hashlib.sha256(payload).hexdigest() == vector["container_sha256"]
    return vector, payload


@pytest.mark.parametrize("name", ["history", "anti-rot", "protected-history"])
def test_committed_extension_vector(name):
    vector, payload = _payload(name)
    decoder = WIMFDecoder(payload)
    assert decoder.was_protected is vector["protected"]
    assert decoder.num_states == vector["states"]
    assert hashlib.sha256(decoder.decode().to_numpy().tobytes()).hexdigest() == vector["primary_pixels_sha256"]
    if vector["states"] > 1:
        state = decoder.decode_chrono_state(1).to_numpy().tobytes()
        assert hashlib.sha256(state).hexdigest() == vector["state_1_pixels_sha256"]


def test_anti_rot_repairs_one_damaged_data_shard_exactly():
    vector, payload = _payload("protected-history")
    parity = parse_extensions(payload, verify_checksums=False)[b"AROT"]["payload"]
    _, shard_count, shard_size = struct.unpack_from("<QII", parity, 4)
    assert shard_count >= 6
    damaged = bytearray(payload)
    damaged[3 * shard_size + 1] ^= 0x40
    decoder = WIMFDecoder(bytes(damaged))
    assert decoder.was_protected and decoder.was_repaired
    assert hashlib.sha256(decoder.decode().to_numpy().tobytes()).hexdigest() == vector["primary_pixels_sha256"]
    assert (
        hashlib.sha256(decoder.decode_chrono_state(1).to_numpy().tobytes()).hexdigest()
        == vector["state_1_pixels_sha256"]
    )


def test_anti_rot_rejects_three_damaged_data_shards():
    _, payload = _payload("protected-history")
    parity = parse_extensions(payload, verify_checksums=False)[b"AROT"]["payload"]
    _, _, shard_size = struct.unpack_from("<QII", parity, 4)
    damaged = bytearray(payload)
    for shard in (3, 4, 5):
        damaged[shard * shard_size + 1] ^= 0x20
    with pytest.raises(ValueError, match="too many corrupted"):
        WIMFDecoder(bytes(damaged))
