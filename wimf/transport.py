"""Bounded Base16, Base32, Base64, and data-URL transport helpers."""

import base64
import binascii
import os

MIME_TYPE = "image/x-wimf"
MAX_TRANSPORT_BYTES = 1024 * 1024 * 1024


def _read_bytes(source):
    if isinstance(source, (str, os.PathLike)):
        with open(source, "rb") as stream:
            data = stream.read(MAX_TRANSPORT_BYTES + 1)
    else:
        data = bytes(source)
    if len(data) > MAX_TRANSPORT_BYTES:
        raise ValueError("WIMF transport input exceeds the safety limit")
    return data


def to_base64(source, *, wrap=0):
    """Encode WIMF bytes or a file as validated ASCII Base64 text."""
    encoded = base64.b64encode(_read_bytes(source)).decode("ascii")
    if wrap:
        if wrap < 4:
            raise ValueError("Base64 wrap width must be at least 4")
        return "\n".join(encoded[index : index + wrap] for index in range(0, len(encoded), wrap))
    return encoded


def _wrap(encoded, width, label):
    if not width:
        return encoded
    if width < 4:
        raise ValueError(f"{label} wrap width must be at least 4")
    return "\n".join(encoded[index : index + width] for index in range(0, len(encoded), width))


def to_base16(source, *, wrap=0):
    """Encode bytes or a file as uppercase RFC 4648 Base16 text."""
    return _wrap(base64.b16encode(_read_bytes(source)).decode("ascii"), wrap, "Base16")


def to_base32(source, *, wrap=0):
    """Encode bytes or a file as padded RFC 4648 Base32 text."""
    return _wrap(base64.b32encode(_read_bytes(source)).decode("ascii"), wrap, "Base32")


def from_base64(value):
    """Decode Base64 text using strict alphabet and padding validation."""
    if isinstance(value, bytes):
        value = value.decode("ascii")
    compact = "".join(str(value).split())
    if len(compact) > ((MAX_TRANSPORT_BYTES + 2) // 3) * 4:
        raise ValueError("Base64 input exceeds the safety limit")
    try:
        decoded = base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(f"invalid Base64 WIMF data: {error}") from error
    if len(decoded) > MAX_TRANSPORT_BYTES:
        raise ValueError("decoded WIMF data exceeds the safety limit")
    return decoded


def _compact_ascii(value, label):
    if isinstance(value, bytes):
        try:
            value = value.decode("ascii")
        except UnicodeDecodeError as error:
            raise ValueError(f"invalid {label} WIMF data: non-ASCII input") from error
    return "".join(str(value).split())


def from_base16(value):
    """Decode uppercase RFC 4648 Base16 with whitespace tolerance."""
    compact = _compact_ascii(value, "Base16")
    if len(compact) > MAX_TRANSPORT_BYTES * 2:
        raise ValueError("Base16 input exceeds the safety limit")
    try:
        decoded = base64.b16decode(compact, casefold=False)
    except (binascii.Error, ValueError) as error:
        raise ValueError(f"invalid Base16 WIMF data: {error}") from error
    return decoded


def from_base32(value):
    """Decode padded uppercase RFC 4648 Base32 with strict alphabet checks."""
    compact = _compact_ascii(value, "Base32")
    if len(compact) > ((MAX_TRANSPORT_BYTES + 4) // 5) * 8:
        raise ValueError("Base32 input exceeds the safety limit")
    try:
        decoded = base64.b32decode(compact, casefold=False)
    except (binascii.Error, ValueError) as error:
        raise ValueError(f"invalid Base32 WIMF data: {error}") from error
    if len(decoded) > MAX_TRANSPORT_BYTES:
        raise ValueError("decoded WIMF data exceeds the safety limit")
    return decoded


def to_data_url(source):
    return f"data:{MIME_TYPE};base64,{to_base64(source)}"


def from_data_url(value):
    if isinstance(value, bytes):
        value = value.decode("ascii")
    prefix = f"data:{MIME_TYPE};base64,"
    if not str(value).startswith(prefix):
        raise ValueError(f"expected a {MIME_TYPE} Base64 data URL")
    return from_base64(str(value)[len(prefix) :])
