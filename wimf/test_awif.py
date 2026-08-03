"""AWIF compatibility, timing, quality, preset, and geometry coverage."""

import json
import struct

import numpy as np
import pytest
from PIL import Image, ImageSequence

import wimf
from wimf.animation import decode_animated, encode_animated


def moving_frames(width, height, count, channels=3):
    y, x = np.indices((height, width))
    frames = []
    for index in range(count):
        image = np.empty((height, width, channels), dtype=np.uint8)
        image[..., 0] = (x * 3 + index * 11) & 255
        image[..., 1] = (y * 5 + index * 7) & 255
        image[..., 2] = ((x + y) * 2 + index * 13) & 255
        if channels == 4:
            image[..., 3] = (x + index * 17) & 255
        frames.append(image)
    return frames


def awif_container(frames, *, quality=5, preset="Balanced", fps=30, durations=None):
    height, width, channels = frames[0].shape
    metadata = {
        "channels": channels,
        "fps": fps,
        "frame_durations_ms": durations or [round(1000 / fps)] * len(frames),
        "loop": 0,
    }
    encoded = encode_animated([frame.tobytes() for frame in frames], width, height, channels, quality, preset)
    metadata_bytes = json.dumps(metadata).encode("utf-8")
    return b"AWIF" + struct.pack("<IIBI", width, height, 7, len(metadata_bytes)) + metadata_bytes + encoded


@pytest.mark.parametrize("fps", [1, 12, 24, 30, 60])
def test_awif_constant_fps_metadata(fps):
    payload = awif_container(moving_frames(33, 19, 4), fps=fps)
    decoder = wimf.WIMFDecoder(payload)
    assert decoder.num_states == 4
    assert decoder.duration_ms == 4 * round(1000 / fps)
    assert decoder.fps == pytest.approx(1000 / round(1000 / fps))


def test_awif_variable_frame_durations():
    durations = [20, 40, 80, 160]
    decoder = wimf.WIMFDecoder(awif_container(moving_frames(48, 32, 4), durations=durations))
    assert decoder.frame_durations_ms == durations
    assert decoder.duration_ms == 300
    assert decoder.fps == pytest.approx(13.333333)


@pytest.mark.parametrize("width,height", [(1, 1), (31, 17), (128, 72), (320, 180)])
@pytest.mark.parametrize("channels", [3, 4])
def test_awif_resolution_and_channels(width, height, channels):
    frames = moving_frames(width, height, 3, channels)
    payload = awif_container(frames, quality=7, preset="Fast")
    decoder = wimf.WIMFDecoder(payload)
    assert (decoder.width, decoder.height, decoder.channels, decoder.num_states) == (width, height, channels, 3)
    for index in range(3):
        decoded = decoder.decode_chrono_state(index)
        assert decoded.pil.size == (width, height)
        assert decoded.pil.mode == ("RGBA" if channels == 4 else "RGB")


@pytest.mark.parametrize("quality", range(1, 11))
@pytest.mark.parametrize("preset", ["Fast", "Balanced", "Extreme"])
def test_awif_quality_preset_matrix(quality, preset):
    frames = moving_frames(32, 24, 3)
    encoded = encode_animated([frame.tobytes() for frame in frames], 32, 24, 3, quality, preset)
    decoded = decode_animated(encoded, 32, 24, 3)
    assert len(decoded) == len(frames)
    assert all(len(frame) == 32 * 24 * 3 for frame in decoded)
    assert np.mean((np.frombuffer(decoded[-1], np.uint8).astype(float) - frames[-1].reshape(-1)) ** 2) < 400


def test_awif_keyframe_boundary_and_random_access():
    frames = moving_frames(16, 12, 31)
    decoder = wimf.WIMFDecoder(awif_container(frames, quality=6))
    assert decoder.num_states == 31
    assert decoder.decode_chrono_state(0).pil.size == (16, 12)
    assert decoder.decode_chrono_state(29).pil.size == (16, 12)
    assert decoder.decode_chrono_state(30).pil.size == (16, 12)


def test_legacy_awif_defaults_to_30_fps():
    frames = moving_frames(8, 8, 2)
    encoded = encode_animated([frame.tobytes() for frame in frames], 8, 8, 3)
    metadata = json.dumps({"channels": 3}).encode()
    decoder = wimf.WIMFDecoder(b"AWIF" + struct.pack("<IIBI", 8, 8, 7, len(metadata)) + metadata + encoded)
    assert decoder.frame_durations_ms == [33, 33]


@pytest.mark.parametrize(
    "payload,match",
    [
        (b"", "header"),
        (struct.pack("<II", 0, 0), "frame count"),
        (struct.pack("<II", 100_001, 0), "frame count"),
        (struct.pack("<II", 1, 99), "audio"),
        (struct.pack("<IIII", 1, 0, 0, 7), "frame type"),
    ],
)
def test_awif_rejects_malformed_animation_payloads(payload, match):
    with pytest.raises(ValueError, match=match):
        decode_animated(payload, 16, 16, 3)


def test_awif_rejects_truncation_and_trailing_bytes():
    frames = moving_frames(16, 12, 2)
    encoded = encode_animated([frame.tobytes() for frame in frames], 16, 12, 3)
    with pytest.raises(ValueError, match="truncated"):
        decode_animated(encoded[:-1], 16, 12, 3)
    with pytest.raises(ValueError, match="trailing"):
        decode_animated(encoded + b"junk", 16, 12, 3)


def test_awif_encoder_rejects_invalid_inputs():
    with pytest.raises(ValueError, match="between"):
        encode_animated([], 16, 16, 3)
    with pytest.raises(ValueError, match="frame size"):
        encode_animated([b"short"], 16, 16, 3)
    with pytest.raises(ValueError, match="quality"):
        encode_animated([bytes(16 * 16 * 3)], 16, 16, 3, quality=0)


def test_awif_gif_timing_roundtrip(tmp_path):
    source = tmp_path / "timed.gif"
    output = tmp_path / "timed.awif"
    exported = tmp_path / "exported.gif"
    frames = [Image.fromarray(frame) for frame in moving_frames(24, 16, 4)]
    durations = [20, 40, 60, 80]
    frames[0].save(source, save_all=True, append_images=frames[1:], duration=durations, loop=2)
    from wimf.cli import convert

    convert(str(source), str(output), quality=5, preset="Fast")
    decoder = wimf.WIMFDecoder(output)
    assert decoder.frame_durations_ms == durations
    assert decoder.duration_ms == sum(durations)
    assert decoder.metadata["loop"] == 2
    convert(str(output), str(exported))
    with Image.open(exported) as result:
        exported_durations = [frame.info["duration"] for frame in ImageSequence.Iterator(result)]
        assert exported_durations == durations
        assert result.info["loop"] == 2
