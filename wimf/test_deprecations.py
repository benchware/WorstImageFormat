import numpy as np
import pytest

import wimf


def test_v1_authoring_warns_and_remains_readable():
    image = np.zeros((8, 8, 3), dtype=np.uint8)
    with pytest.warns(FutureWarning, match="WIMF v1 authoring"):
        payload = wimf.encode(image, lossless=True, format_version=1)
    assert wimf.decode(payload).pil.size == (8, 8)


def test_invalid_native_facing_options_are_consistent():
    image = np.zeros((8, 8, 3), dtype=np.uint8)
    for options in ({"threads": 0}, {"preset": "Turbo"}, {"quality": 0}, {"codec": "bogus"}):
        with pytest.raises(ValueError):
            wimf.encode(image, **options)


def test_wif_filename_alias_warns_but_writes_wim2(tmp_path):
    output = tmp_path / "legacy-name.wif"
    image = np.zeros((8, 8, 3), dtype=np.uint8)
    with pytest.warns(FutureWarning, match=r"\.wif filename alias"):
        wimf.save(output, image, lossless=True, format_version=2)
    assert output.read_bytes().startswith(b"WIM2")
