# Native C++ core

The code in `src/v2_core.hpp` and `src/v2_core.cpp` is a standalone C++17 library. It does not include Python, NumPy, Pillow, or pybind11. `src/v2_bindings.cpp` is the separate Python adapter.

The core exposes image views, tile classification, Predictive and Palette coding, reversible and irreversible wavelet transforms, CRC32, and WIM2 container parsing/writing. Buffers use explicit dimensions, channel counts, bytes per sample, row strides, and byte vectors.

## Embedding

Compile the core into your application and include the public header:

```bash
c++ -std=c++17 -O2 -Isrc your_program.cpp src/v2_core.cpp -o your_program
```

```cpp
#include "v2_core.hpp"

auto info = wimf::v2::parse_container(bytes.data(), bytes.size());
for (const auto& tile : info.tiles) {
    // Fetch tile bytes using tile.offset and tile.size.
}
```

`parse_container` validates the base structure but does not allocate expanded tile output. Applications must dispatch by recorded mode and entropy ID, enforce their own total memory budget, and verify tile CRCs before decoding.

## Portability

Scalar C++17 is the reference implementation. Architecture-specific kernels must produce equivalent coefficients and decoded pixels and must retain a scalar fallback. Python wheels build the core and bindings together; matching wheels do not require an end-user compiler.
