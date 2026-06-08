#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
#include <iostream>
#include <vector>
#include <algorithm>
#include <cmath>
#include <cstring>

namespace py = pybind11;

// --- SIMD LAYER ---
#if defined(__x86_64__) || defined(_M_X64)
    #include <immintrin.h>
    #define WIMF_X86
#elif defined(__aarch64__) || defined(_M_ARM64) || defined(__ARM_NEON)
    #include <arm_neon.h>
    #define WIMF_ARM
#endif

// --- CORE MATH RAW ---
extern "C" {
    void ycocg_forward_raw(int32_t* d, size_t w, size_t h) {
        for (size_t i = 0; i < w * h; ++i) {
            int32_t r = d[i*3], g = d[i*3+1], b = d[i*3+2];
            int32_t co = r-b, t = b+(co>>1), cg = g-t, y = t+(cg>>1);
            d[i*3] = y; d[i*3+1] = co; d[i*3+2] = cg;
        }
    }
    void ycocg_inverse_raw(float* d, size_t n) {
        for (size_t i = 0; i < n; ++i) {
            float y = d[i*3], co = d[i*3+1], cg = d[i*3+2];
            float t = y-std::floor(cg*0.5f), g = cg+t, b = t-std::floor(co*0.5f), r = b+co;
            d[i*3] = r; d[i*3+1] = g; d[i*3+2] = b;
        }
    }
    void haar_2d_raw(const float* b, float* ll, float* hl, float* lh, float* hh, int h, int w) {
        int oh = h/2, ow = w/2;
        for (int y = 0; y < oh; ++y) {
            const float* r0 = &b[(2*y)*w], *r1 = &b[(2*y+1)*w];
            float* wll = &ll[y*ow], *whl = &hl[y*ow], *wlh = &lh[y*ow], *whh = &hh[y*ow];
            int x = 0;
            #ifdef WIMF_X86
            for (; x <= ow-4; x += 4) {
                __m256 v0 = _mm256_loadu_ps(&r0[x*2]), v1 = _mm256_loadu_ps(&r1[x*2]);
                __m256 v0_e = _mm256_castpd_ps(_mm256_permute4x64_pd(_mm256_castps_pd(_mm256_shuffle_ps(v0,v0,0x88)),0xD8));
                __m256 v0_o = _mm256_castpd_ps(_mm256_permute4x64_pd(_mm256_castps_pd(_mm256_shuffle_ps(v0,v0,0xDD)),0xD8));
                __m256 v1_e = _mm256_castpd_ps(_mm256_permute4x64_pd(_mm256_castps_pd(_mm256_shuffle_ps(v1,v1,0x88)),0xD8));
                __m256 v1_o = _mm256_castpd_ps(_mm256_permute4x64_pd(_mm256_castps_pd(_mm256_shuffle_ps(v1,v1,0xDD)),0xD8));
                __m256 resLL = _mm256_mul_ps(_mm256_add_ps(_mm256_add_ps(v0_e, v0_o), _mm256_add_ps(v1_e, v1_o)), _mm256_set1_ps(0.25f));
                __m256 resHL = _mm256_mul_ps(_mm256_add_ps(_mm256_sub_ps(v0_e, v0_o), _mm256_sub_ps(v1_e, v1_o)), _mm256_set1_ps(0.25f));
                __m256 resLH = _mm256_mul_ps(_mm256_sub_ps(_mm256_add_ps(v0_e, v0_o), _mm256_add_ps(v1_e, v1_o)), _mm256_set1_ps(0.25f));
                __m256 resHH = _mm256_mul_ps(_mm256_sub_ps(_mm256_sub_ps(v0_e, v0_o), _mm256_sub_ps(v1_e, v1_o)), _mm256_set1_ps(0.25f));
                _mm_storeu_ps(&wll[x],_mm256_castps256_ps128(resLL)); _mm_storeu_ps(&whl[x],_mm256_castps256_ps128(resHL));
                _mm_storeu_ps(&wlh[x],_mm256_castps256_ps128(resLH)); _mm_storeu_ps(&whh[x],_mm256_castps256_ps128(resHH));
            }
            #endif
            for (; x < ow; ++x) {
                float a = r0[2*x], b_v = r0[2*x+1], c = r1[2*x], d = r1[2*x+1];
                wll[x] = (a+b_v+c+d)*0.25f; whl[x] = (a-b_v+c-d)*0.25f;
                wlh[x] = (a+b_v-c-d)*0.25f; whh[x] = (a-b_v-c+d)*0.25f;
            }
        }
    }
    void ihaar_2d_raw(const float* ll, const float* hl, const float* lh, const float* hh, float* b, int oh, int ow) {
        int w = ow*2;
        for (int y = 0; y < oh; ++y) {
            const float* rll = &ll[y*ow], *rhl = &hl[y*ow], *rlh = &lh[y*ow], *rhh = &hh[y*ow];
            float* w0 = &b[(2*y)*w], *w1 = &b[(2*y+1)*w];
            int x = 0;
            #ifdef WIMF_X86
            for (; x <= ow-4; x += 4) {
                __m128 vLL = _mm_loadu_ps(&rll[x]), vHL = _mm_loadu_ps(&rhl[x]), vLH = _mm_loadu_ps(&rlh[x]), vHH = _mm_loadu_ps(&rhh[x]);
                __m128 a = _mm_add_ps(_mm_add_ps(vLL,vHL),_mm_add_ps(vLH,vHH)), b_v = _mm_add_ps(_mm_sub_ps(vLL,vHL),_mm_sub_ps(vLH,vHH));
                __m128 c = _mm_sub_ps(_mm_add_ps(vLL,vHL),_mm_add_ps(vLH,vHH)), d = _mm_sub_ps(_mm_sub_ps(vLL,vHL),_mm_sub_ps(vLH,vHH));
                __m128 r0l = _mm_unpacklo_ps(a,b_v), r0h = _mm_unpackhi_ps(a,b_v), r1l = _mm_unpacklo_ps(c,d), r1h = _mm_unpackhi_ps(c,d);
                _mm_storeu_ps(&w0[x*2],r0l); _mm_storeu_ps(&w0[x*2+4],r0h); _mm_storeu_ps(&w1[x*2],r1l); _mm_storeu_ps(&w1[x*2+4],r1h);
            }
            #endif
            for (; x < ow; ++x) {
                float a = rll[x], b_v = rhl[x], c = rlh[x], d = rhh[x];
                w0[2*x] = a+b_v+c+d; w0[2*x+1] = a-b_v+c-d; w1[2*x] = a+b_v-c-d; w1[2*x+1] = a-b_v-c+d;
            }
        }
    }
}

// --- MONOLITHIC ---
struct ChannelBands { std::vector<int16_t> bands[7]; };

void process_channel_to_bands(const float* input, int h, int w, ChannelBands& out, float q1, float q2, float nf) {
    size_t sz_l1 = (size_t)(h/2)*(w/2), sz_l2 = (size_t)(h/4)*(w/4);
    std::vector<float> l1_ll(sz_l1), l1_hl(sz_l1), l1_lh(sz_l1), l1_hh(sz_l1);
    std::vector<float> l2_ll(sz_l2), l2_hl(sz_l2), l2_lh(sz_l2), l2_hh(sz_l2);
    haar_2d_raw(input, l1_ll.data(), l1_hl.data(), l1_lh.data(), l1_hh.data(), h, w);
    haar_2d_raw(l1_ll.data(), l2_ll.data(), l2_hl.data(), l2_lh.data(), l2_hh.data(), h/2, w/2);
    auto quant = [&](const std::vector<float>& src, std::vector<int16_t>& dst, float q, float deadzone) {
        dst.resize(src.size()); for (size_t i = 0; i < src.size(); ++i) {
            float v = src[i]; dst[i] = (std::abs(v) < deadzone) ? 0 : (int16_t)std::round(v / q);
        }
    };
    quant(l2_ll, out.bands[0], 1.0f, 0.0f);
    for (int i=1; i<4; ++i) quant(i==1?l2_hl:(i==2?l2_lh:l2_hh), out.bands[i], q2, nf);
    for (int i=4; i<7; ++i) quant(i==4?l1_hl:(i==5?l1_lh:l1_hh), out.bands[i], q1, nf);
}

py::bytes c_encode_lossy(py::array_t<float> input, int chans, int quality, std::string preset, py::dict meta) {
    auto buf = input.unchecked<3>(); int h = (int)buf.shape(1), w = (int)buf.shape(2);
    float ds = meta.contains("bit10") ? 4.0f : 1.0f;
    float q1 = std::max(1.0f, (16.0f*ds)-(quality*1.5f)), q2 = std::max(1.0f, (8.0f*ds)-(quality*0.75f)), nf = std::max(0.0f, (2.0f*ds)-(quality*0.2f));
    std::vector<int16_t> l0, l1, l2;
    for (int c = 0; c < chans; ++c) {
        ChannelBands cb; process_channel_to_bands(buf.data(c,0,0), h, w, cb, q1, q2, nf);
        l0.insert(l0.end(), cb.bands[0].begin(), cb.bands[0].end());
        for(int i=1; i<4; ++i) l1.insert(l1.end(), cb.bands[i].begin(), cb.bands[i].end());
        for(int i=4; i<7; ++i) l2.insert(l2.end(), cb.bands[i].begin(), cb.bands[i].end());
    }
    auto lzma = py::module_::import("lzma"); int lvl = (preset == "Extreme") ? 9 : 2;
    auto comp = [&](const std::vector<int16_t>& v) {
        return py::cast<std::string>(lzma.attr("compress")(py::bytes((char*)v.data(), v.size()*2), py::arg("preset")=lvl));
    };
    std::string s0 = comp(l0), s1 = comp(l1), s2 = comp(l2);
    std::string res = ""; res += (char)(quality << 4 | 9);
    auto add = [&](const std::string& s) { uint32_t len = s.size(); res.append((char*)&len, 4); res.append(s); };
    add(s0); add(s1); add(s2); return py::bytes(res);
}

py::array_t<uint8_t> c_decode_lossy(py::bytes data_bytes, int w, int h, int chans, py::dict meta) {
    std::string data = data_bytes; int offset = 1; int quality = (unsigned char)data[0] >> 4;
    float ds = meta.contains("bit10") ? 4.0f : 1.0f;
    float q1 = std::max(1.0f, (16.0f*ds)-(quality*1.5f)), q2 = std::max(1.0f, (8.0f*ds)-(quality*0.75f));
    auto lzma = py::module_::import("lzma");
    auto decomp = [&](int& off) {
        uint32_t len; std::memcpy(&len, &data[off], 4); off += 4;
        std::string d = py::cast<std::string>(lzma.attr("decompress")(py::bytes(&data[off], len))); off += len;
        std::vector<int16_t> res(d.size()/2); std::memcpy(res.data(), d.data(), d.size()); return res;
    };
    std::vector<int16_t> l0 = decomp(offset), l1 = decomp(offset), l2 = decomp(offset);
    int gh = (h+15)/16, gw = (w+15)/16;
    size_t sz_l0 = (size_t)gh*gw*16, sz_l1 = (size_t)gh*gw*16, sz_l2 = (size_t)gh*gw*64;
    auto result = py::array_t<uint8_t>({(size_t)h, (size_t)w, (size_t)chans}); auto mRes = result.mutable_unchecked<3>();
    for (int c = 0; c < chans; ++c) {
        std::vector<float> r2_ll(sz_l0), r2_hl(sz_l0), r2_lh(sz_l0), r2_hh(sz_l0), r1_ll(sz_l2);
        for(size_t i=0; i<sz_l0; ++i) r2_ll[i] = (float)l0[c*sz_l0+i];
        for(size_t i=0; i<sz_l0; ++i) { r2_hl[i]=(float)l1[(c*3+0)*sz_l1+i]*q2; r2_lh[i]=(float)l1[(c*3+1)*sz_l1+i]*q2; r2_hh[i]=(float)l1[(c*3+2)*sz_l1+i]*q2; }
        ihaar_2d_raw(r2_ll.data(), r2_hl.data(), r2_lh.data(), r2_hh.data(), r1_ll.data(), gh*4, gw*4);
        std::vector<float> r1_hl(sz_l2), r1_lh(sz_l2), r1_hh(sz_l2), r_full((size_t)gh*16*gw*16);
        for(size_t i=0; i<sz_l2; ++i) { r1_hl[i]=(float)l2[(c*3+0)*sz_l2+i]*q1; r1_lh[i]=(float)l2[(c*3+1)*sz_l2+i]*q1; r1_hh[i]=(float)l2[(c*3+2)*sz_l2+i]*q1; }
        ihaar_2d_raw(r1_ll.data(), r1_hl.data(), r1_lh.data(), r1_hh.data(), r_full.data(), gh*8, gw*8);
        for(int y=0; y<h; ++y) for(int x=0; x<w; ++x) mRes(y,x,c) = (uint8_t)std::clamp(r_full[y*gw*16+x], 0.0f, 255.0f);
    }
    return result;
}

// --- PARITY ENGINE ---
extern "C" {
    uint32_t calculate_checksum_raw(const uint8_t* data, size_t size) {
        uint64_t sum = 0;
        size_t i = 0;
        #ifdef WIMF_X86
        for (; i <= size - 32; i += 32) {
            __m256i v = _mm256_loadu_si256((const __m256i*)&data[i]);
            __m256i zero = _mm256_setzero_si256();
            __m256i sad = _mm256_sad_epu8(v, zero);
            sum += (uint64_t)_mm256_extract_epi64(sad, 0);
            sum += (uint64_t)_mm256_extract_epi64(sad, 1);
            sum += (uint64_t)_mm256_extract_epi64(sad, 2);
            sum += (uint64_t)_mm256_extract_epi64(sad, 3);
        }
        #endif
        for (; i < size; ++i) sum += data[i];
        return (uint32_t)(sum % 4294967295ULL);
    }

    void block_xor_raw(uint8_t* target, const uint8_t* source, size_t size) {
        size_t i = 0;
        #ifdef WIMF_X86
        for (; i <= size - 32; i += 32) {
            __m256i v0 = _mm256_loadu_si256((__m256i*)&target[i]);
            __m256i v1 = _mm256_loadu_si256((const __m256i*)&source[i]);
            _mm256_storeu_si256((__m256i*)&target[i], _mm256_xor_si256(v0, v1));
        }
        #elif defined(WIMF_ARM)
        for (; i <= size - 16; i += 16) {
            uint8x16_t v0 = vld1q_u8(&target[i]);
            uint8x16_t v1 = vld1q_u8(&source[i]);
            vst1q_u8(&target[i], veorq_u8(v0, v1));
        }
        #endif
        for (; i < size; ++i) target[i] ^= source[i];
    }
}

// --- ANIMATION & LOSSLESS ---
extern "C" {
    void calculate_frame_diff_raw(const uint8_t* prev, const uint8_t* curr, float* diff, size_t size) {
        for (size_t i = 0; i < size; ++i) {
            diff[i] = (float)curr[i] - (float)prev[i];
        }
    }
    py::array_t<uint8_t> select_best_filters_raw(const int16_t* r0, const int16_t* r1, const int16_t* r2, const int16_t* r3, int h, int w) {
        auto best = py::array_t<uint8_t>(h); auto mB = best.mutable_unchecked<1>();
        for (int y = 0; y < h; ++y) {
            int64_t c[4] = {0,0,0,0};
            for (int x = 0; x < w; ++x) {
                size_t off = y*w+x;
                c[0] += std::abs((int8_t)(r0[off] % 256)); c[1] += std::abs((int8_t)(r1[off] % 256));
                c[2] += std::abs((int8_t)(r2[off] % 256)); c[3] += std::abs((int8_t)(r3[off] % 256));
            }
            uint8_t b = 0; int64_t min_c = c[0];
            for (uint8_t i = 1; i < 4; ++i) { if (c[i] < min_c) { min_c = c[i]; b = i; } }
            mB(y) = b;
        }
        return best;
    }
}

// --- FILE I/O ---
#include <fstream>
void c_save_file(std::string path, py::bytes data) {
    std::string str = data;
    std::ofstream f(path, std::ios::out | std::ios::binary);
    if (!f) throw std::runtime_error("Could not open file for writing.");
    f.write(str.data(), str.size());
    f.close();
}

py::bytes c_load_file(std::string path) {
    std::ifstream f(path, std::ios::in | std::ios::binary | std::ios::ate);
    if (!f) throw std::runtime_error("Could not open file for reading.");
    std::streamsize size = f.tellg();
    f.seekg(0, std::ios::beg);
    std::string buffer(size, '\0');
    if (f.read(&buffer[0], size)) return py::bytes(buffer);
    throw std::runtime_error("File read error.");
}

PYBIND11_MODULE(wimf_cpp, m) {
    m.def("ycocg_forward", [](py::array_t<int32_t> a){ auto b = a.mutable_unchecked<3>(); ycocg_forward_raw(b.mutable_data(0,0,0), b.shape(1), b.shape(0)); });
    m.def("ycocg_inverse", [](const py::buffer& b){ py::buffer_info i = b.request(); ycocg_inverse_raw((float*)i.ptr, i.size/3); });
    m.def("haar_level", [](const py::array_t<float>& b){
        auto buf = b.unchecked<4>(); ssize_t n = buf.shape(0), c = buf.shape(1), h = buf.shape(2), w = buf.shape(3);
        auto LL = py::array_t<float>({n, c, h/2, w/2}), HL = py::array_t<float>({n, c, h/2, w/2});
        auto LH = py::array_t<float>({n, c, h/2, w/2}), HH = py::array_t<float>({n, c, h/2, w/2});
        auto mLL = LL.mutable_unchecked<4>(), mHL = HL.mutable_unchecked<4>(), mLH = LH.mutable_unchecked<4>(), mHH = HH.mutable_unchecked<4>();
        for (ssize_t i = 0; i < (ssize_t)n; ++i) for (ssize_t j = 0; j < (ssize_t)c; ++j) haar_2d_raw((float*)buf.data(i,j,0,0), mLL.mutable_data(i,j,0,0), mHL.mutable_data(i,j,0,0), mLH.mutable_data(i,j,0,0), mHH.mutable_data(i,j,0,0), (int)h, (int)w);
        return py::make_tuple(LL, HL, LH, HH);
    });
    m.def("calculate_checksum", [](py::array_t<uint8_t> d){ return calculate_checksum_raw(d.data(0), d.size()); });
    m.def("block_xor", [](py::array_t<uint8_t> t, py::array_t<uint8_t> s){ block_xor_raw((uint8_t*)t.mutable_data(0), (const uint8_t*)s.data(0), t.size()); });
    m.def("calculate_frame_diff", [](py::array_t<uint8_t> p, py::array_t<uint8_t> c, py::array_t<float> d){ calculate_frame_diff_raw(p.data(0), c.data(0), (float*)d.mutable_data(0), p.size()); });
    m.def("select_best_filters", [](py::array_t<int16_t> r0, py::array_t<int16_t> r1, py::array_t<int16_t> r2, py::array_t<int16_t> r3){
        return select_best_filters_raw(r0.data(0,0), r1.data(0,0), r2.data(0,0), r3.data(0,0), r0.shape(0), r0.shape(1));
    });
    m.def("parse_header", [](py::array_t<uint8_t> d){ const uint8_t* p=d.data(0); uint32_t w,h,m; std::memcpy(&w,p+4,4); std::memcpy(&h,p+8,4); std::memcpy(&m,p+13,4); return py::make_tuple(w,h,p[12],m); });
    m.def("c_encode_lossy", &c_encode_lossy); m.def("c_decode_lossy", &c_decode_lossy);
    m.def("c_save_file", &c_save_file); m.def("c_load_file", &c_load_file);
}
