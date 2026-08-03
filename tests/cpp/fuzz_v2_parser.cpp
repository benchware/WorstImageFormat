#include "v2_core.hpp"

#include <cstdint>
#include <iostream>
#include <random>
#include <vector>

int main() {
    wimf::v2::ContainerInfo source{};
    source.flags = 1;
    source.bit_depth = 8;
    source.channels = 3;
    source.width = 31;
    source.height = 29;
    source.tile_size = 128;
    source.metadata = "{\"format_version\":2}";
    wimf::v2::TileRecord tile{};
    tile.width = 31;
    tile.height = 29;
    tile.mode = 0;
    tile.entropy = 0;
    tile.layers = 1;
    tile.raw_size = 31 * 29 * 3;
    tile.payload.resize(tile.raw_size, 17);
    source.tiles.push_back(tile);

    const auto valid = wimf::v2::write_container(source);
    const auto parsed = wimf::v2::parse_container(valid.data(), valid.size());
    if (parsed.tiles.size() != 1) return 1;

    std::mt19937 generator(20260803);
    std::uniform_int_distribution<size_t> position(0, valid.size() - 1);
    std::uniform_int_distribution<int> value(1, 255);
    for (int iteration = 0; iteration < 20000; ++iteration) {
        auto mutated = valid;
        const int changes = 1 + iteration % 8;
        for (int change = 0; change < changes; ++change)
            mutated[position(generator)] ^= static_cast<uint8_t>(value(generator));
        try {
            (void)wimf::v2::parse_container(mutated.data(), mutated.size());
        } catch (const std::exception&) {
        }
    }
    for (size_t size = 0; size < valid.size(); ++size) {
        try {
            (void)wimf::v2::parse_container(valid.data(), size);
        } catch (const std::exception&) {
        }
    }
    std::cout << "WIM2 parser mutation smoke test passed.\n";
    return 0;
}
