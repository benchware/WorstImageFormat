# Native integration

The portable core lives in `src/v2_core.hpp` and `src/v2_core.cpp`. It uses C++17, memory buffers, structured status results, and pinned Zstandard. It does not depend on Python, NumPy, Pillow, pybind11, filesystem APIs, or global mutable state.

The core exposes complete-image encode/decode, ROI reconstruction, comparison, metadata rewriting, progress/cancellation hooks, and runtime information.

The experimental `src/wimf_c.h` bridge exposes ABI version 1 using plain C structures, initialized option records, structured status codes, and explicit output-buffer release functions. Third-party applications should target this boundary once it is marked stable rather than binding directly to C++ standard-library types.

Planned consumers are Pillow, ImageMagick/GraphicsMagick, FFmpeg, desktop thumbnail providers, WebAssembly, and Rust.
