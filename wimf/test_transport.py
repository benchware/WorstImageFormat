import pytest

import wimf
from wimf.commands import build_parser


@pytest.mark.parametrize(
    "encode,decode",
    [(wimf.to_base16, wimf.from_base16), (wimf.to_base32, wimf.from_base32), (wimf.to_base64, wimf.from_base64)],
)
def test_bounded_base_transports_roundtrip_with_whitespace(encode, decode):
    payload = b"WIM2\x00\x01\xfftransport"
    text = encode(payload, wrap=8)
    assert decode(f" \n{text}\t") == payload


@pytest.mark.parametrize(
    "decode,value",
    [
        (wimf.from_base16, "aa"),
        (wimf.from_base16, "GG"),
        (wimf.from_base32, "lowercase"),
        (wimf.from_base32, "MZXW6"),
        (wimf.from_base64, "not+valid="),
    ],
)
def test_base_transports_reject_noncanonical_or_invalid_text(decode, value):
    with pytest.raises(ValueError, match="invalid"):
        decode(value)


@pytest.mark.parametrize("name", ["base16", "base32", "base64"])
def test_cli_exposes_all_base_transport_commands(name):
    args = build_parser().parse_args([name, "encode", "input.wimf"])
    assert callable(args.handler)
