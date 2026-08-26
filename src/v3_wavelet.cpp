// Embedded bitplane wavelet codec for WIMF 3.0 tile mode 2.
//
// Coefficients come from the shared lossless CDF 5/3 lifting (v2), are
// reordered into dyadic subband sequence, and are coded one magnitude
// bitplane at a time. Each (plane, channel) pair flushes its own range-coder
// segment; payloads truncate at plane boundaries into valid coarser images,
// and decoders honor an explicit target-plane cap for progressive queries.
//
// The significance pass uses zerotree-style context: each coefficient's
// "became significant" decision is modeled per subband and keyed by whether
// its parent coefficient is already significant.
//
// Payload layout:
//   u8 channels, u8 levels, u16 plane_count
//   u32 segment_length[channels * plane_count]   (plane-major, then channel)
//   segments in the same order

#include "v3_core.hpp"

#include <algorithm>
#include <cstring>
#include <stdexcept>

namespace wimf::v3 {
namespace embedded {

using wimf::v2::ImageView;

constexpr uint32_t kRcTop = 1u << 24;
constexpr unsigned kMaxBands = 25;

struct BitModel {
    uint16_t prob = 1024;
    void update(int bit) { if (bit) prob -= prob >> 5; else prob += (2048 - prob) >> 5; }
};

struct RcEncoder {
    uint64_t low = 0;
    uint32_t range = 0xFFFFFFFFu;
    uint8_t cache = 0;
    uint64_t cache_size = 1;
    std::vector<uint8_t> output;
    void shift_low() {
        if ((low >> 32) != 0 || low < 0xFF000000ull) {
            const uint8_t carry = static_cast<uint8_t>((low >> 32) & 1);
            output.push_back(cache + carry);
            for (; cache_size > 1; --cache_size) output.push_back(0xFF + carry);
            cache = static_cast<uint8_t>((low >> 24) & 0xFF);
        } else {
            ++cache_size;
        }
        low = (low & 0x00FFFFFFull) << 8;
    }
    void encode(int bit, uint16_t prob) {
        const uint32_t bound = (range >> 11) * prob;
        if (!bit) {
            range = bound;
        } else {
            low += bound;
            range -= bound;
        }
        while (range < kRcTop) {
            shift_low();
            range <<= 8;
        }
    }
    void flush() {
        for (int i = 0; i < 5; ++i) shift_low();
    }
};

struct RcDecoder {
    uint32_t range = 0xFFFFFFFFu;
    uint32_t code = 0;
    const uint8_t* data = nullptr;
    size_t pos = 0;
    size_t limit = 0;
    void init(const uint8_t* bytes, size_t size) {
        data = bytes;
        limit = size;
        if (size < 5) throw std::runtime_error("truncated embedded wavelet segment");
        pos = 1;
        for (int i = 0; i < 4; ++i) code = (code << 8) | data[pos++];
    }
    int decode(uint16_t prob) {
        const uint32_t bound = (range >> 11) * prob;
        int bit;
        if (code < bound) {
            range = bound;
            bit = 0;
        } else {
            code -= bound;
            range -= bound;
            bit = 1;
        }
        while (range < kRcTop) {
            if (pos >= limit) throw std::runtime_error("corrupt embedded wavelet stream");
            code = (code << 8) | data[pos++];
            range <<= 8;
        }
        return bit;
    }
};

uint32_t next_pow2(uint32_t value) {
    uint32_t out = 1;
    while (out < std::max(2u, value)) out <<= 1;
    return out;
}

uint32_t symmetric_index(uint32_t index, uint32_t length) {
    if (length == 1) return 0;
    const uint32_t period = length * 2;
    const uint32_t folded = index % period;
    return folded < length ? folded : period - folded - 1;
}

uint8_t top_bit(uint64_t value) {
    uint8_t bit = 0;
    while (value >>= 1) ++bit;
    return bit;
}

struct BandRect {
    size_t base;  // first index within the reordered sequence
    uint32_t x, y, w, h;
};

// Must mirror reorder_subbands exactly: LL, then HL/LH/HH per level,
// coarsest first, each band row-major within its rectangle.
std::vector<BandRect> band_layout(uint32_t pw, uint32_t ph, unsigned levels) {
    std::vector<BandRect> bands;
    bands.reserve(1 + static_cast<size_t>(levels) * 3);
    const uint32_t lw = pw >> levels, lh = ph >> levels;
    size_t base = 0;
    bands.push_back({base, 0, 0, lw, lh});
    base += static_cast<size_t>(lw) * lh;
    for (unsigned level = levels; level >= 1; --level) {
        const uint32_t sw = pw >> level, sh = ph >> level;
        bands.push_back({base, sw, 0, sw, sh});
        base += static_cast<size_t>(sw) * sh;
        bands.push_back({base, 0, sh, sw, sh});
        base += static_cast<size_t>(sw) * sh;
        bands.push_back({base, sw, sh, sw, sh});
        base += static_cast<size_t>(sw) * sh;
    }
    return bands;
}

size_t locate(const std::vector<BandRect>& bands, uint32_t x, uint32_t y) {
    for (const BandRect& band : bands)
        if (x >= band.x && x < band.x + band.w && y >= band.y && y < band.y + band.h)
            return band.base + static_cast<size_t>(y - band.y) * band.w + (x - band.x);
    throw std::runtime_error("parent coordinate outside all bands");
}

// Parent index within the reordered sequence for every coefficient (-1 = LL root).
std::vector<int32_t> parent_map(const std::vector<BandRect>& bands, size_t count) {
    std::vector<int32_t> parents(count, -1);
    for (size_t b = 1; b < bands.size(); ++b) {
        const BandRect& band = bands[b];
        for (uint32_t y = band.y; y < band.y + band.h; ++y)
            for (uint32_t x = band.x; x < band.x + band.w; ++x) {
                const size_t self =
                    band.base + static_cast<size_t>(y - band.y) * band.w + (x - band.x);
                parents[self] = static_cast<int32_t>(locate(bands, x >> 1, y >> 1));
            }
    }
    return parents;
}

unsigned band_of(const std::vector<BandRect>& bands, size_t index) {
    for (unsigned b = static_cast<unsigned>(bands.size()); b-- > 0;)
        if (index >= bands[b].base) return b;
    return 0;
}

struct SigModels {
    BitModel sig[kMaxBands][2];  // [subband][parent significant]
    BitModel sign;
};

}  // namespace embedded

namespace embedded {

std::vector<uint8_t> encode(const ImageView& tile) {
    if (!tile.data || !tile.width || !tile.height || !tile.channels ||
        (tile.bytes_per_sample != 1 && tile.bytes_per_sample != 2))
        throw std::runtime_error("unsupported layout for embedded wavelet");
    const uint32_t pw = next_pow2(tile.width), ph = next_pow2(tile.height);
    unsigned levels = 0;
    for (uint32_t value = std::min(pw, ph); value > 1 && levels < 3; value >>= 1) ++levels;

    const auto bands = band_layout(pw, ph, levels);
    const auto parents = parent_map(bands, static_cast<size_t>(pw) * ph);
    SigModels models{};
    std::vector<std::vector<int64_t>> ordered(tile.channels);

    uint64_t max_magnitude = 0;
    std::vector<uint8_t> plane(static_cast<size_t>(pw) * ph * tile.bytes_per_sample);
    for (uint8_t c = 0; c < tile.channels; ++c) {
        for (uint32_t y = 0; y < ph; ++y)
            for (uint32_t x = 0; x < pw; ++x) {
                const uint32_t sx = symmetric_index(x, tile.width),
                               sy = symmetric_index(y, tile.height);
                const uint8_t* src = tile.data + static_cast<size_t>(sy) * tile.row_stride +
                                     (static_cast<size_t>(sx) * tile.channels + c) *
                                         tile.bytes_per_sample;
                uint8_t* dst =
                    plane.data() + (static_cast<size_t>(y) * pw + x) * tile.bytes_per_sample;
                dst[0] = src[0];
                if (tile.bytes_per_sample == 2) dst[1] = src[1];
            }
        auto coefficients = wimf::v2::wavelet_forward(plane.data(), pw, ph,
                                                      tile.bytes_per_sample, true, levels, 1.0);
        ordered[c] = wimf::v2::reorder_subbands_v2(coefficients, pw, ph, levels);
        for (const int64_t coef : ordered[c]) {
            const uint64_t mag =
                coef < 0 ? static_cast<uint64_t>(-(coef + 1)) + 1 : static_cast<uint64_t>(coef);
            max_magnitude = std::max(max_magnitude, mag);
        }
    }

    // Magnitudes drive every bitplane decision; sign rides separately. Using
    // raw two's-complement bits here would mark negatives significant at the
    // top plane (their sign-extension sets every high bit).
    std::vector<std::vector<uint64_t>> magnitudes(tile.channels);
    for (uint8_t c = 0; c < tile.channels; ++c) {
        magnitudes[c].resize(ordered[c].size());
        for (size_t i = 0; i < ordered[c].size(); ++i)
            magnitudes[c][i] = ordered[c][i] < 0
                                   ? static_cast<uint64_t>(-(ordered[c][i] + 1)) + 1
                                   : static_cast<uint64_t>(ordered[c][i]);
    }

    const int n_planes = max_magnitude == 0 ? 1 : top_bit(max_magnitude) + 1;

    struct ChannelState {
        std::vector<uint8_t> significant;
        std::vector<uint8_t> negative;
        std::vector<uint8_t> fresh;
    };
    std::vector<ChannelState> states(tile.channels);
    for (auto& state : states) {
        state.significant.assign(ordered[0].size(), 0);
        state.negative.assign(ordered[0].size(), 0);
        state.fresh.assign(ordered[0].size(), 0);
    }

    std::vector<uint32_t> lengths(static_cast<size_t>(tile.channels) * n_planes);
    std::vector<std::vector<uint8_t>> segments;
    segments.reserve(static_cast<size_t>(tile.channels) * n_planes);

    for (int plane_bit = n_planes - 1; plane_bit >= 0; --plane_bit) {
        for (uint8_t c = 0; c < tile.channels; ++c) {
            ChannelState& state = states[c];
            const auto& mags = magnitudes[c];
            const auto& coefs = ordered[c];
            for (auto& flag : state.fresh) flag = 0;
            RcEncoder encoder;
            // Significance pass.
            for (size_t i = 0; i < coefs.size(); ++i) {
                if (state.significant[i]) continue;
                const int parent_sig = parents[i] >= 0 ? state.significant[parents[i]] : 0;
                BitModel& model = models.sig[band_of(bands, i)][parent_sig];
                const int becomes = static_cast<int>((mags[i] >> plane_bit) & 1);
                encoder.encode(becomes, model.prob);
                model.update(becomes);
                if (becomes) {
                    state.significant[i] = 1;
                    state.fresh[i] = 1;
                    const int negative = coefs[i] < 0 ? 1 : 0;
                    encoder.encode(negative, models.sign.prob);
                    models.sign.update(negative);
                    state.negative[i] = static_cast<uint8_t>(negative);
                }
            }
            // Refinement pass over coefficients significant at earlier planes.
            for (size_t i = 0; i < coefs.size(); ++i) {
                if (!state.significant[i] || state.fresh[i]) continue;
                encoder.encode(static_cast<int>((mags[i] >> plane_bit) & 1), 1024);
            }
            encoder.flush();
            lengths[static_cast<size_t>(c) * n_planes +
                    (n_planes - 1 - plane_bit)] = static_cast<uint32_t>(encoder.output.size());
            segments.push_back(std::move(encoder.output));
        }
    }

    const uint16_t plane_count = static_cast<uint16_t>(n_planes);
    std::vector<uint8_t> out;
    size_t total_bytes = 4 + segments.size() * 4;
    for (const auto& segment : segments) total_bytes += segment.size();
    out.reserve(total_bytes);
    out.push_back(tile.channels);
    out.push_back(static_cast<uint8_t>(levels));
    out.push_back(static_cast<uint8_t>(plane_count & 0xFF));
    out.push_back(static_cast<uint8_t>(plane_count >> 8));
    for (const uint32_t len : lengths)
        for (int i = 0; i < 4; ++i) out.push_back(static_cast<uint8_t>(len >> (i * 8)));
    for (const auto& segment : segments) out.insert(out.end(), segment.begin(), segment.end());
    return out;
}

std::vector<uint8_t> decode(const uint8_t* data, size_t size, uint32_t width, uint32_t height,
                            uint8_t channels, uint8_t bytes_per_sample, uint8_t target_planes) {
    if (!data || size < 4) throw std::runtime_error("truncated embedded wavelet payload");
    const uint8_t stored_channels = data[0];
    const unsigned levels = data[1];
    const uint16_t plane_count =
        static_cast<uint16_t>(data[2] | data[3] << 8);
    if (stored_channels != channels || levels > 8 || plane_count == 0)
        throw std::runtime_error("invalid embedded wavelet header");
    if (size < 4 + static_cast<size_t>(stored_channels) * plane_count * 4)
        throw std::runtime_error("truncated embedded wavelet lengths");

    // How many planes fit in the available bytes (file truncation), capped by
    // the caller's progressive target.
    std::vector<uint32_t> lengths(static_cast<size_t>(stored_channels) * plane_count);
    size_t cursor = 4;
    for (auto& len : lengths) {
        len = static_cast<uint32_t>(data[cursor]) | static_cast<uint32_t>(data[cursor + 1]) << 8 |
              static_cast<uint32_t>(data[cursor + 2]) << 16 |
              static_cast<uint32_t>(data[cursor + 3]) << 24;
        cursor += 4;
    }
    unsigned planes_usable = 0;
    size_t consumed = cursor;
    for (unsigned p = 0; p < plane_count; ++p) {
        size_t plane_bytes = 0;
        for (uint8_t c = 0; c < stored_channels; ++c) plane_bytes += lengths[static_cast<size_t>(c) * plane_count + p];
        if (consumed + plane_bytes > size) break;
        consumed += plane_bytes;
        ++planes_usable;
    }
    const unsigned planes_to_decode =
        std::min<unsigned>(planes_usable, target_planes == 255 ? plane_count : target_planes);

    const uint32_t pw = next_pow2(width), ph = next_pow2(height);
    const auto bands = band_layout(pw, ph, levels);
    const auto parents = parent_map(bands, static_cast<size_t>(pw) * ph);

    struct ChannelState {
        std::vector<uint8_t> significant;
        std::vector<uint8_t> negative;
        std::vector<uint8_t> fresh;
        std::vector<int64_t> value;
    };
    std::vector<ChannelState> states(channels);
    const size_t coef_count = static_cast<size_t>(pw) * ph;
    for (auto& state : states) {
        state.significant.assign(coef_count, 0);
        state.negative.assign(coef_count, 0);
        state.fresh.assign(coef_count, 0);
        state.value.assign(coef_count, 0);
    }

    SigModels models{};
    size_t segment_base = cursor;
    for (unsigned p = 0; p < planes_to_decode; ++p) {
        const int plane_bit = plane_count - 1 - static_cast<int>(p);
        for (uint8_t c = 0; c < channels; ++c) {
            ChannelState& state = states[c];
            const uint32_t length =
                lengths[static_cast<size_t>(c) * plane_count + p];
            RcDecoder decoder;
            decoder.init(data + segment_base, length);
            segment_base += length;
            for (auto& flag : state.fresh) flag = 0;
            // Significance pass.
            for (size_t i = 0; i < coef_count; ++i) {
                if (state.significant[i]) continue;
                const int parent_sig = parents[i] >= 0 ? state.significant[parents[i]] : 0;
                BitModel& model = models.sig[band_of(bands, i)][parent_sig];
                const int becomes = decoder.decode(model.prob);
                model.update(becomes);
                if (becomes) {
                    state.significant[i] = 1;
                    state.fresh[i] = 1;
                    const int negative = decoder.decode(models.sign.prob);
                    models.sign.update(negative);
                    state.negative[i] = static_cast<uint8_t>(negative);
                    state.value[i] = int64_t{1} << plane_bit;
                }
            }
            // Refinement pass.
            for (size_t i = 0; i < coef_count; ++i) {
                if (!state.significant[i] || state.fresh[i]) continue;
                const int bit = decoder.decode(1024);
                state.value[i] |= static_cast<int64_t>(bit) << plane_bit;
            }
        }
    }

    // Reconstruct and crop each channel into the interleaved output image.
    std::vector<uint8_t> out(static_cast<size_t>(width) * height * channels * bytes_per_sample);
    std::vector<int64_t> ordered(coef_count);
    for (uint8_t c = 0; c < channels; ++c) {
        ChannelState& state = states[c];
        for (size_t i = 0; i < coef_count; ++i) {
            ordered[i] = state.significant[i]
                             ? (state.negative[i] ? -state.value[i] : state.value[i])
                             : 0;
        }
        auto raster = wimf::v2::restore_raster_order_v2(ordered, pw, ph, levels);
        auto plane_pixels = wimf::v2::wavelet_inverse(raster.data(), raster.size(), pw, ph,
                                                      bytes_per_sample, true, levels, 1.0);
        for (uint32_t y = 0; y < height; ++y)
            for (uint32_t x = 0; x < width; ++x) {
                const uint8_t* src = plane_pixels.data() +
                                     (static_cast<size_t>(y) * pw + x) * bytes_per_sample;
                uint8_t* dst = out.data() +
                               (static_cast<size_t>(y) * width + x) * channels * bytes_per_sample +
                               static_cast<size_t>(c) * bytes_per_sample;
                dst[0] = src[0];
                if (bytes_per_sample == 2) dst[1] = src[1];
            }
    }
    return out;
}

}  // namespace embedded
}  // namespace wimf::v3
