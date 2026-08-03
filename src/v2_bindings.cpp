#include "v2_core.hpp"

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <cstring>
#include <atomic>
#include <memory>
#include <mutex>

#include "zstd.h"

namespace py = pybind11;
using namespace wimf::v2;
using namespace pybind11::literals;

namespace {
bool is_c_contiguous(const py::buffer_info& view) {
    py::ssize_t expected = view.itemsize;
    for (py::ssize_t axis = view.ndim; axis-- > 0;) {
        if (view.shape[axis] > 1 && view.strides[axis] != expected) return false;
        expected *= view.shape[axis];
    }
    return true;
}

struct PyOperationToken {
    std::atomic<bool> cancelled{false};
    std::atomic<uint64_t> completed{0};
    std::atomic<uint64_t> total{0};
    std::mutex mutex;
    std::string stage;
};

bool token_cancelled(void* context) noexcept {
    return static_cast<PyOperationToken*>(context)->cancelled.load();
}

void token_progress(void* context, const char* stage, uint64_t completed, uint64_t total) noexcept {
    auto* token = static_cast<PyOperationToken*>(context);
    try {
        std::lock_guard<std::mutex> lock(token->mutex);
        if (token->stage != stage) {
            token->stage = stage;
            token->completed.store(completed);
        } else {
            uint64_t current = token->completed.load();
            while (current < completed && !token->completed.compare_exchange_weak(current, completed)) {}
        }
        token->total.store(total);
    } catch (...) {}
}
}  // namespace

PYBIND11_MODULE(wimf_v2_cpp, m) {
    m.doc() = "Portable native kernels for the WIMF v2 codec";
    py::class_<PyOperationToken,std::shared_ptr<PyOperationToken>>(m,"OperationToken")
        .def(py::init<>())
        .def("cancel",[](PyOperationToken& token){token.cancelled.store(true);})
        .def("reset",[](PyOperationToken& token){token.cancelled.store(false);token.completed.store(0);token.total.store(0);std::lock_guard<std::mutex> lock(token.mutex);token.stage.clear();})
        .def_property_readonly("cancelled",[](const PyOperationToken& token){return token.cancelled.load();})
        .def_property_readonly("completed",[](const PyOperationToken& token){return token.completed.load();})
        .def_property_readonly("total",[](const PyOperationToken& token){return token.total.load();})
        .def_property_readonly("stage",[](PyOperationToken& token){std::lock_guard<std::mutex> lock(token.mutex);return token.stage;});
    m.def("runtime_info", [] { auto r=runtime_info(); return py::dict("architecture"_a=r.architecture,"simd"_a=r.simd,"hardware_threads"_a=r.hardware_threads,"codec_version"_a="2.1","native_orchestration"_a=true,"execution_policies"_a=py::make_tuple("synchronous","threaded"),"zstandard_version"_a=ZSTD_VERSION_STRING); });
    m.def("classify", [](py::buffer b,uint32_t w,uint32_t h,uint8_t ch,uint8_t bps){auto i=b.request();ImageView v{static_cast<const uint8_t*>(i.ptr),w,h,ch,bps,static_cast<size_t>(w)*ch*bps};py::gil_scoped_release release;return static_cast<uint8_t>(classify_tile(v));});
    m.def("encode_predictive", [](py::buffer b,uint32_t w,uint32_t h,uint8_t ch,uint8_t bps){auto i=b.request();ImageView v{static_cast<const uint8_t*>(i.ptr),w,h,ch,bps,static_cast<size_t>(w)*ch*bps};std::vector<uint8_t> out;{py::gil_scoped_release release;out=encode_predictive(v);}return py::bytes(reinterpret_cast<const char*>(out.data()),out.size());});
    m.def("decode_predictive", [](py::bytes b,uint32_t w,uint32_t h,uint8_t ch,uint8_t bps){std::string s=b;std::vector<uint8_t> out;{py::gil_scoped_release release;out=decode_predictive(reinterpret_cast<const uint8_t*>(s.data()),s.size(),w,h,ch,bps);}return py::bytes(reinterpret_cast<const char*>(out.data()),out.size());});
    m.def("encode_palette", [](py::buffer b,uint32_t w,uint32_t h,uint8_t ch,uint8_t bps){auto i=b.request();ImageView v{static_cast<const uint8_t*>(i.ptr),w,h,ch,bps,static_cast<size_t>(w)*ch*bps};std::vector<uint8_t> out;{py::gil_scoped_release release;out=encode_palette(v);}return py::bytes(reinterpret_cast<const char*>(out.data()),out.size());});
    m.def("decode_palette", [](py::bytes b,uint32_t w,uint32_t h,uint8_t ch,uint8_t bps){std::string s=b;std::vector<uint8_t> out;{py::gil_scoped_release release;out=decode_palette(reinterpret_cast<const uint8_t*>(s.data()),s.size(),w,h,ch,bps);}return py::bytes(reinterpret_cast<const char*>(out.data()),out.size());});
    m.def("wavelet_forward", [](py::buffer b,uint32_t w,uint32_t h,uint8_t bps,bool rev,unsigned levels,double q){auto i=b.request();std::vector<int64_t> out;{py::gil_scoped_release release;out=wavelet_forward(static_cast<const uint8_t*>(i.ptr),w,h,bps,rev,levels,q);}py::array_t<int64_t> result(out.size());std::memcpy(result.mutable_data(),out.data(),out.size()*sizeof(int64_t));return result;});
    m.def("wavelet_inverse", [](py::array_t<int64_t,py::array::c_style|py::array::forcecast> a,uint32_t w,uint32_t h,uint8_t bps,bool rev,unsigned levels,double q){auto i=a.request();std::vector<uint8_t> out;{py::gil_scoped_release release;out=wavelet_inverse(static_cast<const int64_t*>(i.ptr),i.size,w,h,bps,rev,levels,q);}return py::bytes(reinterpret_cast<const char*>(out.data()),out.size());});
    m.def("crc32", [](py::buffer b){auto i=b.request();py::gil_scoped_release release;return crc32(static_cast<const uint8_t*>(i.ptr),i.size);});
    m.def("write_container", [](uint8_t flags,uint8_t depth,uint8_t channels,uint32_t width,uint32_t height,uint16_t tile_size,py::bytes metadata,py::list tiles){ContainerInfo info{};info.flags=flags;info.bit_depth=depth;info.channels=channels;info.width=width;info.height=height;info.tile_size=tile_size;info.metadata=metadata.cast<std::string>();for(const auto& item:tiles){py::tuple t=py::cast<py::tuple>(item);if(t.size()!=9)throw std::invalid_argument("tile tuple must contain nine fields");TileRecord tile{};tile.x=t[0].cast<uint16_t>();tile.y=t[1].cast<uint16_t>();tile.width=t[2].cast<uint16_t>();tile.height=t[3].cast<uint16_t>();tile.mode=t[4].cast<uint8_t>();tile.entropy=t[5].cast<uint8_t>();tile.layers=t[6].cast<uint8_t>();tile.raw_size=t[7].cast<uint32_t>();std::string payload=t[8].cast<std::string>();tile.payload.assign(payload.begin(),payload.end());info.tiles.push_back(std::move(tile));}std::vector<uint8_t> out;{py::gil_scoped_release release;out=write_container(info);}return py::bytes(reinterpret_cast<const char*>(out.data()),out.size());});
    m.def("inspect_container", [](py::buffer value){auto view=value.request();if(view.ndim!=1||view.itemsize!=1||view.strides[0]!=1)throw py::value_error("WIM2 data must be a contiguous byte buffer");std::string data(static_cast<const char*>(view.ptr),static_cast<size_t>(view.size));ContainerInfo info;{py::gil_scoped_release release;info=parse_container(reinterpret_cast<const uint8_t*>(data.data()),data.size());}py::list tiles;for(const auto& tile:info.tiles)tiles.append(py::make_tuple(tile.x,tile.y,tile.width,tile.height,tile.mode,tile.entropy,tile.layers,0,tile.offset,tile.size,tile.raw_size,tile.checksum));return py::dict("flags"_a=info.flags,"bit_depth"_a=info.bit_depth,"channels"_a=info.channels,"width"_a=info.width,"height"_a=info.height,"tile_size"_a=info.tile_size,"metadata"_a=py::bytes(info.metadata),"entries"_a=tiles);});
    m.def("encode_image", [](py::buffer value,uint32_t width,uint32_t height,uint8_t channels,uint8_t bit_depth,uint8_t quality,bool lossless,const std::string& preset,const std::string& codec,uint16_t tile_size,unsigned threads,py::bytes metadata,bool synchronous,py::object token){auto view=value.request();if(view.ndim<1||!is_c_contiguous(view))throw py::value_error("pixels must be a contiguous buffer");const uint8_t bps=bit_depth==8?1:2;const uint64_t expected=static_cast<uint64_t>(width)*height*channels*bps;const uint64_t byte_count=static_cast<uint64_t>(view.size)*view.itemsize;if(byte_count!=expected)throw py::value_error("pixel buffer length does not match image properties");std::string pixels(static_cast<const char*>(view.ptr),static_cast<size_t>(byte_count));EncodeOptions options{};options.bit_depth=bit_depth;options.quality=quality;options.lossless=lossless;options.tile_size=tile_size;options.threads=threads;options.execution=synchronous?ExecutionPolicy::Synchronous:ExecutionPolicy::Threaded;options.metadata=metadata.cast<std::string>();std::shared_ptr<PyOperationToken> operation;OperationControl control{};if(!token.is_none()){operation=token.cast<std::shared_ptr<PyOperationToken>>();control={operation.get(),token_cancelled,token_progress};options.control=&control;}if(preset=="Fast")options.preset=SearchPreset::Fast;else if(preset=="Extreme")options.preset=SearchPreset::Extreme;else if(preset!="Balanced")throw py::value_error("unknown preset");if(codec=="raw")options.codec=CodecMode::Raw;else if(codec=="predictive")options.codec=CodecMode::Predictive;else if(codec=="palette")options.codec=CodecMode::Palette;else if(codec=="wavelet")options.codec=CodecMode::Wavelet;else if(codec!="auto")throw py::value_error("unknown codec");ImageView image{reinterpret_cast<const uint8_t*>(pixels.data()),width,height,channels,bps,static_cast<size_t>(width)*channels*bps};std::vector<uint8_t> output;CodecStats stats;Status status;{py::gil_scoped_release release;status=wimf::v2::encode_image(image,options,output,&stats);}if(!status)throw py::value_error(status.message);return py::make_tuple(py::bytes(reinterpret_cast<const char*>(output.data()),output.size()),py::dict("raw"_a=stats.raw_tiles,"predictive"_a=stats.predictive_tiles,"palette"_a=stats.palette_tiles,"wavelet"_a=stats.wavelet_tiles,"effective_threads"_a=stats.effective_threads));},"pixels"_a,"width"_a,"height"_a,"channels"_a,"bit_depth"_a,"quality"_a,"lossless"_a,"preset"_a,"codec"_a,"tile_size"_a,"threads"_a=0,"metadata"_a=py::bytes(),"synchronous"_a=false,"token"_a=py::none());
    m.def("decode_image", [](py::buffer value,py::object roi,uint8_t target_layer,unsigned threads,bool synchronous,py::object token){auto view=value.request();if(view.ndim!=1||view.itemsize!=1||view.strides[0]!=1)throw py::value_error("WIM2 data must be a contiguous byte buffer");std::string data(static_cast<const char*>(view.ptr),static_cast<size_t>(view.size));DecodeOptions options{};options.target_layer=target_layer;options.threads=threads;options.execution=synchronous?ExecutionPolicy::Synchronous:ExecutionPolicy::Threaded;std::shared_ptr<PyOperationToken> operation;OperationControl control{};if(!token.is_none()){operation=token.cast<std::shared_ptr<PyOperationToken>>();control={operation.get(),token_cancelled,token_progress};options.control=&control;}if(!roi.is_none()){py::tuple region=py::cast<py::tuple>(roi);if(region.size()!=4)throw py::value_error("ROI must contain four values");options.use_roi=true;options.roi_x=region[0].cast<uint32_t>();options.roi_y=region[1].cast<uint32_t>();options.roi_width=region[2].cast<uint32_t>();options.roi_height=region[3].cast<uint32_t>();}DecodeResult output;Status status;{py::gil_scoped_release release;status=wimf::v2::decode_image(reinterpret_cast<const uint8_t*>(data.data()),data.size(),options,output);}if(!status)throw py::value_error(status.message);return py::dict("pixels"_a=py::bytes(reinterpret_cast<const char*>(output.pixels.data()),output.pixels.size()),"width"_a=output.width,"height"_a=output.height,"channels"_a=output.channels,"bit_depth"_a=output.bit_depth,"metadata"_a=py::bytes(output.metadata),"stats"_a=py::dict("raw"_a=output.stats.raw_tiles,"predictive"_a=output.stats.predictive_tiles,"palette"_a=output.stats.palette_tiles,"wavelet"_a=output.stats.wavelet_tiles,"effective_threads"_a=output.stats.effective_threads));},"data"_a,"roi"_a=py::none(),"target_layer"_a=2,"threads"_a=0,"synchronous"_a=false,"token"_a=py::none());
    m.def("compare_images", [](py::buffer first,py::buffer second,uint32_t width,uint32_t height,uint8_t channels,uint8_t bit_depth){auto a=first.request(),b=second.request();const uint8_t bps=bit_depth==8?1:2;const uint64_t expected=static_cast<uint64_t>(width)*height*channels*bps;if(!is_c_contiguous(a)||!is_c_contiguous(b)||static_cast<uint64_t>(a.size)*a.itemsize!=expected||static_cast<uint64_t>(b.size)*b.itemsize!=expected)throw py::value_error("comparison buffers do not match image properties");std::string left(static_cast<const char*>(a.ptr),expected),right(static_cast<const char*>(b.ptr),expected);ImageView av{reinterpret_cast<const uint8_t*>(left.data()),width,height,channels,bps,static_cast<size_t>(width)*channels*bps},bv{reinterpret_cast<const uint8_t*>(right.data()),width,height,channels,bps,static_cast<size_t>(width)*channels*bps};CompareResult output;Status status;{py::gil_scoped_release release;status=wimf::v2::compare_images(av,bv,bit_depth,output);}if(!status)throw py::value_error(status.message);return py::dict("difference"_a=py::bytes(reinterpret_cast<const char*>(output.difference.data()),output.difference.size()),"mse"_a=output.mse,"maximum_error"_a=output.maximum_error,"psnr"_a=output.psnr);},"first"_a,"second"_a,"width"_a,"height"_a,"channels"_a,"bit_depth"_a);
    m.def("rewrite_metadata", [](py::buffer value,py::bytes metadata){auto view=value.request();if(view.ndim!=1||view.itemsize!=1||view.strides[0]!=1)throw py::value_error("WIM2 data must be a contiguous byte buffer");std::string data(static_cast<const char*>(view.ptr),static_cast<size_t>(view.size)),meta=metadata.cast<std::string>();std::vector<uint8_t> output;Status status;{py::gil_scoped_release release;status=wimf::v2::rewrite_metadata(reinterpret_cast<const uint8_t*>(data.data()),data.size(),meta,output);}if(!status)throw py::value_error(status.message);return py::bytes(reinterpret_cast<const char*>(output.data()),output.size());},"data"_a,"metadata"_a);
}
