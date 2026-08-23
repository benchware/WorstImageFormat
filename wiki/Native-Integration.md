# Native integration

The portable core lives in `src/v2_core.hpp` and `src/v2_core.cpp`. It uses C++17, memory buffers, structured status results, and pinned Zstandard. It does not depend on Python, NumPy, Pillow, pybind11, filesystem APIs, or global mutable state.

The core exposes complete-image encode/decode, ROI reconstruction, comparison, metadata rewriting, progress/cancellation hooks, and runtime information.

The experimental `src/wimf_c.h` bridge exposes ABI version 1 using plain C structures, initialized option records, structured status codes, and explicit output-buffer release functions. Third-party applications should target this boundary once it is marked stable rather than binding directly to C++ standard-library types.

The root CMake project builds static or shared libraries, installs `wimf_c.h`,
and exports `WIMF::wimf` for `find_package(WIMF CONFIG REQUIRED)`. The shared
library uses ABI major version 1; this is independent of the WIM2 container
version and the canonical `.wimf` filename extension.

ABI v1 freezes symbol meanings, record fields, enum values, ownership, cleanup,
threading, and error behavior. Inputs are borrowed during calls; successful
outputs are owned by WIMF and must be released by the same loaded library. No
C++ exception may cross the C boundary, and independent calls may run concurrently.

Planned consumers are Pillow, ImageMagick/GraphicsMagick, FFmpeg, desktop thumbnail providers, WebAssembly, and Rust.

For integrations that cannot link a library yet, CMake also builds the small
`wimf-native` process bridge. It converts 8-bit binary PGM/PPM images to and
from `.wimf` using only the public C ABI. This keeps the bridge portable and
gives other languages an immediate integration path without making filesystem
or image-format dependencies part of the codec core.

Losslessness contract: decoded pixels are bit-exact if and only if the encoder
was given the explicit lossless flag. Quality never implies losslessness -
quality=10 stays a lossy tier on every preset - and the flag switches the
wavelet coder onto its reversible pipeline, so the two payloads always differ.
