// Python bindings for the WIMF 3.0 (oxygen) container. Phase 1 surface:
// lossless encode/decode with Raw and Predictive-RC tiles plus structural
// inspection. Mirrors the v2 binding conventions (contiguous buffers,
// GIL released around codec work, ValueError on Status failures).
#include "v3_core.hpp"

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace py = pybind11;
using namespace pybind11::literals;
using namespace wimf::v3;

namespace {
bool is_c_contiguous(const py::buffer_info& view) {
    py::ssize_t expected = view.itemsize;
    for (py::ssize_t axis = view.ndim; axis-- > 0;) {
        if (view.shape[axis] > 1 && view.strides[axis] != expected) return false;
        expected *= view.shape[axis];
    }
    return true;
}
}  // namespace

PYBIND11_MODULE(wimf_v3_cpp, m) {
    m.doc() = "Portable native kernels for the WIMF v3 (oxygen) codec";
    m.def("encode_image",
          [](py::buffer value, uint32_t width, uint32_t height, uint8_t channels, uint16_t max_tile,
             uint8_t depth, py::bytes metadata) {
              auto view = value.request();
              const uint8_t bps = depth == 0 ? 1 : 2;
              const uint64_t byte_count = static_cast<uint64_t>(view.size) * view.itemsize;
              const uint64_t expected = static_cast<uint64_t>(width) * height * channels * bps;
              if (!is_c_contiguous(view) || byte_count != expected ||
                  (view.itemsize != 1 && view.itemsize != 2))
                  throw py::value_error("pixel buffer does not match image properties");
              std::string pixels(static_cast<const char*>(view.ptr), static_cast<size_t>(byte_count));
              ImageView image{reinterpret_cast<const uint8_t*>(pixels.data()), width, height,
                              channels, bps, static_cast<size_t>(width) * channels * bps};
              EncodeOptionsV3 options{};
              options.max_tile = max_tile;
              options.depth = depth;
              options.metadata = metadata.cast<std::string>();
              std::vector<uint8_t> output;
              wimf::v2::Status status;
              {
                  py::gil_scoped_release release;
                  status = encode_image(image, options, output);
              }
              if (!status) throw py::value_error(status.message);
              return py::bytes(reinterpret_cast<const char*>(output.data()), output.size());
          },
          "pixels"_a, "width"_a, "height"_a, "channels"_a, "max_tile"_a = 256, "depth"_a = 0,
          "metadata"_a = py::bytes());
    m.def("decode_image",
          [](py::buffer value, uint8_t target_planes) {
              auto view = value.request();
              if (view.ndim != 1 || view.itemsize != 1 || view.strides[0] != 1)
                  throw py::value_error("WIM3 data must be a contiguous byte buffer");
              std::string data(static_cast<const char*>(view.ptr), static_cast<size_t>(view.size));
              DecodeOptionsV3 options;
              options.target_planes = target_planes;
              DecodeResult output;
              wimf::v2::Status status;
              {
                  py::gil_scoped_release release;
                  status = decode_image(reinterpret_cast<const uint8_t*>(data.data()), data.size(),
                                        options, output);
              }
              if (!status) throw py::value_error(status.message);
              return py::dict(
                  "pixels"_a =
                      py::bytes(reinterpret_cast<const char*>(output.pixels.data()),
                                output.pixels.size()),
                  "width"_a = output.width, "height"_a = output.height,
                  "channels"_a = output.channels, "bit_depth"_a = output.bit_depth,
                  "metadata"_a = py::bytes(output.metadata));
          },
          "data"_a, "target_planes"_a = 255);
    m.def("parse_container",
          [](py::buffer value) {
              auto view = value.request();
              if (view.ndim != 1 || view.itemsize != 1 || view.strides[0] != 1)
                  throw py::value_error("WIM3 data must be a contiguous byte buffer");
              std::vector<const py::buffer_info*> unused;
              ContainerInfo info;
              try {
                  info = parse_container(reinterpret_cast<const uint8_t*>(view.ptr),
                                         static_cast<size_t>(view.size));
              } catch (const std::exception& error) {
                  throw py::value_error(error.what());
              }
              py::list tiles;
              for (const auto& tile : info.tiles)
                  tiles.append(py::dict("x"_a = tile.x, "y"_a = tile.y, "width"_a = tile.width,
                                        "height"_a = tile.height, "mode"_a = tile.mode,
                                        "entropy"_a = tile.entropy, "size"_a = tile.packed_size));
              return py::dict("width"_a = info.width, "height"_a = info.height,
                              "depth"_a = info.depth, "channels"_a = info.channels,
                              "max_tile"_a = info.max_tile,
                              "metadata"_a = py::bytes(info.metadata), "tiles"_a = tiles);
          },
          "data"_a);
}
