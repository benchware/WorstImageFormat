# WorstImageFormat - Code Quality Issues & Fixes

## Critical Issues Found

### 1. **C++ Code Formatting Nightmare** (`src/main.cpp`)

**Problem:** Lines exceed 300+ characters. Lambda functions defined inline in pybind11 bindings.

**Example (Lines 265-270):**
```cpp
m.def("parse_header", [](py::array_t<uint8_t> d){ const uint8_t* p=d.data(0); uint32_t w,h,m_len; std::memcpy(&w,p+4,4); std::memcpy(&h,p+8,4); std::memcpy(&m_len,p+13,4); return py::make_tuple(...);
m.def("c_encode_lossy", &c_encode_lossy); m.def("c_decode_lossy", &c_decode_lossy);
```

**Fix:**
```cpp
auto parse_header_impl = [](py::array_t<uint8_t> d) {
    const uint8_t* p = d.data(0);
    uint32_t w, h, m_len;
    std::memcpy(&w, p + 4, 4);
    std::memcpy(&h, p + 8, 4);
    std::memcpy(&m_len, p + 13, 4);
    return py::make_tuple(w, h, m_len);
};
m.def("parse_header", parse_header_impl);
m.def("c_encode_lossy", &c_encode_lossy);
m.def("c_decode_lossy", &c_decode_lossy);
m.def("c_save_file", &c_save_file);
m.def("c_load_file", &c_load_file);
```

---

### 2. **Massive Functions - decode_lossy() is 640+ Lines**

**File:** `wimf/codec.py` lines 369-642

**Problems:**
- Deeply nested loops (4-5 levels)
- 11 parameters with complex conditional logic
- Two duplicate code paths (mode 9 vs mode 10) with >95% similarity
- Multiple nested functions

**Impact:** Impossible to test, debug, or modify safely

**Fix:** Extract into separate functions:

```python
def _decode_tile_v10(data, offset_table, idx, tile_size, gh, gw, channels, quality, ...):
    """Decode a single tile in mode 10 (tiled)."""
    # Extract the tile-decoding logic
    
def _decode_full_image_v9(data, offset, channels, bc, gh, gw, quality, ...):
    """Decode full image in mode 9 (simple)."""
    # Extract the mode 9 logic
    
def decode_lossy(data, w, h, channels, ...):
    """Main decoder dispatcher."""
    mode = data[0] & 0x0F
    if mode == 10:
        return _decode_tiled_v10(...)
    elif mode == 9:
        return _decode_full_image_v9(...)
    else:
        raise ValueError(f"unknown WIMF codec mode {mode}")
```

---

### 3. **Magic Numbers Everywhere**

**Problem:** Hardcoded constants scattered throughout

**Examples:**
- `17 + mlen` (header offset) - appears in 6+ files
- `quality << 4 | 9` and `quality << 4 | 10` - encoding/decoding mode
- `16` (tile size), `4, 8, 64` (subtile sizes)
- `30` (keyframe interval in animation)
- `(16 - h % 16) % 16` (padding calculation)
- `0x0F` (mode mask)

**Fix - Create constants module:**

```python
# wimf/constants.py
WIMF_MAGIC = b"WIMF"
AWIF_MAGIC = b"AWIF"

# File format
HEADER_SIZE = 17
METADATA_OFFSET = 17

# Codec modes
CODEC_MODE_RAW = 0
CODEC_MODE_LOSSLESS = 1
CODEC_MODE_LOSSY = 2
CODEC_MODE_TILED = 10
CODEC_MODE_SIMPLE = 9

MODE_MASK = 0x0F
QUALITY_SHIFT = 4

# Tile/block sizes
TILE_SIZE_BASE = 16
MIN_TILE_SIZE = 16
DEFAULT_TILE_SIZE = 32

# Animation
KEYFRAME_INTERVAL = 30

# Quantization
MIN_QUALITY_STEP = 1.0
```

Then update code:
```python
from .constants import *

# OLD:
if f_type == 0:  # literally just raw pixels
    arr[y] = row_res
elif f_type == 1:  # left pixel math

# NEW:
FILTER_RAW = 0
FILTER_LEFT = 1
FILTER_TOP = 2
FILTER_PAETH = 3

if f_type == FILTER_RAW:
    arr[y] = row_res
elif f_type == FILTER_LEFT:
```

---

### 4. **No Error Handling in C++** (`src/main.cpp`)

**Problems:**
- `c_save_file` and `c_load_file` throw but don't validate I/O
- Raw pointer casting without bounds checking
- No validation of `std::memcpy` offsets
- SIMD code has no fallback if alignment fails

**Example (Line 220-226):**
```cpp
void c_save_file(std::string path, py::bytes data) {
    std::string str = data;
    std::ofstream f(path, std::ios::out | std::ios::binary);
    if (!f) throw std::runtime_error("Could not open file for writing.");
    f.write(str.data(), str.size());
    f.close();  // Never checks if close() succeeded
}
```

**Fix:**
```cpp
void c_save_file(std::string path, py::bytes data) {
    std::string str = data;
    std::ofstream f(path, std::ios::out | std::ios::binary);
    if (!f.is_open()) {
        throw std::runtime_error("Failed to open file for writing: " + path);
    }
    f.write(str.data(), str.size());
    if (!f) {
        throw std::runtime_error("Failed to write data to file: " + path);
    }
    f.close();
    if (f.fail()) {
        throw std::runtime_error("Failed to close file: " + path);
    }
}

// Add bounds checking for memcpy
void safe_memcpy_from_offset(void* dest, const uint8_t* src, size_t src_size, 
                             size_t offset, size_t count) {
    if (offset + count > src_size) {
        throw std::runtime_error("Buffer read out of bounds");
    }
    std::memcpy(dest, src + offset, count);
}
```

---

### 5. **CLI Dead Code & Inconsistent Error Handling** (`wimf/cli.py`)

**Dead Code (Line 265-267):**
```python
if args.extract_secret:
    _, _, _, loaded_meta = loadImage(args.input[0])
    return  # Loads but never prints anything!
```

**Problems:**
- No input validation (quality range not checked until deep in call stack)
- Inconsistent error handling
- Magic numbers for quality (1-10) hardcoded in argparse
- 30-line nested conditional starting line 278

**Fix:**

```python
def validate_arguments(args):
    """Validate CLI arguments early."""
    if not args.input:
        raise ValueError("At least one input file is required")
    
    if not 1 <= args.quality <= 10:
        raise ValueError(f"Quality must be 1-10, got {args.quality}")
    
    if args.preset not in ["Fast", "Balanced", "Extreme"]:
        raise ValueError(f"Invalid preset: {args.preset}")
    
    if args.roi and len(args.roi) != 4:
        raise ValueError("--roi requires 4 integer arguments (x y w h)")
    
    if args.mip not in [0, 1, 2]:
        raise ValueError(f"--mip must be 0, 1, or 2, got {args.mip}")
    
    return args

def main():
    parser = argparse.ArgumentParser(...)
    # ... build parser ...
    args = parser.parse_args()
    
    try:
        args = validate_arguments(args)
    except ValueError as e:
        parser.error(str(e))
    
    # Process input files
    input_files = _glob_input_files(args.input)
    
    # Dispatch to appropriate handler
    if args.benchmark:
        _handle_benchmark(args, input_files)
    elif args.extract_secret:
        _handle_extract_secret(args, input_files)
    elif args.chrono:
        _handle_chrono(args, input_files)
    else:
        _handle_convert(args, input_files)
```

---

### 6. **Python Import Order Already Fixed** ✅

**Status:** We already fixed `wimf/codec.py` E402 violations.

---

### 7. **Deep Nesting in cli.py**

**Lines 278-331 - Benchmark setup:**
```python
if args.benchmark:
    if len(input_files) > 1:
        ...
    in_file = input_files[0]
    bench_out = args.output
    if os.path.isdir(bench_out):
        ...
    elif not os.path.splitext(bench_out)[1]:
        if not os.path.exists(bench_out):
            ...
        # Nested 3 levels deep
```

**Fix:** Extract to function:
```python
def _prepare_benchmark_output(output_path, default_name="bench_result.wimf"):
    """Normalize benchmark output path."""
    if os.path.isdir(output_path):
        return os.path.join(output_path, default_name)
    
    dir_path = output_path
    if os.path.splitext(output_path)[1]:
        dir_path = os.path.dirname(output_path) or "."
    
    if not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)
    
    return output_path if os.path.splitext(output_path)[1] else \
           os.path.join(dir_path, default_name)
```

---

## Summary of Recommended Fixes

| Priority | Issue | File | Lines | Effort |
|----------|-------|------|-------|--------|
| 🔴 CRITICAL | C++ formatting | `src/main.cpp` | 1-300 | High |
| 🔴 CRITICAL | decode_lossy() too large | `wimf/codec.py` | 369-642 | High |
| 🟠 HIGH | Magic numbers scattered | All files | Numerous | Medium |
| 🟠 HIGH | No C++ error handling | `src/main.cpp` | 220-236 | Medium |
| 🟠 HIGH | CLI dead code | `wimf/cli.py` | 265-267 | Low |
| 🟡 MEDIUM | Deep nesting | `wimf/cli.py` | 278-331 | Low |

---

## Next Steps

1. **Run formatter:** `clang-format` on C++ code
2. **Add unit tests** before refactoring large functions
3. **Create constants.py** to eliminate magic numbers
4. **Add type hints** throughout (Python 3.8+)
5. **Add docstrings** to all public functions
6. **Use linting:** `pylint`, `flake8` with strict config
