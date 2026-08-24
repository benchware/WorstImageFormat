// WIMF rate-distortion sweep tool.
//
// Encodes a deterministic synthetic corpus (smooth gradient, gradient+noise,
// high-frequency detail, mixed-frequency photo-like scene, natural 1/f-spectrum
// value noise) at every quality 1-10 across all presets, decodes, and reports
// size + PSNR per combination as a Markdown table. Built for the tuning
// workflow: different -DWIMF_LADDER_SCALE / -DWIMF_SCORING_DIVISOR compile
// definitions produce comparable tables for side-by-side review.

#include "v2_core.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <limits>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

#ifndef WIMF_LADDER_SCALE
#define WIMF_LADDER_SCALE 1.5f
#endif
#ifndef WIMF_SCORING_DIVISOR
#define WIMF_SCORING_DIVISOR 16.0
#endif

#define WIMF_STR2(x) #x
#define WIMF_STR(x) WIMF_STR2(x)

namespace {

using Clock = std::chrono::steady_clock;

constexpr uint32_t kWidth = 256, kHeight = 256, kChannels = 3;

enum class Pattern { Smooth, GradientNoise, Detail, Photo, Natural };

// Bilinear value-noise octave: a coarse random grid smoothly interpolated up
// to full resolution. Summing octaves at 1/16, 1/4, and 1 pixel pitch with
// geometrically falling amplitudes approximates the 1/f power spectrum of
// natural photographs - the closest deterministic proxy we can ship in-repo.
double noise_octave(const std::vector<double>& grid, uint32_t grid_size, uint32_t x, uint32_t y) {
    const double fx = static_cast<double>(x) * (grid_size - 1) / static_cast<double>(kWidth - 1);
    const double fy = static_cast<double>(y) * (grid_size - 1) / static_cast<double>(kHeight - 1);
    const uint32_t x0 = static_cast<uint32_t>(fx), y0 = static_cast<uint32_t>(fy);
    const uint32_t x1 = std::min(x0 + 1, grid_size - 1), y1 = std::min(y0 + 1, grid_size - 1);
    const double tx = fx - x0, ty = fy - y0;
    const double top = grid[y0 * grid_size + x0] * (1 - tx) + grid[y0 * grid_size + x1] * tx;
    const double bottom = grid[y1 * grid_size + x0] * (1 - tx) + grid[y1 * grid_size + x1] * tx;
    return top * (1 - ty) + bottom * ty;
}

std::vector<uint8_t> make_image(Pattern pattern, uint32_t seed) {
    std::mt19937 rng(seed);
    std::vector<uint8_t> image(static_cast<size_t>(kWidth) * kHeight * kChannels);
    // Natural pattern: pre-generate the value-noise grids once, per channel
    // and octave, so the per-pixel loop only does bilinear interpolation.
    std::vector<double> natural_grids[3][3];
    if (pattern == Pattern::Natural) {
        const uint32_t sizes[3] = {17, 65, 257};
        for (uint8_t c = 0; c < kChannels; ++c) {
            std::mt19937 channel_rng(seed + c * 7919u);
            for (int octave = 0; octave < 3; ++octave) {
                natural_grids[c][octave].resize(static_cast<size_t>(sizes[octave]) * sizes[octave]);
                for (double& g : natural_grids[c][octave])
                    g = static_cast<double>(channel_rng() % 2000) / 1000.0 - 1.0;
            }
        }
    }
    for (uint32_t y = 0; y < kHeight; ++y) {
        for (uint32_t x = 0; x < kWidth; ++x) {
            for (uint8_t c = 0; c < kChannels; ++c) {
                const uint8_t gradient = static_cast<uint8_t>((x * 255u / (kWidth - 1u) + y * 255u / (kHeight - 1u)) / 2u);
                uint8_t value = gradient;
                if (pattern == Pattern::GradientNoise) {
                    const int noise = static_cast<int>(rng() % 33) - 16;
                    const int mixed = static_cast<int>(gradient) + noise;
                    value = static_cast<uint8_t>(mixed < 0 ? 0 : (mixed > 255 ? 255 : mixed));
                } else if (pattern == Pattern::Detail) {
                    value = static_cast<uint8_t>(((x * 7 + y * 13 + c * 61) ^ (x * 3 + y * 5)) & 255);
                } else if (pattern == Pattern::Natural) {
                    // Three octaves of smooth value noise over a gentle
                    // gradient: coarse structure, mid detail, fine grain.
                    // Grids were generated once below; per-pixel work here is
                    // three bilinear lookups.
                    const uint32_t sizes[3] = {17, 65, 257};
                    const double amps[3] = {42.0, 18.0, 7.0};
                    double sample = 118.0 + (static_cast<int>(x * 30 / (kWidth - 1)) + static_cast<int>(y * 20 / (kHeight - 1)));
                    for (int octave = 0; octave < 3; ++octave)
                        sample += amps[octave] * noise_octave(natural_grids[c][octave], sizes[octave], x, y);
                    sample += static_cast<double>(c) * 3.0;
                    value = static_cast<uint8_t>(sample < 0.0 ? 0 : (sample > 255.0 ? 255 : sample));
                } else if (pattern == Pattern::Photo) {
                    const double fx = static_cast<double>(x) / static_cast<double>(kWidth - 1);
                    const double fy = static_cast<double>(y) / static_cast<double>(kHeight - 1);
                    double sample;
                    if (fy < 0.45) {
                        // sky: smooth vertical falloff with faint grain
                        sample = 205.0 - fy * 130.0 + static_cast<int>(rng() % 5) - 2;
                    } else if (fy < 0.5) {
                        // horizon band: dark strip with a slow ripple
                        sample = 78.0 + 18.0 * std::sin(fx * 40.0 * 3.14159265358979);
                    } else {
                        // ground: medium-frequency texture plus moderate grain
                        sample = 92.0 +
                                 34.0 * std::sin(fx * 25.0 * 3.14159265358979 + std::sin(fy * 60.0)) +
                                 static_cast<int>(rng() % 17) - 8;
                    }
                    // round object straddling the horizon: sharp edges, flat interior
                    const double dx = fx - 0.62;
                    const double dy = fy - 0.42;
                    if (dx * dx + dy * dy < 0.006) sample = 30.0;
                    // per-channel offset so chroma decorrelation has something to model
                    sample += static_cast<double>(c) * 4.0;
                    value = static_cast<uint8_t>(sample < 0.0 ? 0 : (sample > 255.0 ? 255 : sample));
                }
                image[(static_cast<size_t>(y) * kWidth + x) * kChannels + c] = value;
            }
        }
    }
    return image;
}

double psnr(const std::vector<uint8_t>& original, const std::vector<uint8_t>& decoded) {
    if (original.size() != decoded.size() || original.empty()) return 0.0;
    double squared = 0.0;
    for (size_t i = 0; i < original.size(); ++i) {
        const double delta = static_cast<double>(original[i]) - static_cast<double>(decoded[i]);
        squared += delta * delta;
    }
    const double mse = squared / static_cast<double>(original.size());
    if (mse <= 0.0) return std::numeric_limits<double>::infinity();
    return 10.0 * std::log10(255.0 * 255.0 / mse);
}

const char* pattern_name(Pattern pattern) {
    switch (pattern) {
        case Pattern::Smooth: return "smooth";
        case Pattern::GradientNoise: return "gradient+noise";
        case Pattern::Detail: return "high-detail";
        case Pattern::Photo: return "photo";
        case Pattern::Natural: return "natural";
    }
    return "?";
}

}  // namespace

int main() {
    try {
        const char* ladder = WIMF_STR(WIMF_LADDER_SCALE);
        const char* divisor = WIMF_STR(WIMF_SCORING_DIVISOR);
        std::cout << "## RD sweep - ladder scale " << ladder << ", scoring divisor " << divisor << "\n\n";

        const wimf::v2::SearchPreset presets[] = {
            wimf::v2::SearchPreset::Fast, wimf::v2::SearchPreset::Balanced, wimf::v2::SearchPreset::Extreme};
        const char* preset_names[] = {"Fast", "Balanced", "Extreme"};

        std::cout << "| Image | Preset | Q | Size (KB) | PSNR (dB) | Encode (ms) |\n";
        std::cout << "|---|---|---:|---:|---:|---:|\n";
        std::cout << std::fixed << std::setprecision(2);

        for (auto pattern : {Pattern::Smooth, Pattern::GradientNoise, Pattern::Detail, Pattern::Photo,
                             Pattern::Natural}) {
            const std::vector<uint8_t> image = make_image(pattern, 20260823 + static_cast<uint32_t>(pattern));
            const wimf::v2::ImageView view{image.data(), kWidth, kHeight, kChannels, 1,
                                           static_cast<size_t>(kWidth) * kChannels};

            for (int preset_index = 0; preset_index < 3; ++preset_index) {
                for (int quality = 1; quality <= 10; ++quality) {
                    wimf::v2::EncodeOptions options;
                    options.quality = quality;
                    options.preset = presets[preset_index];
                    options.execution = wimf::v2::ExecutionPolicy::Synchronous;
                    options.codec = wimf::v2::CodecMode::Auto;

                    std::vector<uint8_t> encoded;
                    const Clock::time_point start = Clock::now();
                    const wimf::v2::Status status = wimf::v2::encode_image(view, options, encoded);
                    const Clock::time_point stop = Clock::now();
                    if (!status) throw std::runtime_error(std::string("encode failed: ") + status.message);

                    wimf::v2::DecodeResult decoded;
                    wimf::v2::DecodeOptions decode_options;
                    decode_options.execution = wimf::v2::ExecutionPolicy::Synchronous;
                    const wimf::v2::Status decode_status = wimf::v2::decode_image(
                        encoded.data(), encoded.size(), decode_options, decoded);
                    if (!decode_status)
                        throw std::runtime_error(std::string("decode failed: ") + decode_status.message);

                    const double milliseconds =
                        std::chrono::duration_cast<std::chrono::duration<double, std::milli>>(stop - start).count();
                    const double quality_psnr = psnr(image, decoded.pixels);

                    std::cout << "| " << pattern_name(pattern) << " | " << preset_names[preset_index] << " | "
                              << quality << " | " << static_cast<double>(encoded.size()) / 1024.0 << " | ";
                    if (std::isinf(quality_psnr))
                        std::cout << "inf";
                    else
                        std::cout << quality_psnr;
                    std::cout << " | " << milliseconds << " |\n";
                }
            }
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "RD sweep failed: " << error.what() << '\n';
        return 1;
    }
}
