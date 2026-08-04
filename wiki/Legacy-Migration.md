# Legacy migration

WIMF 2.2 warns on legacy authoring. WIMF 3.0 removes legacy writers but retains read-only WIMF v1, `.wif`, AWIF, and `ROT!` compatibility.

```python
import wimf

legacy = wimf.open("legacy.wif")
wimf.save("current.wimf", legacy.pil, lossless=True)
```

The `.wif` extension was only a filename alias. Use `.wimf` for new WIM2 files.

For AWIF, decode states and either export individual frames or store them as WIM2 chrono history. Chrono history is indexed image history, not a timed animation replacement.
