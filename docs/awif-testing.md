# AWIF compatibility and test matrix

AWIF is WIMF's legacy animation container. Animation creation remains legacy-only while the WIM2 still-image pipeline is developed. AWIF stores compressed frames; playback timing is represented by backward-compatible JSON metadata.

## Timing behavior

- `frame_durations_ms` preserves every source GIF frame duration, including variable frame rates.
- `fps` records the average playback rate for tools that need a single number.
- `loop` preserves the GIF loop count.
- Old AWIF files without timing metadata play at the historical 30 FPS default (33 ms per frame).
- FPS changes playback duration, not compressed frame bytes. Quality and preset control compression independently.

## Continuous-integration coverage

The AWIF correctness job tests 1, 12, 24, 30, and 60 FPS; variable frame durations; RGB and RGBA; odd and conventional resolutions from 1×1 through 320×180; every quality from 1 through 10 under Fast, Balanced, and Extreme; the 30-frame keyframe boundary; random state access; GIF timing import; and legacy timing defaults.

The still-image suite likewise runs every quality from 1 through 10 under all three presets. Separate forced-mode tests cover Raw, Predictive, Palette, and Wavelet, while the visual report uses representative configurations on synthetic, nature, and animal fixtures so its summary remains readable.

The AWIF benchmark is separate from correctness tests. It reports Python versus C++-accelerated encode/decode throughput and size on Linux, Windows, and macOS. Measurements are uploaded as artifacts and written to the job summary; they are diagnostic and do not make packaging fixes fail.

Still-image visual comparisons, standalone C++ tests, sanitizers, packaging, and cross-platform Python tests remain separate jobs so each failure identifies one subsystem.
