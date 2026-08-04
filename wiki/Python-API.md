# Python API

## Encode and save

```python
from PIL import Image
import wimf

image = Image.open("source.png")
wimf.save("output.wimf", image, quality=7, preset="Balanced", codec="auto")
```

Lossless output:

```python
wimf.save("exact.wimf", image, lossless=True)
```

The presets are `Fast`, `Balanced`, and `Extreme`. Forced codecs are `raw`, `predictive`, `palette`, and `wavelet`; `auto` selects per tile.

## Decode

```python
decoded = wimf.open("output.wimf")
decoded.pil.save("decoded.png")
```

## ROI decoding

```python
region = wimf.decode("large.wimf", roi=(256, 128, 512, 512))
region.pil.save("region.png")
```

## Inspect without a full decode

```python
details = wimf.inspect("output.wimf")
print(details["tile_modes"])
print(details["metadata"])
```

## Metadata

```python
wimf.save("tagged.wimf", image, metadata={"author": "Example", "purpose": "test"})
```

Metadata is compressed, not encrypted.

## Protection and history

```python
encoder = wimf.WIMFEncoder(image).set_anti_rot(True)
encoder.add_chrono_state(next_image)
payload = encoder.encode(lossless=True)
```

Use `decode_chrono_state(index)` for random state access.
