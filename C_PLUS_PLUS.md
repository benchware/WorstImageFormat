# WIMF C++ Engine Documentation

WIMF (Worst IMage Format) uses a high-performance C++ core to handle computationally intensive image processing tasks. This document provides instructions for building, extending, and maintaining the C++ components.

## 🚀 Architecture Overview

The C++ engine is located in `src/main.cpp` and is exposed to Python via `pybind11`. It focuses on three critical areas:

1.  **SIMD-Accelerated Haar Wavelets**: Uses manual AVX2 (x86) and NEON (ARM) intrinsics to process 2x2 wavelet blocks in parallel.
2.  **Reversible YCoCg-R**: A bit-perfect integer-based color transform implemented in C++ for maximum speed during lossless and lossy encoding.
3.  **Fast Paeth Predictor**: Accelerates the lossless spatial prediction filter used in WIMF's "PNG-style" compression.

## 🛠️ Building the Extension

### Prerequisites
- A modern C++ compiler (GCC 7+, Clang 10+, or MSVC 2019+)
- `pybind11` (`pip install pybind11`)
- `setuptools`

### Local Development Build
To build the extension in-place for local testing:
```bash
pip install -e .
```
This will compile `src/main.cpp` and place the resulting shared object (`.so` or `.pyd`) in the `wimf/` directory.

### Manual Build (Alternative)
```bash
python setup.py build_ext --inplace
```

## 🏎️ SIMD Optimizations

The engine automatically detects the target architecture during compilation:

- **x86_64**: Enables **AVX2** and **FMA** support (`-mavx2 -mfma`).
- **ARM (aarch64)**: Enables **NEON** support.
- **WebAssembly (Wasm)**: Enables compilation via Emscripten with `EMSCRIPTEN_KEEPALIVE` exports.

The Haar transform implementation (`haar_level` and `ihaar_level`) uses:
- **AVX2** (256-bit) on x86_64 to process 4 blocks simultaneously.
- **NEON** (128-bit) on ARM/Android to process 4 blocks simultaneously using `vld2q_f32` and `vst1q_f32`.

## 🌐 Web & Mobile Support

### WebAssembly (Wasm)
The core algorithms are exported with C linkage for Wasm compatibility. Functions like `ycocg_forward_raw` and `haar_level_raw` can be called directly from JavaScript when compiled with Emscripten.

### Android
The C++ core is optimized for Android using NEON intrinsics, ensuring the WIMF codec remains high-performance on mobile hardware. It is recommended to build using the Android NDK with `-O3` and NEON enabled.

## 🧪 Testing

The C++ components are verified using `pytest`. Ensure you have the extension built before running tests:
```bash
pip install pytest numpy pillow
pytest wimf/
```

## 📂 File Structure

- `src/main.cpp`: The monolithic C++ source containing all core algorithms and Python bindings.
- `setup.py`: Build configuration for the C++ extension.
- `.github/workflows/wheels.yml`: Production CI that builds optimized binary wheels for multiple platforms.

## 🔧 Extending the C++ Engine

To add a new function to the C++ core:

1.  Implement the logic in `src/main.cpp`.
2.  Define the binding in the `PYBIND11_MODULE(wimf_cpp, m)` block at the bottom of the file.
3.  Update `wimf/core.py` or `wimf/codec.py` to call the new C++ function with a Python fallback.

### Binding Example:
```cpp
m.def("my_new_function", &my_new_function, "Description of what it does");
```

## 📦 Production Distribution

Production builds are handled by `cibuildwheel` in the GitHub Actions workflow. This ensures that users on Linux, Windows, and macOS receive pre-compiled binaries optimized for their specific CPU architecture.
