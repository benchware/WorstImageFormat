# 🔥 CRITICAL BUGS & CATASTROPHIC CODE PATTERNS

## ⚠️ BUFFER OVERFLOW / MEMORY SAFETY DISASTERS

### BUG #1: UNBOUNDED MEMCPY IN C++ (CRITICAL)
**File:** `src/main.cpp:265`
**Severity:** 🔴 CRITICAL - **BUFFER OVERFLOW VULNERABILITY**

```cpp
m.def("parse_header", [](py::array_t<uint8_t> d){ 
    const uint8_t* p=d.data(0); 
    uint32_t w,h,m_len; 
    std::memcpy(&w,p+4,4);         // ❌ NO BOUNDS CHECK!
    std::memcpy(&h,p+8,4);         // ❌ NO BOUNDS CHECK!
    std::memcpy(&m_len,p+13,4);    // ❌ NO BOUNDS CHECK!
    return py::make_tuple(w,h,p[12],m_len); 
});
```

**Problem:** If input is < 17 bytes, **OUT OF BOUNDS READ → CRASH or RCE**

**Exploit:**
```python
from wimf import wimf_cpp
# Crash the parser with tiny input
wimf_cpp.parse_header(np.array([1,2,3,4], dtype=np.uint8))  # SEGFAULT
```

**Fix:**
```cpp
m.def("parse_header", [](py::array_t<uint8_t> d) {
    if (d.size() < 17) {
        throw std::runtime_error("Input too small for header (need 17 bytes)");
    }
    const uint8_t* p = d.data(0);
    uint32_t w, h, m_len;
    std::memcpy(&w, p + 4, 4);
    std::memcpy(&h, p + 8, 4);
    std::memcpy(&m_len, p + 13, 4);
    return py::make_tuple(w, h, p[12], m_len);
});
```

---

### BUG #2: TILE_COPY 4-LEVEL NESTED LOOP WITH NO BOUNDS CHECKING
**File:** `src/main.cpp:281-289`
**Severity:** 🔴 CRITICAL - **BUFFER UNDERFLOW/OVERFLOW**

```cpp
m.def("tile_copy", [](py::array_t<float> source, py::array_t<float> target, 
                       int ty, int tx, int tile_size, int gh, int gw){
    auto src = source.unchecked<4>();
    auto dst = target.mutable_unchecked<4>();
    for (int y = 0; y < tile_size && ty + y < gh; ++y)
        for (int x = 0; x < tile_size && tx + x < gw; ++x)
            for (int sy = 0; sy < 16; ++sy)
                for (int sx = 0; sx < 16; ++sx)
                    // ❌ WHAT IF sy or sx is out of bounds?
                    dst(y, sy, x, sx) = src(ty + y, sy, tx + x, sx);
});
```

**Problems:**
- No check that `sy < shape[1]` or `sx < shape[3]`
- Accesses `dst(y, sy, x, sx)` where `sy/sx` can be 0-15 unconditionally
- If target is smaller, **OUT OF BOUNDS WRITE**

**Exploit:**
```python
# Create tiny target array
target = np.zeros((2, 4, 2, 4), dtype=np.float32)  # Only 4x4 blocks
source = np.ones((10, 16, 10, 16), dtype=np.float32)
wimf_cpp.tile_copy(source, target, 0, 0, 5, 10, 10)  # BUFFER OVERFLOW
```

**Fix:**
```cpp
m.def("tile_copy", [](py::array_t<float> source, py::array_t<float> target, 
                       int ty, int tx, int tile_size, int gh, int gw) {
    auto src = source.unchecked<4>();
    auto dst = target.mutable_unchecked<4>();
    
    // Bounds check
    if (src.shape(0) < 1 || src.shape(2) < 1) 
        throw std::runtime_error("Invalid source shape");
    if (dst.shape(0) < 1 || dst.shape(2) < 1)
        throw std::runtime_error("Invalid target shape");
    
    for (int y = 0; y < tile_size && ty + y < gh && y < (int)dst.shape(0); ++y) {
        for (int x = 0; x < tile_size && tx + x < gw && x < (int)dst.shape(2); ++x) {
            for (int sy = 0; sy < 16 && sy < (int)dst.shape(1); ++sy) {
                for (int sx = 0; sx < 16 && sx < (int)dst.shape(3); ++sx) {
                    if (ty + y < (int)src.shape(0) && tx + x < (int)src.shape(2))
                        dst(y, sy, x, sx) = src(ty + y, sy, tx + x, sx);
                }
            }
        }
    }
});
```

---

### BUG #3: PAETH FILTER - SHAPE MISMATCH NOT VALIDATED
**File:** `src/main.cpp:270-280`
**Severity:** 🔴 CRITICAL

```cpp
m.def("paeth_filter", [](const py::array_t<int16_t>& arr, 
                          const py::array_t<int16_t>& left, 
                          const py::array_t<int16_t>& above, 
                          const py::array_t<int16_t>& above_left, 
                          py::array_t<int16_t>& out){
    // ❌ NO CHECK: Do all arrays have matching shapes?
    auto rArr = arr.unchecked<2>(), rL = left.unchecked<2>(), 
         rA = above.unchecked<2>(), rAL = above_left.unchecked<2>();
    auto mOut = out.mutable_unchecked<2>();
    
    for (ssize_t y = 0; y < rArr.shape(0); ++y)
        for (ssize_t x = 0; x < rArr.shape(1); ++x) {
            // What if left/above are smaller?
            int32_t a = rL(y,x), b = rA(y,x), c = rAL(y,x);
            // ...
        }
});
```

**Problem:** Accesses `rL(y,x)` where `x` could exceed `rL.shape(1)`

**Fix:**
```cpp
m.def("paeth_filter", [](const py::array_t<int16_t>& arr, 
                          const py::array_t<int16_t>& left, 
                          const py::array_t<int16_t>& above, 
                          const py::array_t<int16_t>& above_left, 
                          py::array_t<int16_t>& out) {
    auto rArr = arr.unchecked<2>(), rL = left.unchecked<2>(), 
         rA = above.unchecked<2>(), rAL = above_left.unchecked<2>();
    auto mOut = out.mutable_unchecked<2>();
    
    // Validate shapes match
    if (rArr.shape(0) != rL.shape(0) || rArr.shape(1) != rL.shape(1) ||
        rArr.shape(0) != rA.shape(0) || rArr.shape(1) != rA.shape(1) ||
        rArr.shape(0) != rAL.shape(0) || rArr.shape(1) != rAL.shape(1) ||
        rArr.shape(0) != mOut.shape(0) || rArr.shape(1) != mOut.shape(1)) {
        throw std::runtime_error("All input arrays must have matching shapes");
    }
    
    for (ssize_t y = 0; y < rArr.shape(0); ++y) {
        for (ssize_t x = 0; x < rArr.shape(1); ++x) {
            int32_t a = rL(y, x), b = rA(y, x), c = rAL(y, x);
            int32_t p = a + b - c, pa = std::abs(p - a), 
                     pb = std::abs(p - b), pc = std::abs(p - c);
            int32_t pr = (pa <= pb && pa <= pc) ? a : (pb <= pc ? b : c);
            mOut(y, x) = static_cast<int16_t>(rArr(y, x) - pr);
        }
    }
});
```

---

## 🔴 LOGIC BUGS THAT CORRUPT DATA

### BUG #4: ANIMATION FRAME DELTA WITHOUT KEYFRAME INITIALIZATION
**File:** `wimf/animation.py:140-145`
**Severity:** 🔴 CRITICAL - **SILENT DATA CORRUPTION**

```python
else:  # Delta frame
    if q_step is None:
        logger.warning("delta frame encountered before any keyframe — skipping")
        frames.append(
            prev_arr.astype(dtype).tobytes() if prev_arr is not None else b"\x00" * (w * h * channels)
        )
        continue
```

**Problem:** If file is corrupted and starts with delta frames, `prev_arr is None` → **APPENDS BLANK FRAME SILENTLY**

The decoder silently replaces corrupted delta frames with **BLACK FRAMES** without erroring out!

**Exploit:**
```python
# Craft animation file that starts with delta frame
# Decoder will output blank frame instead of erroring
```

**Fix:**
```python
else:  # Delta frame
    if q_step is None:
        raise ValueError(
            f"Frame {i}: delta frame encountered before any keyframe. "
            "File is corrupted or invalid."
        )
```

---

### BUG #5: HARDCODED BUFFER SIZE IN DECODE_ANIMATED
**File:** `wimf/animation.py:120-121`
**Severity:** 🟠 HIGH - **SIZE CALCULATION ERROR**

```python
ph, pw = h % 2, w % 2
th, tw = (h + ph) // 2, (w + pw) // 2
sz_coeff = th * tw * channels * 2  # ❌ What if data is smaller?
```

Then line 152:
```python
LL = np.frombuffer(d_raw[o : o + sz_coeff], dtype=np.int16)...
```

**Problem:** If `d_raw` is corrupted and smaller than `4 * sz_coeff`, `frombuffer()` returns **partial array** with no error!

```python
# Example:
d_raw = b"x" * 10  # Tiny corrupted data
o = 0
sz_coeff = 1000
# This doesn't error, just returns array of size 5!
LL = np.frombuffer(d_raw[o : o + sz_coeff], dtype=np.int16)  
```

Then reshape silently fails or creates garbage dimensions.

**Fix:**
```python
for band_idx, band_label in enumerate(['LL', 'HL', 'LH', 'HH']):
    if o + sz_coeff > len(d_raw):
        raise ValueError(
            f"Corrupted delta data: {band_label} band at offset {o} "
            f"needs {sz_coeff} bytes but only {len(d_raw) - o} available"
        )
    band = np.frombuffer(d_raw[o : o + sz_coeff], dtype=np.int16)
    if band.size != sz_coeff // 2:
        raise ValueError(f"{band_label} band incomplete (got {band.size}, need {sz_coeff // 2})")
    # ... process band
    o += sz_coeff
```

---

### BUG #6: INTEGER DIVISION EDGE CASE IN CLIPPING
**File:** `wimf/animation.py:56`
**Severity:** 🟠 HIGH

```python
pad_h, pad_w = cur_h % 2, cur_w % 2
if pad_h > 0 or pad_w > 0:
    d_padded = np.pad(delta, ((0, pad_h), (0, pad_w), (0, 0)), mode="constant")
else:
    d_padded = delta

th, tw = (cur_h + pad_h) // 2, (cur_w + pad_w) // 2
```

**Problem:** If `cur_h=3, pad_h=1`, then `th = 4//2 = 2`. But Haar wavelet needs **even dimensions**, not just after padding.

What if original is odd and we don't pad properly?

```python
# cur_h=3 (odd), pad_h = 3%2 = 1
d_padded.shape = (4, ...) ✓ now even
th = (3+1)//2 = 2 ✓ correct

# BUT: haar_level expects shape divisible by 2, which (4, w) is
# So this works, but it's fragile. What if pad calculation is wrong?
```

**Better:**
```python
def ensure_haar_compatible(delta):
    """Ensure dimensions are compatible with Haar wavelets."""
    h, w, c = delta.shape
    new_h = ((h + 1) // 2) * 2  # Round up to nearest even
    new_w = ((w + 1) // 2) * 2  # Round up to nearest even
    if new_h > h or new_w > w:
        return np.pad(delta, ((0, new_h-h), (0, new_w-w), (0, 0)))
    return delta
```

---

### BUG #7: SILENT TRUNCATION IN DEEPMAP READING
**File:** `wimf/api.py:30-43`
**Severity:** 🟠 HIGH - **SILENT DATA LOSS**

```python
elif channels == 5 and metadata.get("depth"):
    arr = np.frombuffer(pix, dtype=np.uint8).reshape((h, w, 5))
    pil_pix = arr[..., :4].tobytes()
    mode = "RGBA"
else:
    # high channel count fallback: use first 3 channels for a dummy pil image
    try:
        arr = np.frombuffer(pix, dtype=np.uint8).reshape((h, w, channels))
        pil_pix = arr[..., :3].tobytes()  # ❌ SILENTLY DISCARDS CHANNELS 3+
        mode = "RGB"
    except Exception:
        # absolute fallback
        pil_pix = b"\x00" * (w * h * 3)  # ❌ RETURNS BLACK IMAGE
        mode = "RGB"
```

**Problem:** If you have 7-channel image, this **silently converts to RGB**, losing 4 channels with no warning!

```python
# Example: 10-channel hyperspectral image
decoder = WIMFDecoder("hyperspectral.wimf")
img = decoder.decode()  # ❌ Returns RGB only, no warning, data lost
```

**Fix:**
```python
def _pixels_to_pil(pix, w, h, channels, metadata, bit_depth):
    """Convert raw pixel bytes to a PIL Image."""
    if bit_depth == 10:
        arr = np.frombuffer(pix, dtype=np.uint16).reshape((h, w, channels))
        pix = (arr >> 2).astype(np.uint8).tobytes()
    
    if channels == 3:
        return Image.frombytes("RGB", (w, h), pix)
    elif channels == 4:
        return Image.frombytes("RGBA", (w, h), pix)
    elif channels == 5 and metadata.get("depth"):
        arr = np.frombuffer(pix, dtype=np.uint8).reshape((h, w, 5))
        return Image.frombytes("RGBA", (w, h), arr[..., :4].tobytes())
    else:
        logger.warning(
            f"Cannot display {channels}-channel image in PIL. "
            f"Use .to_numpy() to access raw data."
        )
        raise ValueError(
            f"Unsupported channel count: {channels}. "
            f"PIL only supports 3 (RGB) or 4 (RGBA) channels. "
            f"Use `.to_numpy()` to access full data."
        )
```

---

### BUG #8: YCOCG INVERSE SIZE CALCULATION ERROR
**File:** `src/main.cpp:240`
**Severity:** 🟠 MEDIUM - **POTENTIAL STRIDE ERROR**

```cpp
m.def("ycocg_inverse", [](const py::buffer& b){ 
    py::buffer_info i = b.request(); 
    ycocg_inverse_raw((float*)i.ptr, i.size/3);  // ❌ i.size is in BYTES, not elements!
});
```

**Problem:** `i.size` is **byte count**, but code assumes elements:

```python
# If input is 12 floats (48 bytes)
# i.size/3 = 48/3 = 16
# But should be 48/(4*3) = 4 groups of 3 floats!
```

**Fix:**
```cpp
m.def("ycocg_inverse", [](const py::buffer& b) {
    py::buffer_info i = b.request();
    if (i.itemsize != 4) {  // float = 4 bytes
        throw std::runtime_error("Expected float32 array");
    }
    size_t nelems = i.size / i.itemsize;
    if (nelems % 3 != 0) {
        throw std::runtime_error("Buffer size must be multiple of 3 floats");
    }
    ycocg_inverse_raw((float*)i.ptr, nelems / 3);
});
```

---

### BUG #9: IHAAR_LEVEL SHAPE MISMATCH NOT VALIDATED
**File:** `src/main.cpp:249-257`
**Severity:** 🔴 CRITICAL - **SILENT SHAPE MISMATCH**

```cpp
m.def("ihaar_level", [](const py::array_t<float>& LL, const py::array_t<float>& HL, 
                         const py::array_t<float>& LH, const py::array_t<float>& HH){
    auto bufLL = LL.unchecked<4>(), bufHL = HL.unchecked<4>(), ...
    ssize_t n = bufLL.shape(0), c = bufLL.shape(1), h = bufLL.shape(2), w = bufLL.shape(3);
    // ❌ Never checks if HL, LH, HH have same shapes!
```

**Exploit:**
```python
LL = np.zeros((2, 3, 4, 4), dtype=np.float32)
HL = np.zeros((2, 3, 8, 4), dtype=np.float32)  # Wrong h!
LH = np.zeros((2, 3, 4, 4), dtype=np.float32)
HH = np.zeros((2, 3, 4, 4), dtype=np.float32)
wimf_cpp.ihaar_level(LL, HL, LH, HH)  # BUFFER OVERFLOW
```

**Fix:**
```cpp
m.def("ihaar_level", [](const py::array_t<float>& LL, const py::array_t<float>& HL, 
                         const py::array_t<float>& LH, const py::array_t<float>& HH) {
    auto bufLL = LL.unchecked<4>(), bufHL = HL.unchecked<4>(), 
         bufLH = LH.unchecked<4>(), bufHH = HH.unchecked<4>();
    
    // Validate all shapes match
    if (bufHL.shape(0) != bufLL.shape(0) || bufHL.shape(1) != bufLL.shape(1) ||
        bufHL.shape(2) != bufLL.shape(2) || bufHL.shape(3) != bufLL.shape(3)) {
        throw std::runtime_error("HL shape must match LL");
    }
    if (bufLH.shape(0) != bufLL.shape(0) || bufLH.shape(1) != bufLL.shape(1) ||
        bufLH.shape(2) != bufLL.shape(2) || bufLH.shape(3) != bufLL.shape(3)) {
        throw std::runtime_error("LH shape must match LL");
    }
    if (bufHH.shape(0) != bufLL.shape(0) || bufHH.shape(1) != bufLL.shape(1) ||
        bufHH.shape(2) != bufLL.shape(2) || bufHH.shape(3) != bufLL.shape(3)) {
        throw std::runtime_error("HH shape must match LL");
    }
    
    // ... rest of function
});
```

---

## SUMMARY: SCORES OF BUGS

| Bug | File | Line | Severity | Type |
|-----|------|------|----------|------|
| #1 | src/main.cpp | 265 | 🔴 CRITICAL | Buffer overflow |
| #2 | src/main.cpp | 281 | 🔴 CRITICAL | Buffer overflow |
| #3 | src/main.cpp | 270 | 🔴 CRITICAL | Shape mismatch |
| #4 | wimf/animation.py | 140 | 🔴 CRITICAL | Data corruption |
| #5 | wimf/animation.py | 120 | 🟠 HIGH | Size calc error |
| #6 | wimf/animation.py | 56 | 🟠 HIGH | Padding edge case |
| #7 | wimf/api.py | 30 | 🟠 HIGH | Silent data loss |
| #8 | src/main.cpp | 240 | 🟠 MEDIUM | Stride error |
| #9 | src/main.cpp | 249 | 🔴 CRITICAL | Shape mismatch |

### Next Steps:
1. **IMMEDIATE:** Add input validation to all C++ array access
2. **URGENT:** Fix animation decoder error handling
3. **HIGH:** Add type/shape validation in pybind11 wrappers
4. **MEDIUM:** Improve PIL fallback behavior
