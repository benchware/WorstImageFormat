import subprocess
import sys

import numpy as np

import wimf
from wimf.diagnostics import corrupt, diagnose, unsafe_preview
from wimf.extensions import parse_extensions
from wimf.hybrid import parse_v2
from wimf.studio_model import EncodeSettings, StudioDocument


def test_base64_and_data_url_roundtrip():
    image = np.arange(19 * 23 * 3, dtype=np.uint8).reshape(19, 23, 3)
    payload = wimf.encode(image, lossless=True)
    wrapped = wimf.to_base64(payload, wrap=76)
    assert "\n" in wrapped and wimf.from_base64(wrapped) == payload
    assert wimf.from_data_url(wimf.to_data_url(payload)) == payload
    for invalid in ("not base64!", "data:image/png;base64,AAAA"):
        try:
            wimf.from_data_url(invalid) if invalid.startswith("data:") else wimf.from_base64(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid Base64 transport was accepted")


def test_corruption_diagnosis_and_unsafe_preview():
    image = np.random.default_rng(31).integers(0, 256, (133, 259, 3), dtype=np.uint8)
    payload = wimf.encode(image, lossless=True, codec="predictive", format_version=2)
    damaged = corrupt(payload, seed=9, area="payload", tile=(128, 0))
    report = diagnose(damaged)
    assert not report["strict_ok"]
    assert sum(not tile["checksum_valid"] for tile in report["tiles"]) == 1
    preview, failed = unsafe_preview(damaged)
    assert preview.shape == image.shape and len(failed) == 1
    assert np.array_equal(preview[128:, :128], image[128:, :128])


def test_metadata_rewrite_preserves_payloads_and_extensions():
    image = np.random.default_rng(32).integers(0, 256, (131, 257, 4), dtype=np.uint8)
    payload = wimf.encode(image, lossless=True, anti_rot=True, format_version=2, metadata={"before": 1})
    before = parse_v2(payload)
    before_payloads = [payload[entry[8] : entry[8] + entry[9]] for entry in before["entries"]]
    rewritten = wimf.rewrite_metadata(payload, {"after": 2})
    after = parse_v2(rewritten)
    after_payloads = [rewritten[entry[8] : entry[8] + entry[9]] for entry in after["entries"]]
    assert before_payloads == after_payloads
    assert after["metadata"]["after"] == 2
    assert b"AROT" in parse_extensions(rewritten)
    assert np.array_equal(wimf.decode(rewritten).to_numpy(), image)


def test_native_or_fallback_comparison_metrics():
    first = np.zeros((7, 9, 3), dtype=np.uint8)
    second = first.copy()
    second[2, 4, 1] = 5
    result = wimf.compare(first, second)
    assert result["maximum_error"] == 5
    assert np.isclose(result["mse"], 25 / first.size)
    assert result["difference"][2, 4, 1] == 5


def test_studio_document_headless_encode():
    document = StudioDocument(source=np.zeros((17, 21, 3), dtype=np.uint8), metadata={"studio": True})
    result = document.encode(EncodeSettings(lossless=True))
    document.apply_encode_result(result)
    assert document.dirty and document.details["format"] in ("WIM2", "WIM3")
    assert document.metrics["maximum_error"] == 0


def test_operation_token_cancels_before_first_tile():
    token = wimf.operation_token()
    token.cancel()
    try:
        wimf.encode(np.zeros((257, 259, 3), dtype=np.uint8), lossless=True, operation_token=token, format_version=2)
    except ValueError as error:
        assert "cancel" in str(error)
    else:
        raise AssertionError("cancelled encode completed")


def test_studio_and_headless_cli_help():
    subprocess.run([sys.executable, "-m", "wimf.studio_cli", "--help"], check=True, capture_output=True)
    result = subprocess.run([sys.executable, "-m", "wimf", "base64", "--help"], check=True, capture_output=True)
    assert b"encode" in result.stdout and b"decode" in result.stdout
