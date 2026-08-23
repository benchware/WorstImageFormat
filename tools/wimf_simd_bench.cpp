// WIMF native SIMD kernel benchmark.
//
// Times the predictive-filter and CRC-32 kernels behind the runtime dispatch
// layer on the current host (scalar reference versus AVX2/NEON where the host
// supports them), plus end-to-end lossless encode/decode of a deterministic
// synthetic sample image. Output is GitHub-flavored Markdown on stdout so CI
// can paste it straight into a job summary.
//
// Methodology: deterministic PRNG inputs, one warmup pass, then the minimum
// wall time of several repetitions (steady_clock); checksum sinks are printed
// so compilers cannot elide the measured work. Rates from different machines
// are NOT comparable — compare backends only within a single run/report.

#include "v2_core.hpp"
#include "v2_simd.hpp"

#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace simd = wimf::v2::simd;

namespace {

using Clock = std::chrono::steady_clock;

constexpr size_t kFilterRowWidth = 256;
constexpr size_t kFilterRows = 32768;   // 8 MiB of filter input per pass
constexpr size_t kCrcBytes = 16u << 20; // 16 MiB CRC input per pass
constexpr int kWarmups = 1;
constexpr int kRepetitions = 6;

struct FilterRates {
    double cost = 0.0;
    double emit = 0.0;
};

std::vector<uint8_t> make_random_bytes(size_t count, uint32_t seed) {
    std::mt19937 rng(seed);
    std::vector<uint8_t> data(count);
    for (uint8_t& byte : data) byte = static_cast<uint8_t>(rng());
    return data;
}

// Runs `measure_once` repeatedly and converts the fastest pass into a rate of
// `units` (bytes or pixels) per second, reported in millions per second.
template <class Function>
double best_millions_per_second(double units, Function measure_once) {
    for (int i = 0; i < kWarmups; ++i) measure_once();
    double best = 0.0;
    for (int i = 0; i < kRepetitions; ++i) {
        const Clock::time_point start = Clock::now();
        measure_once();
        const Clock::time_point stop = Clock::now();
        const double seconds =
            std::chrono::duration_cast<std::chrono::duration<double>>(stop - start).count();
        if (seconds <= 0.0) continue;
        const double rate = units / seconds / 1000000.0;
        if (rate > best) best = rate;
    }
    return best;
}

std::string format_rate(double rate) {
    std::ostringstream text;
    text << std::fixed << std::setprecision(1) << rate;
    return text.str();
}

// Times one backend's filter kernels over the shared row buffer, treating it
// as independent kFilterRowWidth-byte rows exactly like tiled codec rows.
template <class CostKernel, class EmitKernel>
FilterRates bench_filter(const std::vector<uint8_t>& rows, uint64_t& sink,
                         CostKernel cost_kernel, EmitKernel emit_kernel) {
    const size_t width = kFilterRowWidth;
    std::vector<uint8_t> residuals(width);
    uint64_t local = 0;
    FilterRates rates;
    rates.cost = best_millions_per_second(static_cast<double>(rows.size()), [&] {
        for (size_t r = 0; r < kFilterRows; ++r)
            local ^= cost_kernel(rows.data() + r * width, width);
    });
    rates.emit = best_millions_per_second(static_cast<double>(rows.size()), [&] {
        for (size_t r = 0; r < kFilterRows; ++r) {
            emit_kernel(rows.data() + r * width, residuals.data(), width);
            local += residuals[width / 2];
        }
    });
    sink ^= local;
    return rates;
}

void run(std::ostream& out) {
    const char* arch = "unknown";
#if defined(__aarch64__) || defined(_M_ARM64)
    arch = "arm64";
#elif defined(__x86_64__) || defined(_M_X64)
    arch = "x86_64";
#endif

    out << "# WIMF SIMD kernel benchmark\n\n";
    out << "- Architecture: `" << arch << "`\n";
    out << "- Dispatched AVX2: " << (simd::has_avx2() ? "active" : "inactive") << '\n';
    out << "- Hardware CRC-32: " << (simd::has_hardware_crc32() ? "active" : "inactive") << '\n';
    out << "- Inputs: deterministic PRNG (seed 20260823/20260824); " << kFilterRows
        << " filter rows x " << kFilterRowWidth << " B; " << (kCrcBytes >> 20)
        << " MiB CRC buffer\n";
    out << "- Timing: " << kWarmups << " warmup, minimum of " << kRepetitions
        << " timed passes (steady_clock)\n";

    const std::vector<uint8_t> rows =
        make_random_bytes(kFilterRows * kFilterRowWidth, 20260823);
    const std::vector<uint8_t> crc_data = make_random_bytes(kCrcBytes, 20260824);
    uint64_t sink = 0;

    struct BackendRow {
        const char* name;
        FilterRates rates;
    };
    std::vector<BackendRow> filter_rows;
    filter_rows.push_back({"scalar", bench_filter(
        rows, sink,
        [](const uint8_t* p, size_t w) { return simd::scalar::left_filter_cost(p, w); },
        [](const uint8_t* p, uint8_t* o, size_t w) { simd::scalar::left_filter_emit(p, o, w); })});
#if defined(WIMF_AVX2_KERNELS)
    if (simd::has_avx2())
        filter_rows.push_back({"avx2", bench_filter(
            rows, sink,
            [](const uint8_t* p, size_t w) { return simd::avx2::left_filter_cost(p, w); },
            [](const uint8_t* p, uint8_t* o, size_t w) { simd::avx2::left_filter_emit(p, o, w); })});
#endif
#if defined(WIMF_NEON)
    filter_rows.push_back({"neon", bench_filter(
        rows, sink,
        [](const uint8_t* p, size_t w) { return simd::neon::left_filter_cost(p, w); },
        [](const uint8_t* p, uint8_t* o, size_t w) { simd::neon::left_filter_emit(p, o, w); })});
#endif

    out << "\n## Predictive left filter (input MB/s)\n\n";
    out << "| Backend | Cost | Emit |\n|---|---:|---:|\n";
    for (const BackendRow& row : filter_rows)
        out << "| " << row.name << " | " << format_rate(row.rates.cost) << " | "
            << format_rate(row.rates.emit) << " |\n";

    const FilterRates& scalar_rates = filter_rows.front().rates;
    out << "\n## Filter speedup vs scalar\n\n";
    if (scalar_rates.cost > 0.0 && scalar_rates.emit > 0.0) {
        out << "| Backend | Cost | Emit |\n|---|---:|---:|\n";
        for (size_t i = 1; i < filter_rows.size(); ++i) {
            std::ostringstream cost_ratio, emit_ratio;
            cost_ratio << std::fixed << std::setprecision(2)
                       << filter_rows[i].rates.cost / scalar_rates.cost;
            emit_ratio << std::fixed << std::setprecision(2)
                       << filter_rows[i].rates.emit / scalar_rates.emit;
            out << "| " << filter_rows[i].name << " | " << cost_ratio.str() << "x | "
                << emit_ratio.str() << "x |\n";
        }
    } else {
        out << "_scalar reference produced no measurable rate._\n";
    }

    out << "\n## CRC-32 (input MB/s)\n\n| Backend | Rate |\n|---|---:|\n";
    const double table_rate = best_millions_per_second(
        static_cast<double>(kCrcBytes),
        [&] { sink ^= simd::crc32_table(crc_data.data(), crc_data.size()); });
    out << "| table (scalar) | " << format_rate(table_rate) << " |\n";
#if defined(WIMF_NEON)
    if (simd::has_hardware_crc32()) {
        const double hw_rate = best_millions_per_second(
            static_cast<double>(kCrcBytes),
            [&] { sink ^= simd::crc32_hw::compute(crc_data.data(), crc_data.size()); });
        out << "| hardware (ARM CRC extension) | " << format_rate(hw_rate) << " |\n";
    }
#endif
    const double dispatched_rate = best_millions_per_second(
        static_cast<double>(kCrcBytes),
        [&] { sink ^= simd::crc32(crc_data.data(), crc_data.size()); });
    out << "| dispatched (what the codec uses) | " << format_rate(dispatched_rate) << " |\n";

    // Synthetic sample image: smooth gradient with bounded noise, sized like a
    // couple of full tiles. Lossless round-trip doubles as a correctness check.
    constexpr uint32_t kImageWidth = 512, kImageHeight = 320, kImageChannels = 3;
    std::vector<uint8_t> image(static_cast<size_t>(kImageWidth) * kImageHeight *
                               kImageChannels);
    {
        std::mt19937 rng(20260825);
        for (uint32_t y = 0; y < kImageHeight; ++y) {
            for (uint32_t x = 0; x < kImageWidth; ++x) {
                const uint8_t base = static_cast<uint8_t>(
                    (x * 255u / (kImageWidth - 1u) + y * 255u / (kImageHeight - 1u)) / 2u);
                for (uint8_t c = 0; c < kImageChannels; ++c) {
                    const int noise = static_cast<int>(rng() % 33) - 16;
                    const int value = static_cast<int>(base) + noise;
                    image[(static_cast<size_t>(y) * kImageWidth + x) * kImageChannels + c] =
                        static_cast<uint8_t>(value < 0 ? 0 : (value > 255 ? 255 : value));
                }
            }
        }
    }

    const wimf::v2::ImageView view{image.data(), kImageWidth, kImageHeight, kImageChannels,
                                   1, static_cast<size_t>(kImageWidth) * kImageChannels};
    wimf::v2::EncodeOptions encode_options;
    encode_options.lossless = true;
    encode_options.preset = wimf::v2::SearchPreset::Fast;
    encode_options.execution = wimf::v2::ExecutionPolicy::Synchronous;
    wimf::v2::DecodeOptions decode_options;
    decode_options.execution = wimf::v2::ExecutionPolicy::Synchronous;

    std::vector<uint8_t> encoded;
    const double image_units = static_cast<double>(kImageWidth) * kImageHeight;
    const double encode_rate = best_millions_per_second(image_units, [&] {
        const wimf::v2::Status status =
            wimf::v2::encode_image(view, encode_options, encoded);
        if (!status) throw std::runtime_error("sample encode failed: " + status.message);
    });
    out << "\n## Synthetic sample image " << kImageWidth << "x" << kImageHeight << "x"
        << static_cast<int>(kImageChannels) << " lossless (dispatched backend)\n\n";
    out << "| Stage | MP/s |\n|---|---:|\n";

    wimf::v2::DecodeResult decoded;
    const double decode_rate = best_millions_per_second(image_units, [&] {
        const wimf::v2::Status status = wimf::v2::decode_image(
            encoded.data(), encoded.size(), decode_options, decoded);
        if (!status) throw std::runtime_error("sample decode failed: " + status.message);
    });
    if (decoded.pixels != image) throw std::runtime_error("sample round-trip changed pixels");
    out << "| encode | " << format_rate(encode_rate) << " |\n";
    out << "| decode | " << format_rate(decode_rate) << " |\n";

    // Printed checksum sink: proves every measured pass really ran.
    out << "\n<!-- sink=" << std::hex << sink << std::dec << " -->\n";
}

}  // namespace

int main() {
    try {
        run(std::cout);
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Benchmark failed: " << error.what() << '\n';
        return 1;
    }
}
