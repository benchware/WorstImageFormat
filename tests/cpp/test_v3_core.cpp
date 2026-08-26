// WIMF 3.0 (oxygen) container tests: roundtrips across geometries, quadtree
// validation, corruption rejection, and WIM2 coexistence.
#include <cstdio>
#include <cstring>
#include <random>
#include <vector>

#include "v2_core.hpp"
#include "v3_core.hpp"

using namespace wimf::v3;
using wimf::v2::ImageView;

namespace {

int failures = 0;

void check(bool condition, const char* label) {
    if (!condition) {
        ++failures;
        printf("FAIL: %s\n", label);
    }
}

std::vector<uint8_t> make_image(uint32_t w, uint32_t h, uint8_t ch, int kind, unsigned seed) {
    std::mt19937 rng(seed);
    std::vector<uint8_t> px(static_cast<size_t>(w) * h * ch);
    for (uint32_t y = 0; y < h; ++y)
        for (uint32_t x = 0; x < w; ++x)
            for (uint8_t c = 0; c < ch; ++c) {
                const size_t i = (static_cast<size_t>(y) * w + x) * ch + c;
                if (kind == 0) px[i] = static_cast<uint8_t>((x * 255 / (w ? w : 1) + y * 7 + c * 13) & 255);
                else if (kind == 1) { std::uniform_int_distribution<int> d(0, 255); px[i] = static_cast<uint8_t>(d(rng)); }
                else px[i] = static_cast<uint8_t>(128 + ((x ^ y) & 15) - 8 + c);
            }
    return px;
}

bool roundtrip(uint32_t w, uint32_t h, uint8_t ch, uint16_t max_tile, int kind, const char* label) {
    auto pixels = make_image(w, h, ch, kind, static_cast<unsigned>(w * 31 + h));
    ImageView view{pixels.data(), w, h, ch, 1, static_cast<size_t>(w) * ch};
    EncodeOptionsV3 opt;
    opt.max_tile = max_tile;
    opt.metadata = "{\"fmt\":\"wim3\"}";
    std::vector<uint8_t> encoded;
    if (!wimf::v3::encode_image(view, opt, encoded)) {
        check(false, label);
        return false;
    }
    DecodeOptionsV3 dopt;
    wimf::v2::DecodeResult decoded;
    if (!wimf::v3::decode_image(encoded.data(), encoded.size(), dopt, decoded)) {
        check(false, label);
        return false;
    }
    const bool ok = decoded.pixels == pixels && decoded.width == w && decoded.height == h &&
                    decoded.channels == ch && decoded.metadata == "{\"fmt\":\"wim3\"}";
    check(ok, label);
    return ok;
}

void corrupt_and_expect_reject(const std::vector<uint8_t>& base, size_t offset, uint8_t value,
                               const char* label) {
    std::vector<uint8_t> blob = base;
    blob[offset] = value;
    DecodeOptionsV3 dopt;
    wimf::v2::DecodeResult decoded;
    check(!wimf::v3::decode_image(blob.data(), blob.size(), dopt, decoded), label);
}

}  // namespace

int main() {
    // CRC-32C known answer.
    {
        const uint8_t check9[] = "123456789";
        check(crc32c(check9, 9) == 0xE3069283u, "crc32c check value");
    }

    // Roundtrips: squares, wide, tall, prime-ish, tiny; multiple max_tile values
    // and content kinds exercise every leaf shape the halving rule can produce.
    roundtrip(64, 64, 3, 256, 0, "gradient 64x64 default tile");
    roundtrip(192, 160, 3, 256, 2, "photo-ish 192x160");
    roundtrip(300, 200, 1, 128, 0, "grayscale beyond-256 width");
    roundtrip(1000, 3, 3, 256, 0, "extreme aspect wide");
    roundtrip(3, 1000, 3, 256, 1, "extreme aspect tall noise");
    roundtrip(17, 17, 4, 16, 2, "min-tile rgba");
    roundtrip(1, 1, 1, 16, 0, "single pixel");
    roundtrip(512, 512, 3, 4096, 1, "one giant leaf");
    roundtrip(513, 513, 3, 256, 0, "split past power of two");

    // Corruption rejection.
    auto base = make_image(200, 140, 3, 0, 9);
    ImageView view{base.data(), 200, 140, 3, 1, static_cast<size_t>(200) * 3};
    EncodeOptionsV3 opt;
    std::vector<uint8_t> encoded;
    check(static_cast<bool>(wimf::v3::encode_image(view, opt, encoded)), "encode for corruption suite");

    DecodeOptionsV3 dopt;
    wimf::v2::DecodeResult decoded;
    check(static_cast<bool>(wimf::v3::decode_image(encoded.data(), encoded.size(), dopt, decoded)), "clean decode");
    check(decoded.pixels == base, "clean decode content");

    corrupt_and_expect_reject(encoded, 0, 'X', "bad magic");
    corrupt_and_expect_reject(encoded, 4, 2, "bad version");
    corrupt_and_expect_reject(encoded, 6, kDepthF16, "unsupported depth");
    // max_tile occupies bytes 16-17; force it to 15 (below the minimum of 16).
    {
        std::vector<uint8_t> blob = encoded;
        blob[16] = 15;
        blob[17] = 0;
        DecodeOptionsV3 dopts;
        wimf::v2::DecodeResult out;
        check(!wimf::v3::decode_image(blob.data(), blob.size(), dopts, out), "max_tile below minimum");
    }
    corrupt_and_expect_reject(encoded, 18, 0xFF, "metadata length overflow");
    corrupt_and_expect_reject(encoded, 22, 0xFF, "tree length overflow");

    // Payload CRC flip: last payload byte of the file.
    corrupt_and_expect_reject(encoded, encoded.size() - 1, static_cast<uint8_t>(encoded.back() ^ 0xFF),
                              "payload crc mismatch");

    // Truncations at every structural boundary must be rejected, never crash.
    for (size_t cut : {size_t{0}, size_t{10}, size_t{37}, size_t{38}, size_t{45}}) {
        DecodeOptionsV3 dopts;
        wimf::v2::DecodeResult out;
        check(!wimf::v3::decode_image(encoded.data(), cut, dopts, out), "truncated container rejected");
    }

    // Reserved bytes must stay zero.
    {
        std::vector<uint8_t> blob = encoded;
        const size_t record0 = 38 + 0 + 12;  // header + empty metadata + tree bytes... locate robustly:
        // tree length lives at offset 22; first record starts after metadata+tree.
        const uint32_t tree_len = static_cast<uint32_t>(blob[22]) |
                                   static_cast<uint32_t>(blob[23]) << 8 |
                                   static_cast<uint32_t>(blob[24]) << 16 |
                                   static_cast<uint32_t>(blob[25]) << 24;
        const size_t rec = 38 + tree_len;  // no metadata in this encode
        blob[rec + 18] = 1;
        DecodeOptionsV3 dopts;
        wimf::v2::DecodeResult out;
        check(!wimf::v3::decode_image(blob.data(), blob.size(), dopts, out), "reserved transform byte rejected");
        (void)record0;
    }

    // WIM2 coexistence: a v2 container still parses through the v2 parser.
    {
        auto pixels = make_image(80, 60, 3, 2, 4);
        ImageView v2view{pixels.data(), 80, 60, 3, 1, static_cast<size_t>(80) * 3};
        wimf::v2::EncodeOptions v2opt;
        v2opt.lossless = true;
        std::vector<uint8_t> v2blob;
        check(static_cast<bool>(wimf::v2::encode_image(v2view, v2opt, v2blob)), "v2 encode");
        bool threw = false;
        try {
            parse_container(v2blob.data(), v2blob.size());
        } catch (const std::exception&) {
            threw = true;  // v3 parser must reject WIM2 magic
        }
        check(threw, "v3 parser rejects WIM2");
        wimf::v2::DecodeResult v2out;
        check(static_cast<bool>(wimf::v2::decode_image(v2blob.data(), v2blob.size(), {}, v2out)),
              "v2 decodes own file");
    }

    // Embedded wavelet codec: exact lossless roundtrip on every content kind.
    {
        for (int kind = 0; kind < 3; ++kind) {
            auto pixels = make_image(70, 50, 3, kind, 11);
            ImageView view{pixels.data(), 70, 50, 3, 1, static_cast<size_t>(70) * 3};
            const auto payload = embedded::encode(view);
            const auto decoded =
                embedded::decode(payload.data(), payload.size(), 70, 50, 3, 1, 255);
            check(decoded == pixels, "embedded wavelet lossless roundtrip");
        }
    }

    // Progressive: decoding fewer planes yields a valid coarser image; a
    // payload cut at a plane boundary decodes exactly like the capped decode;
    // the full stream remains lossless.
    {
        auto pixels = make_image(64, 64, 1, 0, 21);
        ImageView view{pixels.data(), 64, 64, 1, 1, 64};
        const auto payload = embedded::encode(view);
        const uint16_t planes = static_cast<uint16_t>(payload[2] | payload[3] << 8);
        check(planes > 1, "embedded stream has multiple planes");

        // Single channel: one u32 length per plane after the 4-byte header.
        std::vector<size_t> plane_len(planes);
        size_t table_end = 4;
        for (unsigned p = 0; p < planes; ++p) {
            plane_len[p] = static_cast<size_t>(payload[table_end]) |
                           static_cast<size_t>(payload[table_end + 1]) << 8 |
                           static_cast<size_t>(payload[table_end + 2]) << 16 |
                           static_cast<size_t>(payload[table_end + 3]) << 24;
            table_end += 4;
        }
        size_t total = table_end;
        for (size_t len : plane_len) total += len;
        check(total == payload.size(), "plane lengths cover payload");

        const unsigned half = planes / 2;
        size_t cut = table_end;
        for (unsigned p = 0; p < half; ++p) cut += plane_len[p];
        std::vector<uint8_t> truncated(payload.begin(), payload.begin() + cut);

        const auto capped =
            embedded::decode(payload.data(), payload.size(), 64, 64, 1, 1,
                             static_cast<uint8_t>(half));
        const auto from_cut = embedded::decode(truncated.data(), truncated.size(), 64, 64, 1, 1, 255);
        check(capped == from_cut, "target-planes decode equals truncated-payload decode");
        const auto everything = embedded::decode(payload.data(), payload.size(), 64, 64, 1, 1, 255);
        check(everything == pixels, "full decode remains lossless");
        bool differs = capped != everything || half == planes;
        check(differs, "coarser decode actually differs from full decode");
    }

    // Container-level progressive query: capping planes stays structurally
    // valid while the uncapped decode stays exact.
    {
        auto pixels = make_image(96, 96, 3, 0, 22);
        ImageView view{pixels.data(), 96, 96, 3, 1, static_cast<size_t>(96) * 3};
        EncodeOptionsV3 opt;
        std::vector<uint8_t> blob;
        check(static_cast<bool>(encode_image(view, opt, blob)), "encode for progressive suite");
        DecodeOptionsV3 coarse;
        coarse.target_planes = 1;
        wimf::v2::DecodeResult rough;
        check(static_cast<bool>(decode_image(blob.data(), blob.size(), coarse, rough)),
              "single-plane decode succeeds");
        wimf::v2::DecodeResult full;
        check(static_cast<bool>(decode_image(blob.data(), blob.size(), DecodeOptionsV3{}, full)),
              "full decode succeeds");
        check(full.pixels == pixels, "container full decode remains lossless");
    }

    // 16-bit container roundtrip exercises the HDR depth enums end to end.
    {
        std::vector<uint16_t> pixels16;
        for (uint32_t y = 0; y < 40; ++y)
            for (uint32_t x = 0; x < 40; ++x)
                for (uint8_t c = 0; c < 3; ++c)
                    pixels16.push_back(static_cast<uint16_t>(((x * 1024 + y * 33 + c * 77) % 4000) + 100));
        std::vector<uint8_t> bytes(pixels16.size() * 2);
        for (size_t i = 0; i < pixels16.size(); ++i) {
            bytes[i * 2] = static_cast<uint8_t>(pixels16[i] & 0xFF);
            bytes[i * 2 + 1] = static_cast<uint8_t>(pixels16[i] >> 8);
        }
        ImageView view16{bytes.data(), 40, 40, 3, 2, static_cast<size_t>(40) * 3 * 2};
        EncodeOptionsV3 opt16;
        opt16.depth = kDepthU12;
        std::vector<uint8_t> blob;
        check(static_cast<bool>(encode_image(view16, opt16, blob)), "u12 encode");
        wimf::v2::DecodeResult out16;
        check(static_cast<bool>(decode_image(blob.data(), blob.size(), DecodeOptionsV3{}, out16)),
              "u12 decode");
        check(out16.bit_depth == 16 && out16.pixels == bytes, "u12 content exact");
        corrupt_and_expect_reject(blob, 6, kDepthF16, "f16 depth rejected");
    }

    if (failures == 0) printf("All WIMF v3 tests passed.\n");
    return failures ? 1 : 0;
}
