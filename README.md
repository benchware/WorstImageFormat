# Worst IMage Format (wimf)

wimf but python library
## Installation

```bash
pip install .
```

## Usage

```python
import wimf

# Load an image
w, h, pixels, meta = wimf.load("image.wimf")

# Save an image
wimf.save("output.wimf", w, h, pixels, quality=8)
```

## Format Specification
wimf uses an open source spectral omniic ccodeec arthcicterture it seperates imegaes to frequenyc lyaers using a 2 level haaarr weavelet transform, applies chroma from luma cfl edge predictoon and compres the reodrered bitstaereem via lzma (artihtmemic) entroy coding

## License
GPL-3.0-or-later

