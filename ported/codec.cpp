#include "codec.hpp"

namespace wimf
{
    
    std::vector<uint8_t> EncodeLosslessChannel(
        const std::vector<uint8_t>& channel,
        uint32_t width,
        uint32_t height
    ) {

    };

    std::vector<uint8_t> DecodeLosslessChannel(
        const uint8_t* data,
        uint32_t width,
        uint32_t height
    ) {

    };

   
    std::vector<uint8_t> EncodeLossless(
        const uint8_t* pixels,
        uint32_t width,
        uint32_t height,
        uint32_t channels,
        const std::string& preset = "Balanced"
    ) {

    };

    std::vector<uint8_t> DecodeLossless(
        const std::vector<uint8_t>& compressed,
        uint32_t width,
        uint32_t height,
        uint32_t channels
    ) {

    };

   
    std::vector<float> ReconstructChannel(
        const std::vector<std::vector<float>>& bands
    ) {

    };


    std::vector<uint8_t> EncodeLossy(
        const uint8_t* pixels,
        uint32_t width,
        uint32_t height,
        int quality = 5,
        const std::string& preset = "Balanced",
        uint32_t channels = 3,
        uint32_t bitDepth = 8
    ) {

    };

    std::vector<uint8_t> DecodeLossy(
        const std::vector<uint8_t>& data,
        uint32_t width,
        uint32_t height,
        uint32_t channels,
        uint32_t bitDepth = 8,
        int targetLayer = 2,
        int modeFlag = 9
    ) {
        
    };
}