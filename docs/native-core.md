# Native C++ core

The code in `src/v2_core.hpp` and `src/v2_core.cpp` is a standalone C++17 library. It does not include Python, NumPy, Pillow, or pybind11. `src/v2_bindings.cpp` is the separate Python adapter.

The core exposes memory-only `encode_image` and `decode_image` operations, tile classification and mode evaluation, Predictive and Palette coding, reversible and irreversible wavelet transforms, CRC32, Zstandard entropy coding, ROI reconstruction, and WIM2 container parsing/writing. Buffers use explicit dimensions, channel counts, bytes per sample, row strides, and byte vectors.

Zstandard 1.5.7 is pinned under `third_party/zstd`. The codec does not read files, mutate process-wide state, or depend on an operating-system API.

## Embedding

Compile the core into your application and include the public header:

```bash
cc -O2 -Ithird_party/zstd -c third_party/zstd/zstd.c -o zstd.o
c++ -std=c++17 -O2 -Isrc -Ithird_party/zstd your_program.cpp src/v2_core.cpp zstd.o -pthread -o your_program
```

```cpp
#include "v2_core.hpp"

wimf::v2::EncodeOptions options;
options.lossless = true;
options.execution_policy = wimf::v2::ExecutionPolicy::Threaded;

std::vector<std::uint8_t> encoded;
wimf::v2::CodecStats stats;
auto status = wimf::v2::encode_image(image_view, options, encoded, &stats);
if (!status) {
    // status.code and status.message contain a stable failure description.
}
```

Both complete-image functions are `noexcept`: exceptions are contained at the facade and returned as a structured status. `DecodeOptions::roi` decodes only intersecting independently compressed tiles. The parser validates offsets, dimensions, expansion bounds, entropy IDs, and tile checksums before reconstruction.

`compare_images` calculates a native difference buffer, MSE, maximum error, and PSNR. `rewrite_metadata` rebuilds the base header and tile index while copying compressed payloads unchanged. Optional `OperationControl` function pointers report stage/tile progress and cooperatively cancel work between tiles without introducing Python or operating-system dependencies.

## Portability

Scalar C++17 is the reference implementation. `ExecutionPolicy::Synchronous` is the portable/WASM-ready path; desktop builds can select `Threaded` for deterministic tile scheduling. Emscripten builds automatically remain synchronous. Architecture-specific kernels must produce equivalent coefficients and decoded pixels and retain a scalar fallback. Python wheels build the core and bindings together; matching wheels do not require an end-user compiler.
