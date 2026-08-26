"""Array-to-PIL conversion helpers shared by the Studio views."""

import numpy as np
from PIL import Image


def _display_array(array):
    value = np.asarray(array)
    if value.dtype != np.uint8:
        maximum = max(1, int(value.max(initial=1)))
        value = np.rint(value.astype(np.float64) * (255 / maximum)).astype(np.uint8)
    if value.ndim == 3 and value.shape[2] == 1:
        value = value[..., 0]
    if value.ndim == 3 and value.shape[2] > 4:
        value = value[..., :3]
    return Image.fromarray(value)
