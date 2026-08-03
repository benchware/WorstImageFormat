#include "v2_core.hpp"

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <cstring>

namespace py = pybind11;
using namespace wimf::v2;
using namespace pybind11::literals;

PYBIND11_MODULE(wimf_v2_cpp, m) {
    m.doc() = "Portable native kernels for the WIMF v2 codec";
    m.def("runtime_info", [] { auto r=runtime_info(); return py::dict("architecture"_a=r.architecture,"simd"_a=r.simd,"hardware_threads"_a=r.hardware_threads,"codec_version"_a="2.1"); });
    m.def("classify", [](py::buffer b,uint32_t w,uint32_t h,uint8_t ch,uint8_t bps){auto i=b.request();ImageView v{static_cast<const uint8_t*>(i.ptr),w,h,ch,bps,static_cast<size_t>(w)*ch*bps};py::gil_scoped_release release;return static_cast<uint8_t>(classify_tile(v));});
    m.def("encode_predictive", [](py::buffer b,uint32_t w,uint32_t h,uint8_t ch,uint8_t bps){auto i=b.request();ImageView v{static_cast<const uint8_t*>(i.ptr),w,h,ch,bps,static_cast<size_t>(w)*ch*bps};std::vector<uint8_t> out;{py::gil_scoped_release release;out=encode_predictive(v);}return py::bytes(reinterpret_cast<const char*>(out.data()),out.size());});
    m.def("decode_predictive", [](py::bytes b,uint32_t w,uint32_t h,uint8_t ch,uint8_t bps){std::string s=b;std::vector<uint8_t> out;{py::gil_scoped_release release;out=decode_predictive(reinterpret_cast<const uint8_t*>(s.data()),s.size(),w,h,ch,bps);}return py::bytes(reinterpret_cast<const char*>(out.data()),out.size());});
    m.def("encode_palette", [](py::buffer b,uint32_t w,uint32_t h,uint8_t ch,uint8_t bps){auto i=b.request();ImageView v{static_cast<const uint8_t*>(i.ptr),w,h,ch,bps,static_cast<size_t>(w)*ch*bps};std::vector<uint8_t> out;{py::gil_scoped_release release;out=encode_palette(v);}return py::bytes(reinterpret_cast<const char*>(out.data()),out.size());});
    m.def("decode_palette", [](py::bytes b,uint32_t w,uint32_t h,uint8_t ch,uint8_t bps){std::string s=b;std::vector<uint8_t> out;{py::gil_scoped_release release;out=decode_palette(reinterpret_cast<const uint8_t*>(s.data()),s.size(),w,h,ch,bps);}return py::bytes(reinterpret_cast<const char*>(out.data()),out.size());});
    m.def("wavelet_forward", [](py::buffer b,uint32_t w,uint32_t h,uint8_t bps,bool rev,unsigned levels,double q){auto i=b.request();std::vector<int64_t> out;{py::gil_scoped_release release;out=wavelet_forward(static_cast<const uint8_t*>(i.ptr),w,h,bps,rev,levels,q);}py::array_t<int64_t> result(out.size());std::memcpy(result.mutable_data(),out.data(),out.size()*sizeof(int64_t));return result;});
    m.def("wavelet_inverse", [](py::array_t<int64_t,py::array::c_style|py::array::forcecast> a,uint32_t w,uint32_t h,uint8_t bps,bool rev,unsigned levels,double q){auto i=a.request();std::vector<uint8_t> out;{py::gil_scoped_release release;out=wavelet_inverse(static_cast<const int64_t*>(i.ptr),i.size,w,h,bps,rev,levels,q);}return py::bytes(reinterpret_cast<const char*>(out.data()),out.size());});
    m.def("crc32", [](py::buffer b){auto i=b.request();py::gil_scoped_release release;return crc32(static_cast<const uint8_t*>(i.ptr),i.size);});
    m.def("write_container", [](uint8_t flags,uint8_t depth,uint8_t channels,uint32_t width,uint32_t height,uint16_t tile_size,py::bytes metadata,py::list tiles){ContainerInfo info{};info.flags=flags;info.bit_depth=depth;info.channels=channels;info.width=width;info.height=height;info.tile_size=tile_size;info.metadata=metadata.cast<std::string>();for(const auto& item:tiles){py::tuple t=py::cast<py::tuple>(item);if(t.size()!=9)throw std::invalid_argument("tile tuple must contain nine fields");TileRecord tile{};tile.x=t[0].cast<uint16_t>();tile.y=t[1].cast<uint16_t>();tile.width=t[2].cast<uint16_t>();tile.height=t[3].cast<uint16_t>();tile.mode=t[4].cast<uint8_t>();tile.entropy=t[5].cast<uint8_t>();tile.layers=t[6].cast<uint8_t>();tile.raw_size=t[7].cast<uint32_t>();std::string payload=t[8].cast<std::string>();tile.payload.assign(payload.begin(),payload.end());info.tiles.push_back(std::move(tile));}std::vector<uint8_t> out;{py::gil_scoped_release release;out=write_container(info);}return py::bytes(reinterpret_cast<const char*>(out.data()),out.size());});
    m.def("inspect_container", [](py::bytes value){std::string data=value;ContainerInfo info;{py::gil_scoped_release release;info=parse_container(reinterpret_cast<const uint8_t*>(data.data()),data.size());}py::list tiles;for(const auto& tile:info.tiles)tiles.append(py::make_tuple(tile.x,tile.y,tile.width,tile.height,tile.mode,tile.entropy,tile.layers,0,tile.offset,tile.size,tile.raw_size,tile.checksum));return py::dict("flags"_a=info.flags,"bit_depth"_a=info.bit_depth,"channels"_a=info.channels,"width"_a=info.width,"height"_a=info.height,"tile_size"_a=info.tile_size,"metadata"_a=py::bytes(info.metadata),"entries"_a=tiles);});
}
