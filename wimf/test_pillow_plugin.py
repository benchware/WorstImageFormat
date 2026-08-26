import io

import numpy as np
import pytest
from PIL import Image

import wimf  # noqa: F401 - importing WIMF registers the Pillow plugin


@pytest.mark.parametrize("mode,shape", [("L", (13, 17)), ("RGB", (13, 17, 3)), ("RGBA", (13, 17, 4))])
def test_pillow_plugin_lossless_open_save(mode, shape):
    source = np.arange(np.prod(shape), dtype=np.uint8).reshape(shape)
    image = Image.fromarray(source, mode=mode)
    stream = io.BytesIO()
    image.save(stream, format="WIMF", lossless=True, metadata={"bridge": "pillow"})
    assert stream.getvalue().startswith((b"WIM2", b"WIM3"))

    stream.seek(0)
    with Image.open(stream) as decoded:
        decoded.load()
        assert decoded.format == "WIMF"
        assert decoded.mode == mode
        assert decoded.size == image.size
        assert decoded.info["bridge"] == "pillow"
        assert np.array_equal(np.asarray(decoded), source)


def test_pillow_plugin_registers_canonical_extension_only():
    assert Image.registered_extensions()[".wimf"] == "WIMF"
    assert Image.MIME["WIMF"] == "image/x-wimf"
