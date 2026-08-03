import json
import logging

from .animation import decode_animated, encode_animated
from .codec import decode_lossless, decode_lossy, encode_lossless, encode_lossy
from .core import parse_header
from .hybrid import MAGIC as V2_MAGIC
from .hybrid import decode_v2, encode_v2, parse_v2

logger = logging.getLogger(__name__)


def stream_load(filename):
    """
    Generator that yields progressively better versions of the image.
    Yields: (w, h, pix, meta, is_final)
    """
    with open(filename, "rb") as f:
        raw = f.read()

    if raw[:4] == V2_MAGIC:
        info = parse_v2(raw)
        pix, _ = decode_v2(raw)
        yield info["width"], info["height"], pix, info["metadata"], True
        return

    magic, w, h, flags, mlen = parse_header(raw)
    if magic != b"WIMF":
        raise ValueError("Streaming only supported for STILL WIMF files")

    meta = json.loads(raw[17 : 17 + mlen].decode("utf-8")) if mlen > 0 else {}
    data = raw[17 + mlen :]
    channels = meta.get("channels", 3)
    bit_depth = 10 if meta.get("bit10") else 8

    if flags == 1:  # Lossless
        yield w, h, decode_lossless(data, w, h, channels), meta, True
        return

    # Check for Progressive Mode (9)
    mode = data[0] & 0x0F
    if mode == 9:
        for layer in range(3):
            pix = decode_lossy(data, w, h, channels, bit_depth=bit_depth, target_layer=layer)
            yield w, h, pix, meta, (layer == 2)
    else:
        # Legacy or other
        pix = decode_lossy(data, w, h, channels, bit_depth=bit_depth)
        yield w, h, pix, meta, True


def loadImage(filename, target_layer=2, roi=None, mip_level=0):
    with open(filename, "rb") as f:
        raw = f.read()

    if raw[:4] == V2_MAGIC:
        info = parse_v2(raw)
        pix, _ = decode_v2(raw, roi=roi, target_layer=target_layer)
        w, h = (roi[2], roi[3]) if roi else (info["width"], info["height"])
        return w, h, pix, info["metadata"]

    magic, w, h, flags, mlen = parse_header(raw)
    meta = json.loads(raw[17 : 17 + mlen].decode("utf-8")) if mlen > 0 else {}
    data = raw[17 + mlen :]
    channels = meta.get("channels", 3)
    bit_depth = 10 if meta.get("bit10") else 8

    if magic == b"AWIF":
        frames = decode_animated(data, w, h, channels, bit_depth=bit_depth, metadata=meta)
        meta["is_animated"] = True
        return w, h, frames, meta
    if flags == 1:
        pix = decode_lossless(data, w, h, channels)
    elif flags in [5, 6, 8, 9, 10]:
        pix = decode_lossy(
            data,
            w,
            h,
            channels,
            bit_depth=bit_depth,
            target_layer=target_layer,
            roi=roi,
            mip_level=mip_level,
            metadata=meta,
        )
    else:
        pix = data
    return w, h, pix, meta


def saveImage(
    filename,
    w,
    h,
    pixels,
    compression=1,
    quality=5,
    metadata=None,
    preset="Balanced",
    format_version=2,
    codec="auto",
    threads=None,
):
    if str(filename).lower().endswith(".wif"):
        from .deprecation import warn_legacy

        warn_legacy("the .wif filename alias", "use the .wimf extension for WIM2 output instead")
    if metadata is None:
        metadata = {}
    is_animated = isinstance(pixels, list)
    bit_depth = 10 if metadata.get("bit10") else 8

    if is_animated:
        first_frame = pixels[0]
        if hasattr(first_frame, "tobytes"):
            channels = first_frame.shape[-1] if len(first_frame.shape) == 3 else 1
            pixels = [f.tobytes() for f in pixels]
        else:
            div = 2 if bit_depth > 8 else 1
            channels = len(first_frame) // (w * h * div)
    else:
        if hasattr(pixels, "tobytes"):
            channels = pixels.shape[-1] if len(pixels.shape) == 3 else 1
            pixels = pixels.tobytes()
        else:
            div = 2 if bit_depth > 8 else 1
            channels = len(pixels) // (w * h * div)

    metadata["channels"] = channels
    m_bytes = json.dumps(metadata).encode("utf-8")
    magic = b"AWIF" if is_animated else b"WIMF"

    if format_version == 2 and not is_animated:
        raw = pixels.tobytes() if hasattr(pixels, "tobytes") else pixels
        encoded = encode_v2(
            raw,
            w,
            h,
            channels,
            bit_depth=bit_depth,
            quality=quality,
            lossless=(compression == 1),
            preset=preset,
            codec=codec,
            metadata=metadata,
            threads=threads,
        )
        with open(filename, "wb") as f:
            f.write(encoded)
        return

    if is_animated:
        data = encode_animated(pixels, w, h, channels, quality, preset, bit_depth=bit_depth)
        final_flags = 7
    else:
        if compression == 2:
            data = encode_lossy(
                pixels, w, h, quality=quality, preset=preset, channels=channels, bit_depth=bit_depth, metadata=metadata
            )
            final_flags = data[0] & 0x0F  # derive from codec output, not hardcoded
        elif compression == 1:
            data = encode_lossless(pixels, w, h, channels, preset=preset)
            final_flags = 1
        else:
            data = pixels
            final_flags = 0

    with open(filename, "wb") as f:
        f.write(magic)
        f.write(w.to_bytes(4, "little") + h.to_bytes(4, "little"))
        f.write(final_flags.to_bytes(1, "little"))
        f.write(len(m_bytes).to_bytes(4, "little") + m_bytes + data)
