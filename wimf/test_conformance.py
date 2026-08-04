import base64
import hashlib
import json
from pathlib import Path

import pytest

from . import hybrid

MANIFEST = Path(__file__).parents[1] / "tests" / "conformance" / "vectors.json"


@pytest.mark.parametrize("name", ["raw", "predictive", "palette", "wavelet"])
def test_committed_wim2_decoder_vector(name):
    vector = json.loads(MANIFEST.read_text(encoding="utf-8"))["vectors"][name]
    container = base64.b64decode(vector["wimf_base64"], validate=True)
    assert hashlib.sha256(container).hexdigest() == vector["container_sha256"]
    parsed = hybrid.parse_v2(container)
    assert hybrid.MODE_NAMES[parsed["entries"][0][4]] == vector["mode"]

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
