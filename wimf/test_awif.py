"""Read-only compatibility checks for committed AWIF-era payloads."""

import base64
from pathlib import Path

import numpy as np
import pytest

from wimf.animation import decode_animated, encode_animated

FIXTURE = Path(__file__).parents[1] / "tests" / "fixtures" / "legacy" / "awif-animation.b64"


def test_committed_awif_animation_payload_decodes():
    payload = base64.b64decode(FIXTURE.read_text(encoding="ascii").strip(), validate=True)
    frames = decode_animated(payload, 4, 4, 3)
    assert len(frames) == 2
    assert np.frombuffer(frames[0], np.uint8).reshape(4, 4, 3).max() == 0
    assert len(frames[1]) == 4 * 4 * 3


def test_awif_writer_warns_during_22_transition():
    with pytest.warns(FutureWarning, match="removed in WIMF 3.0"):
        payload = encode_animated([bytes(4 * 4 * 3)], 4, 4, 3)
    assert decode_animated(payload, 4, 4, 3)


@pytest.mark.parametrize("payload", [b"", b"\x01\x00\x00\x00"])
def test_legacy_decoder_rejects_truncation(payload):
    with pytest.raises(ValueError, match="truncated"):
        decode_animated(payload, 4, 4, 3)
