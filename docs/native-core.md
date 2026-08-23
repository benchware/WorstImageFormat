# Native C++ core

The code in `src/v2_core.hpp` and `src/v2_core.cpp` is a standalone C++17 library. It does not include Python, NumPy, Pillow, or pybind11. `src/v2_bindings.cpp` is the separate Python adapter.

The core exposes memory-only `encode_image` and `decode_image` operations, tile classification and mode evaluation, Predictive and Palette coding, reversible and irreversible wavelet transforms, CRC32, Zstandard entropy coding, ROI reconstruction, and WIM2 container parsing/writing. Buffers use explicit dimensions, channel counts, bytes per sample, row strides, and byte vectors.

## Experimental C ABI

`src/wimf_c.h` exposes ABI version 1 without C++ standard-library types. Callers
initialize options with `wimf_encode_options_init` or
`wimf_decode_options_init`, then call `wimf_encode` or `wimf_decode`. Output
memory is owned by WIMF and must be released with `wimf_buffer_free` or
`wimf_decoded_image_free`.

The `struct_size` fields provide forward compatibility and
`wimf_abi_version()` supports runtime negotiation. Export visibility and shared
library ABI versioning are implemented; the bridge remains experimental until
normative conformance vectors and compatibility tests are complete.

```c
#include "wimf_c.h"

wimf_encode_options options;
wimf_encode_options_init(&options);
options.lossless = 1;

wimf_buffer encoded = {0};
wimf_status status = wimf_encode(&image, &options, &encoded);
if (status.code == WIMF_STATUS_OK) {
    /* consume encoded.data / encoded.size */
}
wimf_buffer_free(&encoded);
```

Build and install the shared library with CMake:

```bash
cmake -S . -B build-native -DBUILD_SHARED_LIBS=ON -DWIMF_BUILD_TESTS=ON
cmake --build build-native --config Release
ctest --test-dir build-native --build-config Release --output-on-failure
cmake --install build-native --prefix /your/install/prefix
```

Consumers can then use `find_package(WIMF CONFIG REQUIRED)` and link
`WIMF::wimf`. The installed shared-library major version follows the C ABI
version, independently of the WIM2 bitstream version.

The default CMake build also installs `wimf-native`, a deliberately small
process bridge built exclusively on the C ABI:

```bash
wimf-native encode source.ppm output.wimf
wimf-native encode source.pgm output.wimf --lossy 7
wimf-native decode output.wimf restored.ppm
```

It accepts 8-bit binary PGM (P5) and PPM (P6). Set `WIMF_BUILD_TOOLS=OFF` when
only the library is required. The tool owns filesystem I/O; the codec core
remains memory-only and dependency-free.

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

The C ABI exposes the same callback contract through its encode and decode
option records. CI also builds the standalone core conformance binary with
Emscripten and runs it under Node.js, making WebAssembly portability tested
rather than a compile-only claim.

## Portability

Scalar C++17 is the reference implementation with runtime-dispatched NEON (ARMv8) and AVX2 (x86-64) SIMD acceleration for CRC-32 checksums and predictive filter encoding: ISA-specific kernels live in dedicated translation units, are selected per CPU at load time (CPUID/XGETBV on x86-64, `getauxval(AT_HWCAP)` for the ARM CRC extension), and every path keeps a scalar fallback so one binary runs safely on any host. `ExecutionPolicy::Synchronous` is the portable/WASM-ready path; desktop builds can select `Threaded` for deterministic tile scheduling. Emscripten builds automatically remain synchronous. Architecture-specific kernels must produce equivalent coefficients and decoded pixels and retain a scalar fallback. Python wheels build the core and bindings together; matching wheels do not require an end-user compiler.
