#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <iostream>
#include <vector>
#include <algorithm>
#include <cmath>

namespace py = pybind11;

// --- SIMD ABSTRACTION LAYER ---
#if defined(__x86_64__) || defined(_M_X64)
    #include <immintrin.h>
    #define WIMF_X86
#elif defined(__aarch64__) || defined(_M_ARM64)
    #include <arm_neon.h>
    #define WIMF_ARM
#endif

// --- YCoCg-R TRANSFORM ---
void ycocg_forward(py::array_t<int32_t> arr) {
    if (arr.ndim() != 3) throw std::runtime_error("ycocg_forward expects a 3D array [H, W, 3]");
    auto buf = arr.mutable_unchecked<3>();
    
    ssize_t h = buf.shape(0);
    ssize_t w = buf.shape(1);

    for (ssize_t y = 0; y < h; ++y) {
        int32_t* row_ptr = &buf(y, 0, 0);
        for (ssize_t x = 0; x < w; ++x) {
            int32_t r = row_ptr[x * 3 + 0];
            int32_t g = row_ptr[x * 3 + 1];
            int32_t b = row_ptr[x * 3 + 2];

            int32_t co = r - b;
            int32_t tmp = b + (co >> 1);
            int32_t cg = g - tmp;
            int32_t luma = tmp + (cg >> 1);

            row_ptr[x * 3 + 0] = luma;
            row_ptr[x * 3 + 1] = co;
            row_ptr[x * 3 + 2] = cg;
        }
    }
}

void ycocg_inverse(const py::buffer& b) {
    py::buffer_info info = b.request();
    if (info.format != py::format_descriptor<float>::format())
        throw std::runtime_error("Incompatible format: expected float");

    if (info.shape.empty() || info.shape.back() != 3)
        throw std::runtime_error("Last dimension must be 3 (RGB)");

    auto* data = static_cast<float*>(info.ptr);
    ssize_t total_pixels = info.size / 3;

    for (ssize_t i = 0; i < total_pixels; ++i) {
        float luma = data[i * 3 + 0];
        float co   = data[i * 3 + 1];
        float cg   = data[i * 3 + 2];

        float tmp = luma - std::floor(cg * 0.5f);
        float g = cg + tmp;
        float b = tmp - std::floor(co * 0.5f);
        float r = b + co;

        data[i * 3 + 0] = r;
        data[i * 3 + 1] = g;
        data[i * 3 + 2] = b;
    }
}

// --- HAAR WAVELET TRANSFORM ---
py::tuple haar_level(const py::array_t<float>& b) {
    auto buf = b.unchecked<4>();
    ssize_t n = buf.shape(0);
    ssize_t c = buf.shape(1);
    ssize_t h = buf.shape(2);
    ssize_t w = buf.shape(3);

    ssize_t out_h = h / 2;
    ssize_t out_w = w / 2;

    auto LL = py::array_t<float>({n, c, out_h, out_w});
    auto HL = py::array_t<float>({n, c, out_h, out_w});
    auto LH = py::array_t<float>({n, c, out_h, out_w});
    auto HH = py::array_t<float>({n, c, out_h, out_w});

    auto mLL = LL.mutable_unchecked<4>();
    auto mHL = HL.mutable_unchecked<4>();
    auto mLH = LH.mutable_unchecked<4>();
    auto mHH = HH.mutable_unchecked<4>();

    for (ssize_t i = 0; i < n; ++i) {
        for (ssize_t j = 0; j < c; ++j) {
            for (ssize_t y = 0; y < out_h; ++y) {
                const float* r0 = &buf(i, j, 2*y, 0);
                const float* r1 = &buf(i, j, 2*y + 1, 0);
                float* wLL = &mLL(i, j, y, 0);
                float* wHL = &mHL(i, j, y, 0);
                float* wLH = &mLH(i, j, y, 0);
                float* wHH = &mHH(i, j, y, 0);

                ssize_t x = 0;
                #ifdef WIMF_X86
                for (; x <= out_w - 4; x += 4) {
                    __m256 v0 = _mm256_loadu_ps(&r0[x * 2]);
                    __m256 v1 = _mm256_loadu_ps(&r1[x * 2]);

                    __m256 v0_e = _mm256_castpd_ps(_mm256_permute4x64_pd(_mm256_castps_pd(_mm256_shuffle_ps(v0, v0, 0x88)), 0xD8));
                    __m256 v0_o = _mm256_castpd_ps(_mm256_permute4x64_pd(_mm256_castps_pd(_mm256_shuffle_ps(v0, v0, 0xDD)), 0xD8));
                    __m256 v1_e = _mm256_castpd_ps(_mm256_permute4x64_pd(_mm256_castps_pd(_mm256_shuffle_ps(v1, v1, 0x88)), 0xD8));
                    __m256 v1_o = _mm256_castpd_ps(_mm256_permute4x64_pd(_mm256_castps_pd(_mm256_shuffle_ps(v1, v1, 0xDD)), 0xD8));

                    __m256 resLL = _mm256_mul_ps(_mm256_add_ps(_mm256_add_ps(v0_e, v0_o), _mm256_add_ps(v1_e, v1_o)), _mm256_set1_ps(0.25f));
                    __m256 resHL = _mm256_mul_ps(_mm256_add_ps(_mm256_sub_ps(v0_e, v0_o), _mm256_sub_ps(v1_e, v1_o)), _mm256_set1_ps(0.25f));
                    __m256 resLH = _mm256_mul_ps(_mm256_sub_ps(_mm256_add_ps(v0_e, v0_o), _mm256_add_ps(v1_e, v1_o)), _mm256_set1_ps(0.25f));
                    __m256 resHH = _mm256_mul_ps(_mm256_sub_ps(_mm256_sub_ps(v0_e, v0_o), _mm256_sub_ps(v1_e, v1_o)), _mm256_set1_ps(0.25f));

                    _mm_storeu_ps(&wLL[x], _mm256_castps256_ps128(resLL));
                    _mm_storeu_ps(&wHL[x], _mm256_castps256_ps128(resHL));
                    _mm_storeu_ps(&wLH[x], _mm256_castps256_ps128(resLH));
                    _mm_storeu_ps(&wHH[x], _mm256_castps256_ps128(resHH));
                }
                #endif

                for (; x < out_w; ++x) {
                    float a = r0[2*x];
                    float b_val = r0[2*x + 1];
                    float c_val = r1[2*x];
                    float d = r1[2*x + 1];

                    wLL[x] = (a + b_val + c_val + d) * 0.25f;
                    wHL[x] = (a - b_val + c_val - d) * 0.25f;
                    wLH[x] = (a + b_val - c_val - d) * 0.25f;
                    wHH[x] = (a - b_val - c_val + d) * 0.25f;
                }
            }
        }
    }

    return py::make_tuple(LL, HL, LH, HH);
}

py::array_t<float> ihaar_level(const py::array_t<float>& LL, const py::array_t<float>& HL, const py::array_t<float>& LH, const py::array_t<float>& HH) {
    auto mLL = LL.unchecked<4>();
    auto mHL = HL.unchecked<4>();
    auto mLH = LH.unchecked<4>();
    auto mHH = HH.unchecked<4>();

    ssize_t n = mLL.shape(0);
    ssize_t c = mLL.shape(1);
    ssize_t h = mLL.shape(2);
    ssize_t w = mLL.shape(3);

    auto out = py::array_t<float>({n, c, h * 2, w * 2});
    auto mOut = out.mutable_unchecked<4>();

    for (ssize_t i = 0; i < n; ++i) {
        for (ssize_t j = 0; j < c; ++j) {
            for (ssize_t y = 0; y < h; ++y) {
                const float* rLL = &mLL(i, j, y, 0);
                const float* rHL = &mHL(i, j, y, 0);
                const float* rLH = &mLH(i, j, y, 0);
                const float* rHH = &mHH(i, j, y, 0);
                float* w0 = &mOut(i, j, 2*y, 0);
                float* w1 = &mOut(i, j, 2*y + 1, 0);

                ssize_t x = 0;
                #ifdef WIMF_X86
                for (; x <= w - 4; x += 4) {
                    __m128 vLL = _mm_loadu_ps(&rLL[x]);
                    __m128 vHL = _mm_loadu_ps(&rHL[x]);
                    __m128 vLH = _mm_loadu_ps(&rLH[x]);
                    __m128 vHH = _mm_loadu_ps(&rHH[x]);

                    __m128 a = _mm_add_ps(_mm_add_ps(vLL, vHL), _mm_add_ps(vLH, vHH));
                    __m128 b = _mm_add_ps(_mm_sub_ps(vLL, vHL), _mm_sub_ps(vLH, vHH));
                    __m128 c_val = _mm_sub_ps(_mm_add_ps(vLL, vHL), _mm_add_ps(vLH, vHH));
                    __m128 d = _mm_sub_ps(_mm_sub_ps(vLL, vHL), _mm_sub_ps(vLH, vHH));

                    __m128 r0_low = _mm_unpacklo_ps(a, b);
                    __m128 r0_high = _mm_unpackhi_ps(a, b);
                    _mm_storeu_ps(&w0[x * 2], r0_low);
                    _mm_storeu_ps(&w0[x * 2 + 4], r0_high);

                    __m128 r1_low = _mm_unpacklo_ps(c_val, d);
                    __m128 r1_high = _mm_unpackhi_ps(c_val, d);
                    _mm_storeu_ps(&w1[x * 2], r1_low);
                    _mm_storeu_ps(&w1[x * 2 + 4], r1_high);
                }
                #endif

                for (; x < w; ++x) {
                    float ll = rLL[x];
                    float hl = rHL[x];
                    float lh = rLH[x];
                    float hh = rHH[x];

                    w0[2*x] = ll + hl + lh + hh;
                    w0[2*x + 1] = ll - hl + lh - hh;
                    w1[2*x] = ll + hl - lh - hh;
                    w1[2*x + 1] = ll - hl - lh + hh;
                }
            }
        }
    }

    return out;
}

// --- PAETH PREDICTOR ---
inline int32_t paeth_scalar(int32_t a, int32_t b, int32_t c) {
    int32_t p = a + b - c;
    int32_t pa = std::abs(p - a);
    int32_t pb = std::abs(p - b);
    int32_t pc = std::abs(p - c);
    if (pa <= pb && pa <= pc) return a;
    if (pb <= pc) return b;
    return c;
}

void paeth_filter(const py::array_t<int16_t>& arr, const py::array_t<int16_t>& left, const py::array_t<int16_t>& above, const py::array_t<int16_t>& above_left, py::array_t<int16_t>& out) {
    auto rArr = arr.unchecked<2>();
    auto rL = left.unchecked<2>();
    auto rA = above.unchecked<2>();
    auto rAL = above_left.unchecked<2>();
    auto mOut = out.mutable_unchecked<2>();

    ssize_t h = rArr.shape(0);
    ssize_t w = rArr.shape(1);

    for (ssize_t y = 0; y < h; ++y) {
        for (ssize_t x = 0; x < w; ++x) {
            mOut(y, x) = static_cast<int16_t>(rArr(y, x) - paeth_scalar(rL(y, x), rA(y, x), rAL(y, x)));
        }
    }
}

// Python binding module
PYBIND11_MODULE(wimf_cpp, m) {
    m.doc() = "WIMF Optimized C++ Extension";
    m.def("ycocg_forward", &ycocg_forward, "Forward YCoCg-R transform");
    m.def("ycocg_inverse", &ycocg_inverse, "Inverse YCoCg-R transform");
    m.def("haar_level", &haar_level, "Forward Haar wavelet level");
    m.def("ihaar_level", &ihaar_level, "Inverse Haar wavelet level");
    m.def("paeth_filter", &paeth_filter, "Batch Paeth filter processing");
}
