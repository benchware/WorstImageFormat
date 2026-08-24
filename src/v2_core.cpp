#include "v2_core.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <cstdlib>
#include <limits>
#include <memory>
#include <atomic>
#include <exception>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <unordered_map>
#include <unordered_set>

#include "zstd.h"
#include "v2_simd.hpp"

// Tunable codec constants (defaults reproduce the historical behavior exactly).
// The tuning workflow overrides these via -D flags to sweep candidate curves.
#ifndef WIMF_LADDER_SCALE
#define WIMF_LADDER_SCALE 1.5f
#endif
#ifndef WIMF_SCORING_DIVISOR
#define WIMF_SCORING_DIVISOR 8.0
#endif

namespace wimf::v2 {
namespace {

size_t checked_mul(size_t left, size_t right) {
    if (left != 0 && right > std::numeric_limits<size_t>::max() / left)
        throw std::overflow_error("image size overflow");
    return left * right;
}

uint32_t sample(const ImageView& v, uint32_t x, uint32_t y, uint8_t c) {
    const uint8_t* p = v.data + static_cast<size_t>(y) * v.row_stride +
                       (static_cast<size_t>(x) * v.channels + c) * v.bytes_per_sample;
    if (v.bytes_per_sample == 1) return *p;
    return static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8);
}

void append_sample(std::vector<uint8_t>& out, uint32_t value, uint8_t bytes) {
    out.push_back(static_cast<uint8_t>(value));
    if (bytes == 2) out.push_back(static_cast<uint8_t>(value >> 8));
}

uint32_t paeth(uint32_t a, uint32_t b, uint32_t c) {
    const int64_t p = static_cast<int64_t>(a) + b - c;
    const auto pa = std::llabs(p - a), pb = std::llabs(p - b), pc = std::llabs(p - c);
    return pa <= pb && pa <= pc ? a : (pb <= pc ? b : c);
}

void validate(const ImageView& v) {
    if (!v.data || !v.width || !v.height || !v.channels || v.channels > 16 ||
        (v.bytes_per_sample != 1 && v.bytes_per_sample != 2))
        throw std::invalid_argument("invalid image view");
    const size_t minimum = static_cast<size_t>(v.width) * v.channels * v.bytes_per_sample;
    if (v.row_stride < minimum) throw std::invalid_argument("row stride is too small");
}

int64_t floor_div(int64_t value, int64_t divisor) {
    const int64_t q = value / divisor, r = value % divisor;
    return q - (r != 0 && value < 0);
}

std::vector<double> lift97_forward(const std::vector<double>& line) {
    constexpr double a=-1.586134342, b=-0.05298011854, g=0.8829110762, d=0.4435068522, k=1.149604398;
    const size_t half=(line.size()+1)/2, odds=line.size()/2;
    std::vector<double> e(half), o(odds), out(line.size());
    for(size_t i=0;i<half;++i)e[i]=line[i*2]; for(size_t i=0;i<odds;++i)o[i]=line[i*2+1];
    for(size_t i=0;i<odds;++i)o[i]+=a*(e[i]+e[std::min(i+1,half-1)]);
    for(size_t i=0;i<half;++i)e[i]+=b*(o[i?i-1:0]+o[std::min(i,odds-1)]);
    for(size_t i=0;i<odds;++i)o[i]+=g*(e[i]+e[std::min(i+1,half-1)]);
    for(size_t i=0;i<half;++i)e[i]+=d*(o[i?i-1:0]+o[std::min(i,odds-1)]);
    for(auto& x:e)x*=k; for(auto& x:o)x/=k;
    std::copy(e.begin(),e.end(),out.begin()); std::copy(o.begin(),o.end(),out.begin()+half); return out;
}

std::vector<double> lift97_inverse(const std::vector<double>& line) {
    constexpr double a=-1.586134342, b=-0.05298011854, g=0.8829110762, d=0.4435068522, k=1.149604398;
    const size_t half=(line.size()+1)/2, odds=line.size()/2;
    std::vector<double> e(line.begin(),line.begin()+half),o(line.begin()+half,line.end()),out(line.size());
    for(auto& x:e)x/=k; for(auto& x:o)x*=k;
    for(size_t i=0;i<half;++i)e[i]-=d*(o[i?i-1:0]+o[std::min(i,odds-1)]);
    for(size_t i=0;i<odds;++i)o[i]-=g*(e[i]+e[std::min(i+1,half-1)]);
    for(size_t i=0;i<half;++i)e[i]-=b*(o[i?i-1:0]+o[std::min(i,odds-1)]);
    for(size_t i=0;i<odds;++i)o[i]-=a*(e[i]+e[std::min(i+1,half-1)]);
    for(size_t i=0;i<half;++i)out[i*2]=e[i]; for(size_t i=0;i<odds;++i)out[i*2+1]=o[i]; return out;
}

std::vector<double> lift53_forward(const std::vector<double>& line) {
    const size_t half=(line.size()+1)/2, odds=line.size()/2;
    std::vector<int64_t> e(half),o(odds); std::vector<double> out(line.size());
    for(size_t i=0;i<half;++i)e[i]=static_cast<int64_t>(line[i*2]); for(size_t i=0;i<odds;++i)o[i]=static_cast<int64_t>(line[i*2+1]);
    for(size_t i=0;i<odds;++i)o[i]-=floor_div(e[i]+e[std::min(i+1,half-1)],2);
    for(size_t i=0;i<half;++i)e[i]+=floor_div(o[i?i-1:0]+o[std::min(i,odds-1)]+2,4);
    for(size_t i=0;i<half;++i)out[i]=static_cast<double>(e[i]); for(size_t i=0;i<odds;++i)out[half+i]=static_cast<double>(o[i]); return out;
}

std::vector<double> lift53_inverse(const std::vector<double>& line) {
    const size_t half=(line.size()+1)/2, odds=line.size()/2;
    std::vector<int64_t> e(half),o(odds); std::vector<double> out(line.size());
    for(size_t i=0;i<half;++i)e[i]=static_cast<int64_t>(line[i]); for(size_t i=0;i<odds;++i)o[i]=static_cast<int64_t>(line[half+i]);
    for(size_t i=0;i<half;++i)e[i]-=floor_div(o[i?i-1:0]+o[std::min(i,odds-1)]+2,4);
    for(size_t i=0;i<odds;++i)o[i]+=floor_div(e[i]+e[std::min(i+1,half-1)],2);
    for(size_t i=0;i<half;++i)out[i*2]=static_cast<double>(e[i]); for(size_t i=0;i<odds;++i)out[i*2+1]=static_cast<double>(o[i]); return out;
}

}  // namespace

RuntimeInfo runtime_info() {
#if defined(__aarch64__) || defined(_M_ARM64)
    const char* arch="arm64"; const char* simd="neon";
#elif defined(__x86_64__) || defined(_M_X64)
    const char* arch="x86_64"; const char* simd=simd::has_avx2()?"avx2":"scalar";
#else
    const char* arch="unknown"; const char* simd="scalar";
#endif
#if defined(__EMSCRIPTEN__)
    return {arch,simd,1};
#else
    return {arch,simd,std::max(1u,std::thread::hardware_concurrency())};
#endif
}

TileMode classify_tile(const ImageView& v) {
    validate(v);std::unordered_map<std::string,uint8_t> colors;colors.reserve(257);
    long double sum=0,sum2=0,edge=0,cross=0,first2=0,second2=0,alpha_edge=0;size_t n=0;
    const uint32_t step=std::max(1u,std::min(v.width,v.height)/64u);const double scale=v.bytes_per_sample==1?1.0:1.0/257.0;
    for(uint32_t y=0;y<v.height;y+=step)for(uint32_t x=0;x<v.width;x+=step){
        std::string key(checked_mul(v.channels,v.bytes_per_sample),'\0');for(uint8_t c=0;c<v.channels;++c){const uint32_t s=sample(v,x,y,c);key[checked_mul(c,v.bytes_per_sample)]=static_cast<char>(s);if(v.bytes_per_sample==2)key[checked_mul(c,2)+1]=static_cast<char>(s>>8);}if(colors.size()<=256)colors.emplace(std::move(key),0);
        const double first=sample(v,x,y,0)*scale,second=sample(v,x,y,std::min<uint8_t>(1,v.channels-1))*scale,gray=(first+second+sample(v,x,y,std::min<uint8_t>(2,v.channels-1))*scale)/3.0;sum+=gray;sum2+=gray*gray;cross+=first*second;first2+=first*first;second2+=second*second;++n;
        if(x>=step){edge+=std::abs(gray-(sample(v,x-step,y,0)+sample(v,x-step,y,std::min<uint8_t>(1,v.channels-1))+sample(v,x-step,y,std::min<uint8_t>(2,v.channels-1)))*scale/3.0);if(v.channels==2||v.channels==4)alpha_edge+=std::abs(static_cast<int64_t>(sample(v,x,y,v.channels-1))-sample(v,x-step,y,v.channels-1))*scale;}
        if(y>=step)edge+=std::abs(gray-(sample(v,x,y-step,0)+sample(v,x,y-step,std::min<uint8_t>(1,v.channels-1))+sample(v,x,y-step,std::min<uint8_t>(2,v.channels-1)))*scale/3.0);
    }
    if(colors.size()<=256)return TileMode::Palette;const double mean=static_cast<double>(sum/n),variance=std::max(0.0,static_cast<double>(sum2/n)-mean*mean),gradient=static_cast<double>(edge/n),correlation=static_cast<double>(cross/std::sqrt(std::max<long double>(1.0,first2*second2)));
    if(alpha_edge/n>12.0||(gradient>28.0&&variance<5200.0))return TileMode::Predictive;return correlation>0.85&&gradient<30.0?TileMode::Wavelet:TileMode::Predictive;
}

std::vector<uint8_t> encode_predictive(const ImageView& v) {
    validate(v); const uint32_t mask=v.bytes_per_sample==1?0xFFu:0xFFFFu; const uint32_t mod=mask+1;
    std::vector<uint8_t> out; out.reserve(static_cast<size_t>(v.height)*(1+v.width*v.bytes_per_sample)*v.channels);
    std::vector<uint8_t> rbuf(v.bytes_per_sample==1?v.width:0u);
    for(uint8_t c=0;c<v.channels;++c)for(uint32_t y=0;y<v.height;++y){
        std::array<uint64_t,4> costs{};
        if(v.bytes_per_sample==1){const uint8_t* base=v.data+static_cast<size_t>(y)*v.row_stride+c;for(uint32_t x=0;x<v.width;++x)rbuf[x]=base[x*v.channels];costs[1]=simd::left_filter_cost(rbuf.data(),v.width);}
        for(uint32_t x=0;x<v.width;++x){const uint32_t cur=sample(v,x,y,c),l=x?sample(v,x-1,y,c):0,u=y?sample(v,x,y-1,c):0,ul=x&&y?sample(v,x-1,y-1,c):0; const uint32_t ps[4]={0,l,u,paeth(l,u,ul)}; for(int k=0;k<4;++k){if(v.bytes_per_sample==1&&k==1)continue;uint32_t r=(cur-ps[k])&mask; costs[k]+=std::min(r,mod-r);}}
        const uint8_t kind=static_cast<uint8_t>(std::min_element(costs.begin(),costs.end())-costs.begin()); out.push_back(kind);
        if(v.bytes_per_sample==1&&kind==1){const size_t pos=out.size();out.resize(pos+v.width);simd::left_filter_emit(rbuf.data(),out.data()+pos,v.width);}
        else{for(uint32_t x=0;x<v.width;++x){const uint32_t cur=sample(v,x,y,c),l=x?sample(v,x-1,y,c):0,u=y?sample(v,x,y-1,c):0,ul=x&&y?sample(v,x-1,y-1,c):0; const uint32_t ps[4]={0,l,u,paeth(l,u,ul)}; append_sample(out,(cur-ps[kind])&mask,v.bytes_per_sample);}}
    } return out;
}

std::vector<uint8_t> decode_predictive(const uint8_t* data,size_t size,uint32_t w,uint32_t h,uint8_t ch,uint8_t bps){
    const size_t expected=static_cast<size_t>(ch)*h*(1+static_cast<size_t>(w)*bps); if(size!=expected)throw std::runtime_error("invalid predictive payload");
    const uint32_t mask=bps==1?0xFFu:0xFFFFu; std::vector<uint8_t> out(static_cast<size_t>(w)*h*ch*bps); ImageView view{out.data(),w,h,ch,bps,static_cast<size_t>(w)*ch*bps}; size_t p=0;
    for(uint8_t c=0;c<ch;++c)for(uint32_t y=0;y<h;++y){const uint8_t kind=data[p++];if(kind>3)throw std::runtime_error("invalid predictor");for(uint32_t x=0;x<w;++x){uint32_t r=data[p++];if(bps==2)r|=static_cast<uint32_t>(data[p++])<<8;const uint32_t l=x?sample(view,x-1,y,c):0,u=y?sample(view,x,y-1,c):0,ul=x&&y?sample(view,x-1,y-1,c):0,ps[4]={0,l,u,paeth(l,u,ul)},value=(ps[kind]+r)&mask;uint8_t* dst=out.data()+(static_cast<size_t>(y)*w*ch+x*ch+c)*bps;dst[0]=static_cast<uint8_t>(value);if(bps==2)dst[1]=static_cast<uint8_t>(value>>8);}}
    return out;
}

std::vector<uint8_t> encode_palette(const ImageView& v){
    validate(v); const size_t pixel_bytes=v.channels*v.bytes_per_sample; std::unordered_map<std::string,uint16_t> map; std::vector<std::string> palette; std::vector<uint8_t> indices; indices.reserve(static_cast<size_t>(v.width)*v.height);
    for(uint32_t y=0;y<v.height;++y)for(uint32_t x=0;x<v.width;++x){std::string key(reinterpret_cast<const char*>(v.data+y*v.row_stride+x*pixel_bytes),pixel_bytes);auto [it,added]=map.emplace(key,static_cast<uint16_t>(palette.size()));if(added){if(palette.size()==256)return {};palette.push_back(key);}indices.push_back(static_cast<uint8_t>(it->second));}
    std::vector<uint8_t> out;out.push_back(static_cast<uint8_t>(palette.size()));out.push_back(static_cast<uint8_t>(palette.size()>>8));for(const auto& p:palette)out.insert(out.end(),p.begin(),p.end());out.insert(out.end(),indices.begin(),indices.end());return out;
}

std::vector<uint8_t> decode_palette(const uint8_t* data,size_t size,uint32_t w,uint32_t h,uint8_t ch,uint8_t bps){
    if(size<2)throw std::runtime_error("truncated palette");const uint16_t count=data[0]|static_cast<uint16_t>(data[1])<<8;if(!count||count>256)throw std::runtime_error("invalid palette");const size_t pb=ch*bps,head=2+count*pb,pixels=static_cast<size_t>(w)*h;if(size!=head+pixels)throw std::runtime_error("invalid palette payload");std::vector<uint8_t> out(pixels*pb);for(size_t i=0;i<pixels;++i){const uint8_t ix=data[head+i];if(ix>=count)throw std::runtime_error("palette index out of range");std::memcpy(out.data()+i*pb,data+2+ix*pb,pb);}return out;
}

std::vector<int64_t> wavelet_forward(const uint8_t* data,uint32_t w,uint32_t h,uint8_t bps,bool rev,unsigned levels,double q){
    if(!data||!w||!h||!q||levels>8)throw std::invalid_argument("invalid wavelet input");std::vector<double>a(static_cast<size_t>(w)*h);for(size_t i=0;i<a.size();++i)a[i]=bps==1?data[i]:data[i*2]|static_cast<uint16_t>(data[i*2+1])<<8;uint32_t rw=w,rh=h;
    for(unsigned level=0;level<levels;++level){for(uint32_t y=0;y<rh;++y){std::vector<double>line(a.begin()+y*w,a.begin()+y*w+rw);line=rev?lift53_forward(line):lift97_forward(line);std::copy(line.begin(),line.end(),a.begin()+y*w);}for(uint32_t x=0;x<rw;++x){std::vector<double>line(rh);for(uint32_t y=0;y<rh;++y)line[y]=a[y*w+x];line=rev?lift53_forward(line):lift97_forward(line);for(uint32_t y=0;y<rh;++y)a[y*w+x]=line[y];}rw=(rw+1)/2;rh=(rh+1)/2;}
    std::vector<int64_t>out(a.size());for(size_t i=0;i<a.size();++i)out[i]=std::llround(a[i]/q);return out;
}

std::vector<uint8_t> wavelet_inverse(const int64_t* coeff,size_t count,uint32_t w,uint32_t h,uint8_t bps,bool rev,unsigned levels,double q){
    if(count!=static_cast<size_t>(w)*h)throw std::invalid_argument("invalid coefficient count");std::vector<double>a(count);for(size_t i=0;i<count;++i)a[i]=static_cast<double>(coeff[i])*q;
    for(int level=static_cast<int>(levels)-1;level>=0;--level){const uint32_t rw=(w+(1u<<level)-1)>>level,rh=(h+(1u<<level)-1)>>level;for(uint32_t x=0;x<rw;++x){std::vector<double>line(rh);for(uint32_t y=0;y<rh;++y)line[y]=a[y*w+x];line=rev?lift53_inverse(line):lift97_inverse(line);for(uint32_t y=0;y<rh;++y)a[y*w+x]=line[y];}for(uint32_t y=0;y<rh;++y){std::vector<double>line(a.begin()+y*w,a.begin()+y*w+rw);line=rev?lift53_inverse(line):lift97_inverse(line);std::copy(line.begin(),line.end(),a.begin()+y*w);}}
    const uint32_t max=bps==1?255u:65535u;std::vector<uint8_t>out(count*bps);for(size_t i=0;i<count;++i){const uint32_t v=static_cast<uint32_t>(std::clamp<int64_t>(std::llround(a[i]),0,max));out[i*bps]=static_cast<uint8_t>(v);if(bps==2)out[i*bps+1]=static_cast<uint8_t>(v>>8);}return out;
}

uint32_t crc32(const uint8_t* data,size_t size){return simd::crc32(data,size);}

namespace {
constexpr size_t kHeaderSize = 26, kEntrySize = 32;
uint16_t read16(const uint8_t* p){return static_cast<uint16_t>(p[0])|static_cast<uint16_t>(p[1])<<8;}
uint32_t read32(const uint8_t* p){return static_cast<uint32_t>(p[0])|static_cast<uint32_t>(p[1])<<8|static_cast<uint32_t>(p[2])<<16|static_cast<uint32_t>(p[3])<<24;}
uint64_t read64(const uint8_t* p){uint64_t value=0;for(int i=7;i>=0;--i)value=(value<<8)|p[i];return value;}
void put16(std::vector<uint8_t>& out,uint16_t value){out.push_back(static_cast<uint8_t>(value));out.push_back(static_cast<uint8_t>(value>>8));}
void put32(std::vector<uint8_t>& out,uint32_t value){for(int i=0;i<4;++i)out.push_back(static_cast<uint8_t>(value>>(i*8)));}
void put64(std::vector<uint8_t>& out,uint64_t value){for(int i=0;i<8;++i)out.push_back(static_cast<uint8_t>(value>>(i*8)));}
}

ContainerInfo parse_container(const uint8_t* data,size_t size){
    if(!data||size<kHeaderSize||std::memcmp(data,"WIM2",4)!=0||data[4]!=2)throw std::runtime_error("not a supported WIM2 container");
    ContainerInfo out{};out.flags=data[5];out.bit_depth=data[6];out.channels=data[7];out.width=read32(data+8);out.height=read32(data+12);out.tile_size=read16(data+16);
    const uint32_t metadata_size=read32(data+18),count=read32(data+22);
    if(!out.width||!out.height||!out.channels||out.channels>16||(out.bit_depth!=8&&out.bit_depth!=10&&out.bit_depth!=16)||out.tile_size<16||out.tile_size>256||metadata_size>16u*1024u*1024u||count>16777216u)throw std::runtime_error("invalid WIM2 properties");
    const uint64_t index_start=kHeaderSize+metadata_size,data_start=index_start+static_cast<uint64_t>(count)*kEntrySize;
    if(data_start>size)throw std::runtime_error("truncated WIM2 index");out.metadata.assign(reinterpret_cast<const char*>(data+kHeaderSize),metadata_size);out.tiles.reserve(count);
    const uint64_t expected=(out.width+out.tile_size-1)/out.tile_size*static_cast<uint64_t>((out.height+out.tile_size-1)/out.tile_size);if(count!=expected)throw std::runtime_error("WIM2 tile count mismatch");
    std::unordered_set<uint64_t> seen;
    for(uint32_t i=0;i<count;++i){const uint8_t* p=data+index_start+static_cast<uint64_t>(i)*kEntrySize;TileRecord tile{};tile.x=read16(p);tile.y=read16(p+2);tile.width=read16(p+4);tile.height=read16(p+6);tile.mode=p[8];tile.entropy=p[9];tile.layers=p[10];tile.offset=read64(p+12);tile.size=read32(p+20);tile.raw_size=read32(p+24);tile.checksum=read32(p+28);const uint64_t key=static_cast<uint64_t>(tile.y)<<32|tile.x;const uint64_t max_raw=std::max<uint64_t>(1048576,static_cast<uint64_t>(tile.width)*tile.height*out.channels*std::max(2,out.bit_depth/8)*32);
        if(!tile.width||!tile.height||tile.mode>3||tile.entropy>1||tile.layers!=1||static_cast<uint32_t>(tile.x)+tile.width>out.width||static_cast<uint32_t>(tile.y)+tile.height>out.height||tile.x%out.tile_size||tile.y%out.tile_size||tile.width!=std::min<uint32_t>(out.tile_size,out.width-tile.x)||tile.height!=std::min<uint32_t>(out.tile_size,out.height-tile.y)||!seen.insert(key).second||tile.offset<data_start||tile.offset>size||tile.size>size-tile.offset||tile.raw_size>max_raw)throw std::runtime_error("invalid WIM2 tile entry");out.tiles.push_back(std::move(tile));}
    return out;
}

std::vector<uint8_t> write_container(const ContainerInfo& container){
    if(!container.width||!container.height||!container.channels||container.channels>16||(container.bit_depth!=8&&container.bit_depth!=10&&container.bit_depth!=16)||container.tile_size<16||container.tile_size>256||container.metadata.size()>16u*1024u*1024u||container.tiles.size()>16777216u)throw std::invalid_argument("invalid WIM2 container");
    const uint64_t header_size=kHeaderSize+container.metadata.size()+container.tiles.size()*kEntrySize;uint64_t total=header_size;for(const auto& tile:container.tiles){if(tile.payload.size()>std::numeric_limits<uint32_t>::max())throw std::overflow_error("tile payload too large");total+=tile.payload.size();}if(total>std::numeric_limits<size_t>::max())throw std::overflow_error("container too large");
    std::vector<uint8_t> out;out.reserve(static_cast<size_t>(total));out.insert(out.end(),{'W','I','M','2',2,container.flags,container.bit_depth,container.channels});put32(out,container.width);put32(out,container.height);put16(out,container.tile_size);put32(out,static_cast<uint32_t>(container.metadata.size()));put32(out,static_cast<uint32_t>(container.tiles.size()));out.insert(out.end(),container.metadata.begin(),container.metadata.end());
    uint64_t offset=header_size;for(const auto& tile:container.tiles){put16(out,tile.x);put16(out,tile.y);put16(out,tile.width);put16(out,tile.height);out.push_back(tile.mode);out.push_back(tile.entropy);out.push_back(tile.layers);out.push_back(0);put64(out,offset);put32(out,static_cast<uint32_t>(tile.payload.size()));put32(out,tile.raw_size);put32(out,crc32(tile.payload.data(),tile.payload.size()));offset+=tile.payload.size();}for(const auto& tile:container.tiles)out.insert(out.end(),tile.payload.begin(),tile.payload.end());return out;
}

namespace {

constexpr uint8_t kEntropyNone = 0, kEntropyZstd = 1;

class OperationCancelled final : public std::runtime_error {
public:
    OperationCancelled() : std::runtime_error("operation cancelled") {}
};

void check_cancelled(const OperationControl* control) {
    if (control && control->is_cancelled && control->is_cancelled(control->context)) throw OperationCancelled();
}

void report_progress(const OperationControl* control, const char* stage, uint64_t completed, uint64_t total) noexcept {
    if (control && control->on_progress) control->on_progress(control->context, stage, completed, total);
}

unsigned effective_threads(unsigned requested, ExecutionPolicy policy, size_t jobs) {
#if defined(__EMSCRIPTEN__)
    (void)requested;
    (void)policy;
    (void)jobs;
    return 1;
#else
    if (policy == ExecutionPolicy::Synchronous || jobs < 2) return 1;
    const unsigned available = std::max(1u, std::thread::hardware_concurrency());
    const unsigned wanted = requested ? requested : std::min(available, 8u);
    return std::max(1u, std::min<unsigned>(wanted, static_cast<unsigned>(jobs)));
#endif
}

template <class Function>
void parallel_for(size_t count, unsigned workers, Function function) {
    if (workers <= 1) {
        for (size_t i = 0; i < count; ++i) function(i);
        return;
    }
#if !defined(__EMSCRIPTEN__)
    std::atomic<size_t> next{0};
    std::mutex error_mutex;
    std::exception_ptr error;
    std::vector<std::thread> pool;
    pool.reserve(workers);
    for (unsigned worker = 0; worker < workers; ++worker) {
        pool.emplace_back([&] {
            try {
                while (true) {
                    const size_t i = next.fetch_add(1);
                    if (i >= count) break;
                    function(i);
                }
            } catch (...) {
                std::lock_guard<std::mutex> lock(error_mutex);
                if (!error) error = std::current_exception();
                next.store(count);
            }
        });
    }
    for (auto& thread : pool) thread.join();
    if (error) std::rethrow_exception(error);
#else
    for (size_t i = 0; i < count; ++i) function(i);
#endif
}

std::vector<uint8_t> compress_zstd(const std::vector<uint8_t>& input, SearchPreset preset) {
    const int level = preset == SearchPreset::Fast ? 3 : (preset == SearchPreset::Extreme ? 19 : 9);
    struct CctxCloser { void operator()(ZSTD_CCtx* context) const noexcept { ZSTD_freeCCtx(context); } };
    thread_local std::unique_ptr<ZSTD_CCtx, CctxCloser> context{ZSTD_createCCtx()};
    if (!context) throw std::bad_alloc();
    std::vector<uint8_t> output(ZSTD_compressBound(input.size()));
    const size_t size = ZSTD_compressCCtx(context.get(), output.data(), output.size(),
                                          input.data(), input.size(), level);
    if (ZSTD_isError(size)) throw std::runtime_error(ZSTD_getErrorName(size));
    output.resize(size);
    return output;
}

std::vector<uint8_t> decompress_zstd(const uint8_t* input, size_t size, size_t expected) {
    struct DctxCloser { void operator()(ZSTD_DCtx* context) const noexcept { ZSTD_freeDCtx(context); } };
    thread_local std::unique_ptr<ZSTD_DCtx, DctxCloser> context{ZSTD_createDCtx()};
    if (!context) throw std::bad_alloc();
    std::vector<uint8_t> output(expected);
    const size_t actual =
        ZSTD_decompressDCtx(context.get(), output.data(), output.size(), input, size);
    if (ZSTD_isError(actual) || actual != expected) throw std::runtime_error("invalid zstd tile payload");
    return output;
}

void append_float(std::vector<uint8_t>& output, float value) {
    uint32_t bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    put32(output, bits);
}

float read_float(const uint8_t* input) {
    const uint32_t bits = read32(input);
    float value = 0;
    std::memcpy(&value, &bits, sizeof(value));
    return value;
}

void append_varint(std::vector<uint8_t>& output, uint64_t value) {
    while (value >= 0x80) {
        output.push_back(static_cast<uint8_t>(value) | 0x80);
        value >>= 7;
    }
    output.push_back(static_cast<uint8_t>(value));
}

uint64_t read_varint(const uint8_t* data, size_t size, size_t& position) {
    uint64_t value = 0;
    for (unsigned shift = 0; shift < 70; shift += 7) {
        if (position >= size) throw std::runtime_error("truncated coefficient varint");
        const uint8_t byte = data[position++];
        value |= static_cast<uint64_t>(byte & 0x7f) << shift;
        if (byte < 0x80) return value;
    }
    throw std::runtime_error("oversized coefficient varint");
}

std::vector<uint8_t> pack_coefficients(const std::vector<int64_t>& coefficients) {
    std::vector<uint8_t> output;
    size_t run = 0;
    for (const int64_t value : coefficients) {
        if (value == 0) {
            ++run;
            continue;
        }
        output.push_back(0);
        append_varint(output, run);
        run = 0;
        const uint64_t zigzag = (static_cast<uint64_t>(value) << 1) ^ static_cast<uint64_t>(value >> 63);
        append_varint(output, zigzag);
    }
    if (run) {
        output.push_back(0);
        append_varint(output, run);
    }
    return output;
}

std::vector<int64_t> unpack_coefficients(const uint8_t* data, size_t size, size_t count) {
    std::vector<int64_t> output(count);
    size_t position = 0, index = 0;
    while (index < count) {
        if (position >= size || data[position++] != 0) throw std::runtime_error("invalid coefficient marker");
        const uint64_t run = read_varint(data, size, position);
        if (run > count - index) throw std::runtime_error("coefficient zero run exceeds tile");
        index += static_cast<size_t>(run);
        if (index == count) break;
        const uint64_t zigzag = read_varint(data, size, position);
        output[index++] = static_cast<int64_t>((zigzag >> 1) ^ (0 - (zigzag & 1)));
    }
    if (position != size) throw std::runtime_error("trailing coefficient data");
    return output;
}

uint32_t next_power_of_two(uint32_t value) {
    uint32_t output = 1;
    while (output < std::max(2u, value)) output <<= 1;
    return output;
}

uint32_t symmetric_index(uint32_t index, uint32_t length) {
    if (length == 1) return 0;
    const uint32_t period = length * 2;
    const uint32_t folded = index % period;
    return folded < length ? folded : period - folded - 1;
}

std::vector<uint8_t> encode_wavelet_tile(const ImageView& tile, uint8_t quality, bool lossless,
                                         std::vector<uint8_t>* reconstructed) {
    const uint32_t padded_height = next_power_of_two(tile.height), padded_width = next_power_of_two(tile.width);
    unsigned levels = 0;
    for (uint32_t value = std::min(padded_width, padded_height); value > 1 && levels < 3; value >>= 1) ++levels;
    const float base_q=std::max(1.0f,static_cast<float>((11-quality)*WIMF_LADDER_SCALE));float quantizer=1.0f;
    if(!lossless){double energy=0;const uint32_t step=std::max(1u,std::min(tile.width,tile.height)/32u);for(uint32_t sy=0;sy<tile.height;sy+=step)for(uint32_t sx=0;sx<tile.width;sx+=step)for(uint8_t ch=0;ch<tile.channels;++ch){const double val=sample(tile,sx,sy,ch);if(sx>=step){double d=val-sample(tile,sx-step,sy,ch);energy+=d*d;}if(sy>=step){double d=val-sample(tile,sx,sy-step,ch);energy+=d*d;}}energy/=std::max(1.0,static_cast<double>(tile.width/step)*(tile.height/step)*tile.channels);quantizer=std::max(1.0f,base_q*std::clamp(static_cast<float>(std::sqrt(energy)/40.0),0.5f,2.0f));}
    std::vector<uint8_t> output;
    put16(output, static_cast<uint16_t>(padded_height));
    put16(output, static_cast<uint16_t>(padded_width));
    output.push_back(static_cast<uint8_t>(levels));
    output.push_back(lossless ? 1 : 0);
    append_float(output, quantizer);
    if (reconstructed) reconstructed->assign(static_cast<size_t>(tile.width) * tile.height * tile.channels * tile.bytes_per_sample, 0);

    for (uint8_t channel = 0; channel < tile.channels; ++channel) {
        std::vector<uint8_t> plane(static_cast<size_t>(padded_width) * padded_height * tile.bytes_per_sample);
        for (uint32_t y = 0; y < padded_height; ++y) for (uint32_t x = 0; x < padded_width; ++x) {
            const uint32_t value = sample(tile, symmetric_index(x, tile.width), symmetric_index(y, tile.height), channel);
            const size_t position = (static_cast<size_t>(y) * padded_width + x) * tile.bytes_per_sample;
            plane[position] = static_cast<uint8_t>(value);
            if (tile.bytes_per_sample == 2) plane[position + 1] = static_cast<uint8_t>(value >> 8);
        }
        const auto coefficients = wavelet_forward(plane.data(), padded_width, padded_height,
                                                  tile.bytes_per_sample, lossless, levels, quantizer);
        const auto packed = pack_coefficients(coefficients);
        put32(output, static_cast<uint32_t>(packed.size()));
        output.insert(output.end(), packed.begin(), packed.end());
        if (reconstructed) {
            const auto decoded = wavelet_inverse(coefficients.data(), coefficients.size(), padded_width,
                                                 padded_height, tile.bytes_per_sample, lossless, levels, quantizer);
            for (uint32_t y = 0; y < tile.height; ++y) for (uint32_t x = 0; x < tile.width; ++x) {
                const size_t source = (static_cast<size_t>(y) * padded_width + x) * tile.bytes_per_sample;
                const size_t target = (static_cast<size_t>(y) * tile.width * tile.channels + x * tile.channels + channel) * tile.bytes_per_sample;
                std::memcpy(reconstructed->data() + target, decoded.data() + source, tile.bytes_per_sample);
            }
        }
    }
    return output;
}

std::vector<uint8_t> decode_wavelet_tile(const uint8_t* data, size_t size, uint32_t width,
                                         uint32_t height, uint8_t channels, uint8_t bytes_per_sample) {
    if (size < 10) throw std::runtime_error("truncated wavelet tile");
    const uint32_t padded_height = read16(data), padded_width = read16(data + 2);
    const uint8_t levels = data[4], reversible = data[5];
    const float quantizer = read_float(data + 6);
    if (padded_width > 256 || padded_height > 256 || padded_width < width || padded_height < height ||
        levels > 8 || reversible > 1 || !std::isfinite(quantizer) || quantizer <= 0)
        throw std::runtime_error("invalid wavelet dimensions");
    size_t position = 10;
    std::vector<uint8_t> output(static_cast<size_t>(width) * height * channels * bytes_per_sample);
    for (uint8_t channel = 0; channel < channels; ++channel) {
        if (position + 4 > size) throw std::runtime_error("truncated wavelet channel");
        const uint32_t packed_size = read32(data + position);
        position += 4;
        if (packed_size > size - position) throw std::runtime_error("truncated wavelet coefficients");
        const auto coefficients = unpack_coefficients(data + position, packed_size,
                                                      static_cast<size_t>(padded_width) * padded_height);
        position += packed_size;
        const auto plane = wavelet_inverse(coefficients.data(), coefficients.size(), padded_width,
                                           padded_height, bytes_per_sample, reversible != 0, levels, quantizer);
        for (uint32_t y = 0; y < height; ++y) for (uint32_t x = 0; x < width; ++x) {
            const size_t source = (static_cast<size_t>(y) * padded_width + x) * bytes_per_sample;
            const size_t target = (static_cast<size_t>(y) * width * channels + x * channels + channel) * bytes_per_sample;
            std::memcpy(output.data() + target, plane.data() + source, bytes_per_sample);
        }
    }
    if (position != size) throw std::runtime_error("trailing wavelet tile data");
    return output;
}

std::vector<uint8_t> copy_tile(const ImageView& image, uint32_t x, uint32_t y, uint32_t width, uint32_t height) {
    const size_t row_bytes = static_cast<size_t>(width) * image.channels * image.bytes_per_sample;
    std::vector<uint8_t> output(row_bytes * height);
    for (uint32_t row = 0; row < height; ++row)
        std::memcpy(output.data() + static_cast<size_t>(row) * row_bytes,
                    image.data + static_cast<size_t>(y + row) * image.row_stride +
                        static_cast<size_t>(x) * image.channels * image.bytes_per_sample,
                    row_bytes);
    return output;
}

std::vector<TileMode> candidate_modes(const ImageView& tile, const EncodeOptions& options) {
    if (options.codec != CodecMode::Auto) {
        TileMode forced = TileMode::Raw;
        if (options.codec == CodecMode::Predictive) forced = TileMode::Predictive;
        else if (options.codec == CodecMode::Palette) forced = TileMode::Palette;
        else if (options.codec == CodecMode::Wavelet) forced = TileMode::Wavelet;
        return forced == TileMode::Raw ? std::vector<TileMode>{TileMode::Raw}
                                       : std::vector<TileMode>{forced, TileMode::Raw};
    }
    const TileMode ranked = classify_tile(tile);
    if (options.preset == SearchPreset::Fast) return {ranked, TileMode::Raw};
    if (options.preset == SearchPreset::Extreme)
        return {TileMode::Palette, TileMode::Predictive, TileMode::Wavelet, TileMode::Raw};
    if (ranked == TileMode::Palette) return {TileMode::Palette, TileMode::Predictive, TileMode::Raw};
    if (ranked == TileMode::Predictive) return {TileMode::Predictive, TileMode::Wavelet, TileMode::Raw};
    return {TileMode::Wavelet, TileMode::Predictive, TileMode::Raw};
}

void count_mode(CodecStats& stats, uint8_t mode) {
    if (mode == static_cast<uint8_t>(TileMode::Raw)) ++stats.raw_tiles;
    else if (mode == static_cast<uint8_t>(TileMode::Predictive)) ++stats.predictive_tiles;
    else if (mode == static_cast<uint8_t>(TileMode::Palette)) ++stats.palette_tiles;
    else if (mode == static_cast<uint8_t>(TileMode::Wavelet)) ++stats.wavelet_tiles;
}

Status failure(ErrorCode code, const std::exception& error) { return {code, error.what()}; }

}  // namespace

Status encode_image(const ImageView& image, const EncodeOptions& options,
                    std::vector<uint8_t>& encoded, CodecStats* stats) noexcept {
    try {
        validate(image);
        if ((options.bit_depth != 8 && options.bit_depth != 10 && options.bit_depth != 16) ||
            (options.bit_depth == 8 ? 1 : 2) != image.bytes_per_sample || options.quality < 1 || options.quality > 10 ||
            options.tile_size < 16 || options.tile_size > 256 || image.width > 65535 || image.height > 65535 ||
            options.metadata.size() > 16u * 1024u * 1024u)
            throw std::invalid_argument("invalid encode options");
        // Known-flaw A2: channels were entropy-coded independently. Apply the
        // reversible mod-256 green differencing (G kept, R-G / B-G residual
        // planes) so chroma planes become near-flat and compress far better.
        // Pixel-wise and exactly invertible, so tiling/ROI/threading are
        // unaffected. Signaled by container flags bit 1.
        // Channel decorrelation (known-flaw A2): reversible mod-256 green
        // differencing, signaled by container flags bit 1 and mirrored by the
        // Python reference decoder.
        constexpr bool kDecorrelateEnabled = true;
        std::vector<uint8_t> color_work;
        const bool color_decorrelated =
            kDecorrelateEnabled && (image.channels == 3 || image.channels == 4)
                && image.bytes_per_sample == 1;
        if (color_decorrelated) {
            color_work.assign(image.data,
                              image.data + static_cast<size_t>(image.width) * image.height * image.channels);
            for (size_t i = 0; i < color_work.size(); i += image.channels) {
                const uint8_t green = color_work[i + 1];
                color_work[i] = static_cast<uint8_t>(color_work[i] - green);
                color_work[i + 2] = static_cast<uint8_t>(color_work[i + 2] - green);
            }
        }
        const ImageView source = color_decorrelated
            ? ImageView{color_work.data(), image.width, image.height, image.channels,
                        image.bytes_per_sample, image.row_stride}
            : image;
        const uint32_t columns = (image.width + options.tile_size - 1) / options.tile_size;
        const uint32_t rows = (image.height + options.tile_size - 1) / options.tile_size;
        const size_t count = static_cast<size_t>(columns) * rows;
        check_cancelled(options.control);
        report_progress(options.control, "encode", 0, count);
        ContainerInfo container{};
        container.flags = options.lossless ? 1 : 0;
        if (color_decorrelated) container.flags |= 0x2;
        container.bit_depth = options.bit_depth;
        container.channels = image.channels;
        container.width = image.width;
        container.height = image.height;
        container.tile_size = options.tile_size;
        container.metadata = options.metadata;
        container.tiles.resize(count);
        const unsigned workers = effective_threads(options.threads, options.execution, count);
        std::atomic<uint64_t> completed{0};
        parallel_for(count, workers, [&](size_t index) {
            check_cancelled(options.control);
            const uint32_t x = static_cast<uint32_t>(index % columns) * options.tile_size;
            const uint32_t y = static_cast<uint32_t>(index / columns) * options.tile_size;
            const uint32_t width = std::min<uint32_t>(options.tile_size, image.width - x);
            const uint32_t height = std::min<uint32_t>(options.tile_size, image.height - y);
            auto pixels = copy_tile(source, x, y, width, height);
            const ImageView tile{pixels.data(), width, height, source.channels, source.bytes_per_sample,
                                 static_cast<size_t>(width) * source.channels * source.bytes_per_sample};
            double best_score = std::numeric_limits<double>::infinity();
            size_t best_size = std::numeric_limits<size_t>::max();
            TileMode best_mode = TileMode::Raw;
            std::vector<uint8_t> best_raw, best_payload;
            // Known-flaw B2: scoring every candidate at Extreme's Zstandard level
            // 19 wastes most of the effort. Rank candidates with the cheaper
            // Balanced level, then ship the winner recompressed at full preset
            // strength. Selection stays deterministic; lossless and non-Extreme
            // paths are untouched.
            const SearchPreset scoring_preset =
                (!options.lossless && options.preset == SearchPreset::Extreme)
                    ? SearchPreset::Balanced
                    : options.preset;
            for (const TileMode mode : candidate_modes(tile, options)) {
                std::vector<uint8_t> raw, reconstructed;
                if (mode == TileMode::Raw) raw = pixels;
                else if (mode == TileMode::Predictive) raw = encode_predictive(tile);
                else if (mode == TileMode::Palette) {
                    raw = encode_palette(tile);
                    if (raw.empty()) continue;
                } else raw = encode_wavelet_tile(tile, options.quality, options.lossless,
                                                  options.lossless ? nullptr : &reconstructed);
                auto payload = mode == TileMode::Raw ? raw : compress_zstd(raw, scoring_preset);
                double distortion = 0;
                if (!options.lossless && mode == TileMode::Wavelet) {
                    for (size_t i = 0; i < pixels.size(); i += image.bytes_per_sample) {
                        const uint32_t a = image.bytes_per_sample == 1 ? pixels[i] : pixels[i] | static_cast<uint32_t>(pixels[i + 1]) << 8;
                        const uint32_t b = image.bytes_per_sample == 1 ? reconstructed[i] : reconstructed[i] | static_cast<uint32_t>(reconstructed[i + 1]) << 8;
                        const double delta = static_cast<double>(a) - b;
                        distortion += delta * delta;
                    }
                    distortion /= pixels.size() / image.bytes_per_sample;
                }
                const double score = options.lossless ? static_cast<double>(payload.size())
                    : payload.size() + distortion * (static_cast<double>(width) * height * image.channels) /
                      std::max(1.0, static_cast<double>(options.quality) * options.quality * WIMF_SCORING_DIVISOR);
                if (score < best_score || (score == best_score && payload.size() < best_size) ||
                    (score == best_score && payload.size() == best_size && static_cast<uint8_t>(mode) < static_cast<uint8_t>(best_mode))) {
                    best_score = score; best_size = payload.size(); best_mode = mode;
                    best_raw = std::move(raw); best_payload = std::move(payload);
                }
            }
            // Ship the winner at the full preset strength (see scoring_preset).
            if (best_mode != TileMode::Raw)
                best_payload = compress_zstd(best_raw, options.preset);
            else
                best_payload = best_raw;
            TileRecord record{};
            record.x = static_cast<uint16_t>(x); record.y = static_cast<uint16_t>(y);
            record.width = static_cast<uint16_t>(width); record.height = static_cast<uint16_t>(height);
            record.mode = static_cast<uint8_t>(best_mode);
            record.entropy = best_mode == TileMode::Raw ? kEntropyNone : kEntropyZstd;
            record.layers = 1; record.raw_size = static_cast<uint32_t>(best_raw.size());
            record.payload = std::move(best_payload);
            container.tiles[index] = std::move(record);
            report_progress(options.control, "encode", completed.fetch_add(1) + 1, count);
        });
        check_cancelled(options.control);
        report_progress(options.control, "container", count, count);
        encoded = write_container(container);
        if (stats) {
            *stats = {};
            stats->effective_threads = workers;
            for (const auto& tile : container.tiles) count_mode(*stats, tile.mode);
        }
        return {};
    } catch (const OperationCancelled& error) { return failure(ErrorCode::Cancelled, error); }
      catch (const std::invalid_argument& error) { return failure(ErrorCode::InvalidArgument, error); }
      catch (const std::bad_alloc& error) { return failure(ErrorCode::ResourceLimit, error); }
      catch (const std::exception& error) { return failure(ErrorCode::Internal, error); }
}

Status decode_image(const uint8_t* data, size_t size, const DecodeOptions& options,
                    DecodeResult& decoded) noexcept {
    try {
        const ContainerInfo container = parse_container(data, size);
        check_cancelled(options.control);
        const uint8_t bytes_per_sample = container.bit_depth == 8 ? 1 : 2;
        const uint32_t rx = options.use_roi ? options.roi_x : 0, ry = options.use_roi ? options.roi_y : 0;
        const uint32_t rw = options.use_roi ? options.roi_width : container.width;
        const uint32_t rh = options.use_roi ? options.roi_height : container.height;
        if (!rw || !rh || rx > container.width || ry > container.height || rw > container.width - rx || rh > container.height - ry)
            throw std::invalid_argument("ROI is outside image");
        const uint64_t output_size = static_cast<uint64_t>(rw) * rh * container.channels * bytes_per_sample;
        if (!options.max_output_bytes || output_size > options.max_output_bytes ||
            output_size > std::numeric_limits<size_t>::max())
            throw std::bad_alloc();
        decoded = {};
        decoded.width = rw; decoded.height = rh; decoded.channels = container.channels;
        decoded.bit_depth = container.bit_depth; decoded.metadata = container.metadata;
        decoded.pixels.assign(static_cast<size_t>(output_size), 0);
        std::vector<size_t> selected;
        for (size_t i = 0; i < container.tiles.size(); ++i) {
            const auto& tile = container.tiles[i];
            if (tile.x < rx + rw && tile.y < ry + rh && static_cast<uint32_t>(tile.x) + tile.width > rx &&
                static_cast<uint32_t>(tile.y) + tile.height > ry) selected.push_back(i);
        }
        const unsigned workers = effective_threads(options.threads, options.execution, selected.size());
        std::atomic<uint64_t> completed{0};
        report_progress(options.control, "decode", 0, selected.size());
        parallel_for(selected.size(), workers, [&](size_t selected_index) {
            check_cancelled(options.control);
            const auto& tile = container.tiles[selected[selected_index]];
            const uint8_t* packed = data + tile.offset;
            if (crc32(packed, tile.size) != tile.checksum) throw std::runtime_error("WIMF v2 tile checksum mismatch");
            std::vector<uint8_t> raw = tile.entropy == kEntropyNone
                ? std::vector<uint8_t>(packed, packed + tile.size)
                : decompress_zstd(packed, tile.size, tile.raw_size);
            std::vector<uint8_t> pixels;
            if (tile.mode == static_cast<uint8_t>(TileMode::Raw)) {
                const size_t expected = static_cast<size_t>(tile.width) * tile.height * container.channels * bytes_per_sample;
                if (raw.size() != expected) throw std::runtime_error("invalid raw tile length");
                pixels = std::move(raw);
            } else if (tile.mode == static_cast<uint8_t>(TileMode::Predictive))
                pixels = decode_predictive(raw.data(), raw.size(), tile.width, tile.height, container.channels, bytes_per_sample);
            else if (tile.mode == static_cast<uint8_t>(TileMode::Palette))
                pixels = decode_palette(raw.data(), raw.size(), tile.width, tile.height, container.channels, bytes_per_sample);
            else pixels = decode_wavelet_tile(raw.data(), raw.size(), tile.width, tile.height, container.channels, bytes_per_sample);
            const uint32_t x0 = std::max<uint32_t>(rx, tile.x), y0 = std::max<uint32_t>(ry, tile.y);
            const uint32_t x1 = std::min<uint32_t>(rx + rw, tile.x + tile.width), y1 = std::min<uint32_t>(ry + rh, tile.y + tile.height);
            const size_t pixel_bytes = static_cast<size_t>(container.channels) * bytes_per_sample;
            for (uint32_t y = y0; y < y1; ++y) {
                const size_t source = (static_cast<size_t>(y - tile.y) * tile.width + (x0 - tile.x)) * pixel_bytes;
                const size_t target = (static_cast<size_t>(y - ry) * rw + (x0 - rx)) * pixel_bytes;
                std::memcpy(decoded.pixels.data() + target, pixels.data() + source, static_cast<size_t>(x1 - x0) * pixel_bytes);
            }
            report_progress(options.control, "decode", completed.fetch_add(1) + 1, selected.size());
        });
        // Undo channel decorrelation when present (flags bit 1). Restricted to
        // 8-bit RGB/RGBA at encode time; stale bits on hostile input degrade
        // gracefully by skipping the pass.
        if ((container.flags & 0x2) != 0 && container.bit_depth == 8 && container.channels >= 3) {
            const size_t total = decoded.pixels.size();
            const uint8_t stride = container.channels;
            for (size_t i = 0; i < total; i += stride) {
                const uint8_t green = decoded.pixels[i + 1];
                decoded.pixels[i] = static_cast<uint8_t>(decoded.pixels[i] + green);
                decoded.pixels[i + 2] = static_cast<uint8_t>(decoded.pixels[i + 2] + green);
            }
        }
        decoded.stats.effective_threads = workers;
        for (const size_t index : selected) count_mode(decoded.stats, container.tiles[index].mode);
        return {};
    } catch (const OperationCancelled& error) { return failure(ErrorCode::Cancelled, error); }
      catch (const std::invalid_argument& error) { return failure(ErrorCode::InvalidArgument, error); }
      catch (const std::bad_alloc& error) { return failure(ErrorCode::ResourceLimit, error); }
      catch (const std::exception& error) { return failure(ErrorCode::CorruptData, error); }
}

Status compare_images(const ImageView& first, const ImageView& second, uint8_t bit_depth,
                      CompareResult& compared) noexcept {
    try {
        validate(first); validate(second);
        if (first.width != second.width || first.height != second.height || first.channels != second.channels ||
            first.bytes_per_sample != second.bytes_per_sample ||
            (bit_depth != 8 && bit_depth != 10 && bit_depth != 16) || (bit_depth == 8 ? 1 : 2) != first.bytes_per_sample)
            throw std::invalid_argument("images are not comparable");
        const uint64_t sample_count = static_cast<uint64_t>(first.width) * first.height * first.channels;
        if (sample_count > std::numeric_limits<size_t>::max() / first.bytes_per_sample) throw std::bad_alloc();
        compared = {};
        compared.difference.resize(static_cast<size_t>(sample_count) * first.bytes_per_sample);
        long double squared = 0;
        for (uint32_t y = 0; y < first.height; ++y) for (uint32_t x = 0; x < first.width; ++x)
            for (uint8_t channel = 0; channel < first.channels; ++channel) {
                const uint32_t a = sample(first, x, y, channel), b = sample(second, x, y, channel);
                const uint32_t delta = a > b ? a - b : b - a;
                compared.maximum_error = std::max(compared.maximum_error, delta);
                squared += static_cast<long double>(delta) * delta;
                const size_t index = (static_cast<size_t>(y) * first.width * first.channels +
                                      static_cast<size_t>(x) * first.channels + channel) * first.bytes_per_sample;
                compared.difference[index] = static_cast<uint8_t>(delta);
                if (first.bytes_per_sample == 2) compared.difference[index + 1] = static_cast<uint8_t>(delta >> 8);
            }
        compared.mse = static_cast<double>(squared / sample_count);
        const double peak = static_cast<double>((uint32_t{1} << bit_depth) - 1);
        compared.psnr = compared.mse == 0 ? std::numeric_limits<double>::infinity()
                                          : 10.0 * std::log10(peak * peak / compared.mse);
        return {};
    } catch (const std::invalid_argument& error) { return failure(ErrorCode::InvalidArgument, error); }
      catch (const std::bad_alloc& error) { return failure(ErrorCode::ResourceLimit, error); }
      catch (const std::exception& error) { return failure(ErrorCode::Internal, error); }
}

Status rewrite_metadata(const uint8_t* data, size_t size, const std::string& metadata,
                        std::vector<uint8_t>& rewritten) noexcept {
    try {
        if (metadata.size() > 16u * 1024u * 1024u) throw std::invalid_argument("metadata is too large");
        ContainerInfo container = parse_container(data, size);
        container.metadata = metadata;
        for (auto& tile : container.tiles)
            tile.payload.assign(data + tile.offset, data + tile.offset + tile.size);
        rewritten = write_container(container);
        return {};
    } catch (const std::invalid_argument& error) { return failure(ErrorCode::InvalidArgument, error); }
      catch (const std::bad_alloc& error) { return failure(ErrorCode::ResourceLimit, error); }
      catch (const std::exception& error) { return failure(ErrorCode::CorruptData, error); }
}

}  // namespace wimf::v2
