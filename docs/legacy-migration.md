# Legacy migration

WIMF 2.2 is the warning release. WIMF 3.0 removes legacy authoring while keeping
WIMF v1, AWIF, and `ROT!` decoding available.

## WIMF v1 or `ROT!` still image to WIM2

```python
import wimf

legacy = wimf.open("legacy.wimf")
wimf.save("current.wimf", legacy.pil, lossless=True)
```

## AWIF to frames or WIM2 history

```python
import wimf

legacy = wimf.WIMFDecoder("legacy.awif")
frames = [legacy.decode_chrono_state(i).pil for i in range(legacy.num_states)]

encoder = wimf.WIMFEncoder(frames[0])
for frame in frames[1:]:
    encoder.add_chrono_state(frame)
open("history.wimf", "wb").write(encoder.encode(lossless=True))
```

Export individual frames when animation playback is required; WIM2 chrono history
is indexed image history, not a replacement animation timing format.

Metadata and pixels are compressed, not encrypted. Do not place secrets in WIMF metadata.
