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

// Tunable codec constants. The scoring divisor was retuned from 8.0 to 16.0
// after RD sweeps showed it adds intermediate lossy ladder steps with no
// quality regression. The ladder scale stays at the historical 1.5: the
// 2.5 experiment produced smaller files but visible chroma artifacts at
// medium quality (issue #44). The tuning workflow overrides these via -D
// flags to sweep candidate curves.
#ifndef WIMF_LADDER_SCALE
#define WIMF_LADDER_SCALE 1.5f
#endif
#ifndef WIMF_SCORING_DIVISOR
#define WIMF_SCORING_DIVISOR 16.0
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

// B1: lifting functions operate in-place on `line` using caller-provided
// scratch buffers. After the first call, resize() is a no-op, eliminating
// per-line heap allocations in the hot loop. Math is unchanged.
void lift97_forward(std::vector<double>& line,std::vector<double>& e,std::vector<double>& o){
    constexpr double a=-1.586134342, b=-0.05298011854, g=0.8829110762, d=0.4435068522, k=1.149604398;
    const size_t half=(line.size()+1)/2, odds=line.size()/2, om=odds?odds-1:0;
    e.resize(half); o.resize(odds?odds:1); if(!odds)o[0]=0;
    for(size_t i=0;i<half;++i)e[i]=line[i*2]; for(size_t i=0;i<odds;++i)o[i]=line[i*2+1];
    for(size_t i=0;i<odds;++i)o[i]+=a*(e[i]+e[std::min(i+1,half-1)]);
    for(size_t i=0;i<half;++i)e[i]+=b*(o[i?i-1:0]+o[std::min(i,om)]);
    for(size_t i=0;i<odds;++i)o[i]+=g*(e[i]+e[std::min(i+1,half-1)]);
    for(size_t i=0;i<half;++i)e[i]+=d*(o[i?i-1:0]+o[std::min(i,om)]);
    for(auto& x:e)x*=k; for(auto& x:o)x/=k;
    std::copy(e.begin(),e.end(),line.begin()); std::copy(o.begin(),o.end(),line.begin()+half);
}

void lift97_inverse(std::vector<double>& line,std::vector<double>& e,std::vector<double>& o){
    constexpr double a=-1.586134342, b=-0.05298011854, g=0.8829110762, d=0.4435068522, k=1.149604398;
    const size_t half=(line.size()+1)/2, odds=line.size()/2, om=odds?odds-1:0;
    e.resize(half); o.resize(odds?odds:1); if(!odds)o[0]=0;
    for(size_t i=0;i<half;++i)e[i]=line[i]; for(size_t i=0;i<odds;++i)o[i]=line[half+i];
    for(auto& x:e)x/=k; for(auto& x:o)x*=k;
    for(size_t i=0;i<half;++i)e[i]-=d*(o[i?i-1:0]+o[std::min(i,om)]);
    for(size_t i=0;i<odds;++i)o[i]-=g*(e[i]+e[std::min(i+1,half-1)]);
    for(size_t i=0;i<half;++i)e[i]-=b*(o[i?i-1:0]+o[std::min(i,om)]);
    for(size_t i=0;i<odds;++i)o[i]-=a*(e[i]+e[std::min(i+1,half-1)]);
    for(size_t i=0;i<half;++i)line[i*2]=e[i]; for(size_t i=0;i<odds;++i)line[i*2+1]=o[i];
}

void lift53_forward(std::vector<double>& line,std::vector<int64_t>& e,std::vector<int64_t>& o){
    const size_t half=(line.size()+1)/2, odds=line.size()/2, om=odds?odds-1:0;
    e.resize(half); o.resize(odds?odds:1); if(!odds)o[0]=0;
    for(size_t i=0;i<half;++i)e[i]=static_cast<int64_t>(line[i*2]); for(size_t i=0;i<odds;++i)o[i]=static_cast<int64_t>(line[i*2+1]);
    for(size_t i=0;i<odds;++i)o[i]-=floor_div(e[i]+e[std::min(i+1,half-1)],2);
    for(size_t i=0;i<half;++i)e[i]+=floor_div(o[i?i-1:0]+o[std::min(i,om)]+2,4);
    for(size_t i=0;i<half;++i)line[i]=static_cast<double>(e[i]); for(size_t i=0;i<odds;++i)line[half+i]=static_cast<double>(o[i]);
}

void lift53_inverse(std::vector<double>& line,std::vector<int64_t>& e,std::vector<int64_t>& o){
    const size_t half=(line.size()+1)/2, odds=line.size()/2, om=odds?odds-1:0;
    e.resize(half); o.resize(odds?odds:1); if(!odds)o[0]=0;
    for(size_t i=0;i<half;++i)e[i]=static_cast<int64_t>(line[i]); for(size_t i=0;i<odds;++i)o[i]=static_cast<int64_t>(line[half+i]);
    for(size_t i=0;i<half;++i)e[i]-=floor_div(o[i?i-1:0]+o[std::min(i,om)]+2,4);
    for(size_t i=0;i<odds;++i)o[i]+=floor_div(e[i]+e[std::min(i+1,half-1)],2);
    for(size_t i=0;i<half;++i)line[i*2]=static_cast<double>(e[i]); for(size_t i=0;i<odds;++i)line[i*2+1]=static_cast<double>(o[i]);
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
    // Scratch buffers are allocated once at the largest size; every later
    // resize shrinks within existing capacity, so the lifting loop performs
    // no per-line heap allocations. resize() always precedes the copy into
    // `line` - the original B1 attempt copied first and overflowed the
    // buffer whenever a later level's row width exceeded a shrunk size
    // (any non-square tile).
    std::vector<double> line,e97,o97;std::vector<int64_t> e53,o53;
    for(unsigned level=0;level<levels;++level){for(uint32_t y=0;y<rh;++y){line.resize(rw);std::copy(a.begin()+static_cast<size_t>(y)*w,a.begin()+static_cast<size_t>(y)*w+rw,line.begin());if(rev)lift53_forward(line,e53,o53);else lift97_forward(line,e97,o97);std::copy(line.begin(),line.begin()+rw,a.begin()+static_cast<size_t>(y)*w);}for(uint32_t x=0;x<rw;++x){line.resize(rh);for(uint32_t y=0;y<rh;++y)line[y]=a[static_cast<size_t>(y)*w+x];if(rev)lift53_forward(line,e53,o53);else lift97_forward(line,e97,o97);for(uint32_t y=0;y<rh;++y)a[static_cast<size_t>(y)*w+x]=line[y];}rw=(rw+1)/2;rh=(rh+1)/2;}
    std::vector<int64_t>out(a.size());for(size_t i=0;i<a.size();++i)out[i]=std::llround(a[i]/q);return out;
}

std::vector<uint8_t> wavelet_inverse(const int64_t* coeff,size_t count,uint32_t w,uint32_t h,uint8_t bps,bool rev,unsigned levels,double q){
    if(count!=static_cast<size_t>(w)*h)throw std::invalid_argument("invalid coefficient count");std::vector<double>a(count);for(size_t i=0;i<count;++i)a[i]=static_cast<double>(coeff[i])*q;
    std::vector<double> line,e97,o97;std::vector<int64_t> e53,o53;
    for(int level=static_cast<int>(levels)-1;level>=0;--level){const uint32_t rw=(w+(1u<<level)-1)>>level,rh=(h+(1u<<level)-1)>>level;for(uint32_t x=0;x<rw;++x){line.resize(rh);for(uint32_t y=0;y<rh;++y)line[y]=a[static_cast<size_t>(y)*w+x];if(rev)lift53_inverse(line,e53,o53);else lift97_inverse(line,e97,o97);for(uint32_t y=0;y<rh;++y)a[static_cast<size_t>(y)*w+x]=line[y];}for(uint32_t y=0;y<rh;++y){line.resize(rw);std::copy(a.begin()+static_cast<size_t>(y)*w,a.begin()+static_cast<size_t>(y)*w+rw,line.begin());if(rev)lift53_inverse(line,e53,o53);else lift97_inverse(line,e97,o97);std::copy(line.begin(),line.begin()+rw,a.begin()+static_cast<size_t>(y)*w);}}
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
        if(!tile.width||!tile.height||tile.mode>3||tile.entropy>2||tile.layers!=1||static_cast<uint32_t>(tile.x)+tile.width>out.width||static_cast<uint32_t>(tile.y)+tile.height>out.height||tile.x%out.tile_size||tile.y%out.tile_size||tile.width!=std::min<uint32_t>(out.tile_size,out.width-tile.x)||tile.height!=std::min<uint32_t>(out.tile_size,out.height-tile.y)||!seen.insert(key).second||tile.offset<data_start||tile.offset>size||tile.size>size-tile.offset||tile.raw_size>max_raw)throw std::runtime_error("invalid WIM2 tile entry");out.tiles.push_back(std::move(tile));}
    return out;
}

std::vector<uint8_t> write_container(const ContainerInfo& container){
    if(!container.width||!container.height||!container.channels||container.channels>16||(container.bit_depth!=8&&container.bit_depth!=10&&container.bit_depth!=16)||container.tile_size<16||container.tile_size>256||container.metadata.size()>16u*1024u*1024u||container.tiles.size()>16777216u)throw std::invalid_argument("invalid WIM2 container");
    const uint64_t header_size=kHeaderSize+container.metadata.size()+container.tiles.size()*kEntrySize;uint64_t total=header_size;for(const auto& tile:container.tiles){if(tile.payload.size()>std::numeric_limits<uint32_t>::max())throw std::overflow_error("tile payload too large");total+=tile.payload.size();}if(total>std::numeric_limits<size_t>::max())throw std::overflow_error("container too large");
    std::vector<uint8_t> out;out.reserve(static_cast<size_t>(total));out.insert(out.end(),{'W','I','M','2',2,container.flags,container.bit_depth,container.channels});put32(out,container.width);put32(out,container.height);put16(out,container.tile_size);put32(out,static_cast<uint32_t>(container.metadata.size()));put32(out,static_cast<uint32_t>(container.tiles.size()));out.insert(out.end(),container.metadata.begin(),container.metadata.end());
    uint64_t offset=header_size;for(const auto& tile:container.tiles){put16(out,tile.x);put16(out,tile.y);put16(out,tile.width);put16(out,tile.height);out.push_back(tile.mode);out.push_back(tile.entropy);out.push_back(tile.layers);out.push_back(0);put64(out,offset);put32(out,static_cast<uint32_t>(tile.payload.size()));put32(out,tile.raw_size);put32(out,crc32(tile.payload.data(),tile.payload.size()));offset+=tile.payload.size();}for(const auto& tile:container.tiles)out.insert(out.end(),tile.payload.begin(),tile.payload.end());return out;
}

namespace {

constexpr uint8_t kEntropyNone = 0, kEntropyZstd = 1, kEntropyRC = 2;

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
    // Deliberately leaked per-thread context: MinGW's emutls runs TLS
    // destructors during pthread key teardown, so a destroying thread_local
    // unique_ptr intermittently touches freed memory at worker-thread exit
    // (Dr.Mem: emutls_destroy -> ~unique_ptr, then heap corruption reports).
    // Contexts are bounded at one per thread; the OS reclaims them at exit.
    thread_local ZSTD_CCtx* context = ZSTD_createCCtx();
    if (!context) throw std::bad_alloc();
    std::vector<uint8_t> output(ZSTD_compressBound(input.size()));
    const size_t size = ZSTD_compressCCtx(context, output.data(), output.size(),
                                          input.data(), input.size(), level);
    if (ZSTD_isError(size)) throw std::runtime_error(ZSTD_getErrorName(size));
    output.resize(size);
    return output;
}

std::vector<uint8_t> decompress_zstd(const uint8_t* input, size_t size, size_t expected) {
    // See compress_zstd for why this context is intentionally not destroyed.
    thread_local ZSTD_DCtx* context = ZSTD_createDCtx();
    if (!context) throw std::bad_alloc();
    std::vector<uint8_t> output(expected);
    const size_t actual =
        ZSTD_decompressDCtx(context, output.data(), output.size(), input, size);
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

std::vector<int64_t> unpack_coefficients(const uint8_t* data, size_t size, size_t count) {
    std::vector<int64_t> output(count);
    size_t position = 0, index = 0;
    while (index < count) {
        if (position >= size) break; // stream ended, remaining coefficients are zero
        if (data[position++] != 0) throw std::runtime_error("invalid coefficient marker");
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

// Marker-free token layout (reversible flag value 2). Legacy packing spends a
// mandatory 0x00 marker byte on every run/value token, roughly a quarter of
// the packed lossy stream. V2 tokens are strict (run, zigzag) varint pairs;
// the reversible byte distinguishes the layouts and pre-v2.2 decoders reject
// the value cleanly.
std::vector<int64_t> unpack_coefficients_v2(const uint8_t* data, size_t size, size_t count) {
    std::vector<int64_t> output(count);
    size_t position = 0, index = 0;
    while (index < count) {
        if (position >= size) break; // stream ended, remaining coefficients are zero
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

// ---- A3 stage 2: adaptive binary range coder for wavelet coefficients ----
// Replaces varint+zstd with a single-pass context-modeled arithmetic coder.
// Structure adapted from LZMA's range coder (public domain) with adaptive
// 11-bit probability models (shift-5 counter update).

struct RangeEncoder {
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
        } else { ++cache_size; }
        low = (low & 0x00FFFFFF) << 8;
    }
    void encode(int bit, uint16_t prob) {
        const uint32_t bound = (range >> 11) * prob;
        if (!bit) { range = bound; } else { low += bound; range -= bound; }
        while (range < (1u << 24)) { shift_low(); range <<= 8; }
    }
    void flush() { for (int i = 0; i < 5; ++i) shift_low(); }
};

struct RangeDecoder {
    uint32_t range = 0xFFFFFFFFu;
    uint32_t code = 0;
    const uint8_t* data;
    size_t pos;
    // Hard ceiling on byte consumption. The encoder's five-byte flush makes
    // valid streams never reach it; hostile or desynced input does, turning
    // a silent out-of-bounds read into an exception.
    size_t limit = 0;
    RangeDecoder(const uint8_t* d, size_t offset) : data(d), pos(offset + 1) {
        for (int i = 0; i < 4; ++i) code = (code << 8) | data[pos++];
    }
    void set_limit(size_t bytes) { limit = bytes; }
    int decode(uint16_t prob) {
        const uint32_t bound = (range >> 11) * prob;
        int bit;
        if (code < bound) { range = bound; bit = 0; } else { code -= bound; range -= bound; bit = 1; }
        while (range < (1u << 24)) {
            if (limit != 0 && pos >= limit) throw std::runtime_error("range coder overread");
            code = (code << 8) | data[pos++];
            range <<= 8;
        }
        return bit;
    }
};

struct BitModel {
    uint16_t prob = 1024;
    void update(int bit) { if (bit) prob -= prob >> 5; else prob += (2048 - prob) >> 5; }
};

// Maximum subband contexts: LL plus HL/LH/HH for up to 8 wavelet levels.
constexpr unsigned kMaxRCBands = 25;

struct WaveletRCModels {
    BitModel is_zero[kMaxRCBands][2];
    BitModel is_gt[kMaxRCBands][8];
    BitModel sign;
};

void encode_coef_rc(RangeEncoder& re, WaveletRCModels& m, int& prev_zero, int64_t c, unsigned band) {
    const int is_zero = c == 0 ? 1 : 0;
    re.encode(is_zero, m.is_zero[band][prev_zero].prob);
    m.is_zero[band][prev_zero].update(is_zero);
    prev_zero = is_zero;
    if (is_zero) return;
    const uint64_t mag = c < 0 ? static_cast<uint64_t>(-c) : static_cast<uint64_t>(c);
    int level = 0;
    while (level < 8 && mag > ((uint64_t)1 << (level + 1)) - 1) {
        re.encode(1, m.is_gt[band][level].prob);
        m.is_gt[band][level].update(1);
        ++level;
    }
    if (level < 8) {
        re.encode(0, m.is_gt[band][level].prob);
        m.is_gt[band][level].update(0);
        for (int i = level - 1; i >= 0; --i)
            re.encode(static_cast<int>((mag >> i) & 1), 1024);
    } else {
        // level == 8: magnitude >= 256, code 16 raw bits for any value up to 65535
        for (int i = 15; i >= 0; --i)
            re.encode(static_cast<int>((mag >> i) & 1), 1024);
    }
    const int sign = c < 0 ? 1 : 0;
    re.encode(sign, m.sign.prob);
    m.sign.update(sign);
}

int64_t decode_coef_rc(RangeDecoder& rd, WaveletRCModels& m, int& prev_zero, unsigned band) {
    const int is_zero = rd.decode(m.is_zero[band][prev_zero].prob);
    m.is_zero[band][prev_zero].update(is_zero);
    prev_zero = is_zero;
    if (is_zero) return 0;
    int level = 0;
    while (level < 8) {
        const int b = rd.decode(m.is_gt[band][level].prob);
        m.is_gt[band][level].update(b);
        if (!b) break;
        ++level;
    }
    uint64_t mag;
    if (level < 8) {
        mag = (uint64_t)1 << level;
        for (int i = level - 1; i >= 0; --i)
            mag |= static_cast<uint64_t>(rd.decode(1024)) << i;
    } else {
        mag = 0;
        for (int i = 15; i >= 0; --i)
            mag |= static_cast<uint64_t>(rd.decode(1024)) << i;
    }
    const int sign = rd.decode(m.sign.prob);
    m.sign.update(sign);
    return sign ? -static_cast<int64_t>(mag) : static_cast<int64_t>(mag);
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

// Known-flaw A3, stage 1: subband-aware coefficient scanning. Reorders the
// raster-order DWT coefficients into dyadic subband sequence (LL, then
// HL/LH/HH per level, coarsest first) so quantized zeros and similar
// magnitudes cluster, producing longer zero-runs and flatter statistics for
// the entropy stage. Exactly invertible; padded dimensions are powers of two.
std::vector<int64_t> reorder_subbands(const std::vector<int64_t>& coefficients, uint32_t width,
                                      uint32_t height, unsigned levels) {
    std::vector<int64_t> ordered(coefficients.size());
    const uint32_t low_width = width >> levels, low_height = height >> levels;
    for (uint32_t y = 0; y < low_height; ++y)
        for (uint32_t x = 0; x < low_width; ++x)
            ordered[y * low_width + x] = coefficients[y * width + x];
    size_t position = static_cast<size_t>(low_width) * low_height;
    for (int level = static_cast<int>(levels); level >= 1; --level) {
        const uint32_t sw = width >> level, sh = height >> level;
        for (uint32_t y = 0; y < sh; ++y)
            for (uint32_t x = sw; x < 2 * sw; ++x)
                ordered[position++] = coefficients[y * width + x];
        for (uint32_t y = sh; y < 2 * sh; ++y)
            for (uint32_t x = 0; x < sw; ++x)
                ordered[position++] = coefficients[y * width + x];
        for (uint32_t y = sh; y < 2 * sh; ++y)
            for (uint32_t x = sw; x < 2 * sw; ++x)
                ordered[position++] = coefficients[y * width + x];
    }
    return ordered;
}

std::vector<int64_t> restore_raster_order(const std::vector<int64_t>& ordered, uint32_t width,
                                          uint32_t height, unsigned levels) {
    std::vector<int64_t> coefficients(ordered.size());
    const uint32_t low_width = width >> levels, low_height = height >> levels;
    for (uint32_t y = 0; y < low_height; ++y)
        for (uint32_t x = 0; x < low_width; ++x)
            coefficients[y * width + x] = ordered[y * low_width + x];
    size_t position = static_cast<size_t>(low_width) * low_height;
    for (int level = static_cast<int>(levels); level >= 1; --level) {
        const uint32_t sw = width >> level, sh = height >> level;
        for (uint32_t y = 0; y < sh; ++y)
            for (uint32_t x = sw; x < 2 * sw; ++x)
                coefficients[y * width + x] = ordered[position++];
        for (uint32_t y = sh; y < 2 * sh; ++y)
            for (uint32_t x = 0; x < sw; ++x)
                coefficients[y * width + x] = ordered[position++];
        for (uint32_t y = sh; y < 2 * sh; ++y)
            for (uint32_t x = sw; x < 2 * sw; ++x)
                coefficients[y * width + x] = ordered[position++];
    }
    return coefficients;
}

// Cumulative segment boundaries of the dyadic ordered stream: band b spans
// [starts[b], starts[b+1]). Band 0 is LL, then HL/LH/HH per level, coarsest
// first - mirrors reorder_subbands exactly.
std::vector<size_t> rc_band_starts(uint32_t width, uint32_t height, unsigned levels) {
    std::vector<size_t> starts;
    starts.reserve(2 + static_cast<size_t>(levels) * 3);
    starts.push_back(0);
    starts.push_back(static_cast<size_t>(width >> levels) * (height >> levels));
    for (unsigned level = levels; level >= 1; --level) {
        const size_t count = static_cast<size_t>(width >> level) * (height >> level);
        starts.push_back(starts.back() + count);
        starts.push_back(starts.back() + count);
        starts.push_back(starts.back() + count);
    }
    return starts;
}


std::vector<uint8_t> encode_wavelet_tile(const ImageView& tile, uint8_t quality, bool lossless,
                                         std::vector<uint8_t>* reconstructed,
                                         float quantizer_scale = 1.0f) {
    const uint32_t padded_height = next_power_of_two(tile.height), padded_width = next_power_of_two(tile.width);
    unsigned levels = 0;
    for (uint32_t value = std::min(padded_width, padded_height); value > 1 && levels < 3; value >>= 1) ++levels;
    const float base_q=std::max(1.0f,static_cast<float>((11-quality)*WIMF_LADDER_SCALE)*quantizer_scale);float quantizer=1.0f;
    if(!lossless){double energy=0;const uint32_t step=std::max(1u,std::min(tile.width,tile.height)/32u);for(uint32_t sy=0;sy<tile.height;sy+=step)for(uint32_t sx=0;sx<tile.width;sx+=step)for(uint8_t ch=0;ch<tile.channels;++ch){const double val=sample(tile,sx,sy,ch);if(sx>=step){double d=val-sample(tile,sx-step,sy,ch);energy+=d*d;}if(sy>=step){double d=val-sample(tile,sx,sy-step,ch);energy+=d*d;}}energy/=std::max(1.0,static_cast<double>(tile.width/step)*(tile.height/step)*tile.channels);quantizer=std::max(1.0f,base_q*std::clamp(static_cast<float>(std::sqrt(energy)/40.0),0.5f,2.0f));}
    std::vector<uint8_t> output;
    put16(output, static_cast<uint16_t>(padded_height));
    put16(output, static_cast<uint16_t>(padded_width));
    output.push_back(static_cast<uint8_t>(levels | 0x80));
    // reversible byte doubles as the coefficient-packing selector. Lossless
    // keeps the 2.2.4 single-context RC stream (flag 3): measured across the
    // bench corpus, splitting its near-uniform 5/3 coefficient statistics into
    // per-subband contexts costs ~0.5% to context fragmentation. Lossy uses
    // flag 6 with per-subband contexts: quantization makes band statistics
    // diverge sharply (large LL magnitudes, mostly-zero HH), worth ~0.5%.
    // Flags 4 (single-context lossy) and 0-2 (legacy varint) remain decodable.
    output.push_back(lossless ? 3 : 6);
    append_float(output, quantizer);
    if (reconstructed) reconstructed->assign(static_cast<size_t>(tile.width) * tile.height * tile.channels * tile.bytes_per_sample, 0);

    RangeEncoder re;
    WaveletRCModels models;
    // Segment layout must mirror the decoder's interpretation of the emitted
    // reversible flag exactly: flag 3 is one flat stream with a single
    // zero-run context, flag 6 walks dyadic subband segments.
    const size_t plane_coefficients = static_cast<size_t>(padded_width) * padded_height;
    const auto band_starts = lossless ? std::vector<size_t>{0, plane_coefficients}
                                      : rc_band_starts(padded_width, padded_height, levels);
    int prev_zero[kMaxRCBands];
    for (auto& value : prev_zero) value = 1;

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
        const auto ordered = reorder_subbands(coefficients, padded_width, padded_height, levels);
        size_t index = 0;
        for (unsigned band = 0; band + 1 < band_starts.size(); ++band)
            for (; index < band_starts[band + 1]; ++index)
                encode_coef_rc(re, models, prev_zero[band], ordered[index], band);
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
    re.flush();
    output.insert(output.end(), re.output.begin(), re.output.end());
    return output;
}

std::vector<uint8_t> decode_wavelet_tile(const uint8_t* data, size_t size, uint32_t width,
                                         uint32_t height, uint8_t channels, uint8_t bytes_per_sample) {
    if (size < 10) throw std::runtime_error("truncated wavelet tile");
    const uint32_t padded_height = read16(data), padded_width = read16(data + 2);
    const bool subband = (data[4] & 0x80) != 0;
    const uint8_t levels = data[4] & 0x7F, reversible = data[5];
    const float quantizer = read_float(data + 6);
    if (padded_width > 256 || padded_height > 256 || padded_width < width || padded_height < height ||
        levels > 8 || reversible > 6 || !std::isfinite(quantizer) || quantizer <= 0)
        throw std::runtime_error("invalid wavelet dimensions");
    size_t position = 10;
    std::vector<uint8_t> output(static_cast<size_t>(width) * height * channels * bytes_per_sample);
    // Lossless inverses: reversible 1 (legacy), 3 (single-context RC), 5 (banded RC).
    const bool lossless_inv = reversible == 1 || reversible == 3 || reversible == 5;
    if (reversible >= 3) {
        // A3 stage 2: range-coder unpacking, no per-channel size headers.
        // Reversible 5/6 code coefficients with per-subband contexts walked in
        // dyadic segment order; 3/4 keep the single-context stream of 2.2.4.
        if (size < 15) throw std::runtime_error("truncated wavelet RC stream");
        RangeDecoder rd(data, 10);
        rd.set_limit(size);
        WaveletRCModels models;
        const size_t coef_count = static_cast<size_t>(padded_width) * padded_height;
        const bool banded = reversible >= 5 && subband;
        const auto band_starts = banded ? rc_band_starts(padded_width, padded_height, levels)
                                        : std::vector<size_t>{0, coef_count};
        int prev_zero[kMaxRCBands];
        for (auto& value : prev_zero) value = 1;
        for (uint8_t channel = 0; channel < channels; ++channel) {
            std::vector<int64_t> ordered(coef_count);
            size_t index = 0;
            for (unsigned band = 0; band + 1 < band_starts.size(); ++band)
                for (; index < band_starts[band + 1]; ++index)
                    ordered[index] = decode_coef_rc(rd, models, prev_zero[band], band);
            auto coefficients = subband ? restore_raster_order(std::move(ordered), padded_width, padded_height, levels)
                                        : std::move(ordered);
            const auto plane = wavelet_inverse(coefficients.data(), coefficients.size(), padded_width,
                                               padded_height, bytes_per_sample, lossless_inv, levels, quantizer);
            for (uint32_t y = 0; y < height; ++y) for (uint32_t x = 0; x < width; ++x) {
                const size_t source = (static_cast<size_t>(y) * padded_width + x) * bytes_per_sample;
                const size_t target = (static_cast<size_t>(y) * width * channels + x * channels + channel) * bytes_per_sample;
                std::memcpy(output.data() + target, plane.data() + source, bytes_per_sample);
            }
        }
        return output;
    }
    for (uint8_t channel = 0; channel < channels; ++channel) {
        if (position + 4 > size) throw std::runtime_error("truncated wavelet channel");
        const uint32_t packed_size = read32(data + position);
        position += 4;
        if (packed_size > size - position) throw std::runtime_error("truncated wavelet coefficients");
        auto coefficients = reversible == 2 ? unpack_coefficients_v2(data + position, packed_size,
                                                                      static_cast<size_t>(padded_width) * padded_height)
                                            : unpack_coefficients(data + position, packed_size,
                                                                  static_cast<size_t>(padded_width) * padded_height);
        if (subband) coefficients = restore_raster_order(std::move(coefficients), padded_width, padded_height, levels);
        position += packed_size;
        const auto plane = wavelet_inverse(coefficients.data(), coefficients.size(), padded_width,
                                           padded_height, bytes_per_sample, lossless_inv, levels, quantizer);
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

// Exported wrappers over the internal subband reorder pair for the WIM3
// embedded wavelet tile mode; distinct names avoid shadowing the internals.

std::vector<int64_t> reorder_subbands_v2(const std::vector<int64_t>& coefficients, uint32_t width,
                                         uint32_t height, unsigned levels) {
    return reorder_subbands(coefficients, width, height, levels);
}

std::vector<int64_t> restore_raster_order_v2(const std::vector<int64_t>& ordered, uint32_t width,
                                             uint32_t height, unsigned levels) {
    return restore_raster_order(ordered, width, height, levels);
}

// Entropy-coded predictive residuals (tile entropy byte 2). The logical
// stream matches encode_predictive - predictor kind per channel-row, then
// wrapped residuals - but kinds ride two adaptive binary decisions and
// residuals are coded as signed values through the shared coefficient models,
// reusing the per-predictor context slot as the band index. Exported for the
// WIM3 container, which reuses this codec for its predictive tiles.

std::vector<uint8_t> encode_predictive_rc(const ImageView& v) {
    validate(v); const uint32_t mask=v.bytes_per_sample==1?0xFFu:0xFFFFu; const uint32_t mod=mask+1u; const int64_t modulus=static_cast<int64_t>(mask)+1;
    RangeEncoder re; WaveletRCModels models; BitModel kind_bit[2];
    int prev_zero[kMaxRCBands]; for(auto& value:prev_zero)value=1;
    std::vector<uint8_t> rbuf(v.bytes_per_sample==1?v.width:0u);
    for(uint8_t c=0;c<v.channels;++c)for(uint32_t y=0;y<v.height;++y){
        std::array<uint64_t,4> costs{};
        if(v.bytes_per_sample==1){const uint8_t* base=v.data+static_cast<size_t>(y)*v.row_stride+c;for(uint32_t x=0;x<v.width;++x)rbuf[x]=base[x*v.channels];costs[1]=simd::left_filter_cost(rbuf.data(),v.width);}
        for(uint32_t x=0;x<v.width;++x){const uint32_t cur=sample(v,x,y,c),l=x?sample(v,x-1,y,c):0,u=y?sample(v,x,y-1,c):0,ul=x&&y?sample(v,x-1,y-1,c):0;const uint32_t ps[4]={0,l,u,paeth(l,u,ul)};for(int k=0;k<4;++k){if(v.bytes_per_sample==1&&k==1)continue;uint32_t r=(cur-ps[k])&mask;costs[k]+=std::min(r,mod-r);}}
        const uint8_t kind=static_cast<uint8_t>(std::min_element(costs.begin(),costs.end())-costs.begin());
        re.encode(kind&1,kind_bit[0].prob);kind_bit[0].update(kind&1);
        re.encode((kind>>1)&1,kind_bit[1].prob);kind_bit[1].update((kind>>1)&1);
        for(uint32_t x=0;x<v.width;++x){const uint32_t cur=sample(v,x,y,c),l=x?sample(v,x-1,y,c):0,u=y?sample(v,x,y-1,c):0,ul=x&&y?sample(v,x-1,y-1,c):0,ps[4]={0,l,u,paeth(l,u,ul)};int64_t s=static_cast<int64_t>((cur-ps[kind])&mask);if(s>modulus/2)s-=modulus;encode_coef_rc(re,models,prev_zero[kind],s,kind);}
    }
    re.flush();
    return std::move(re.output);
}

std::vector<uint8_t> decode_predictive_rc(const uint8_t* data,size_t size,uint32_t w,uint32_t h,uint8_t ch,uint8_t bps){
    if(!data||size<5)throw std::runtime_error("truncated predictive RC stream");
    RangeDecoder rd(data,0); rd.set_limit(size); WaveletRCModels models; BitModel kind_bit[2];
    int prev_zero[kMaxRCBands]; for(auto& value:prev_zero)value=1;
    const uint32_t mask=bps==1?0xFFu:0xFFFFu; const int64_t modulus=static_cast<int64_t>(mask)+1;
    const size_t expected=static_cast<size_t>(ch)*h*(1+static_cast<size_t>(w)*bps);
    std::vector<uint8_t> out; out.reserve(expected);
    for(uint8_t c=0;c<ch;++c)for(uint32_t y=0;y<h;++y){
        const int k0=rd.decode(kind_bit[0].prob);kind_bit[0].update(k0);
        const int k1=rd.decode(kind_bit[1].prob);kind_bit[1].update(k1);
        const uint8_t kind=static_cast<uint8_t>(k0|(k1<<1)); out.push_back(kind);
        for(uint32_t x=0;x<w;++x){const int64_t s=decode_coef_rc(rd,models,prev_zero[kind],kind);append_sample(out,s<0?static_cast<uint32_t>(s+modulus):static_cast<uint32_t>(s),bps);}
    }
    if(rd.pos>size+8||out.size()!=expected)throw std::runtime_error("corrupt predictive RC stream");
    return out;
}

Status encode_image(const ImageView& image, const EncodeOptions& options,
                    std::vector<uint8_t>& encoded, CodecStats* stats) noexcept {
    try {        validate(image);
        if ((options.bit_depth != 8 && options.bit_depth != 10 && options.bit_depth != 16) ||
            (options.bit_depth == 8 ? 1 : 2) != image.bytes_per_sample || options.quality < 1 || options.quality > 10 ||
            options.tile_size < 16 || options.tile_size > 256 || image.width > 65535 || image.height > 65535 ||
            options.metadata.size() > 16u * 1024u * 1024u)
            throw std::invalid_argument("invalid encode options");
        // Known-flaw A2: reversible mod-256 green differencing for 8-bit
        // RGB/RGBA. Lossless ONLY: quantization errors in the residual
        // planes are amplified by the mod-256 undo in dark areas (issue
        // #44), producing chroma artifacts. Lossy tiles code raw RGB.
        constexpr bool kDecorrelateEnabled = true;
        std::vector<uint8_t> color_work;
        const bool color_decorrelated =
            kDecorrelateEnabled && options.lossless
                && (image.channels == 3 || image.channels == 4)
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
            uint8_t best_entropy = kEntropyZstd;
            bool best_is_rc = false;
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
            // Rate-distortion consideration for one candidate payload. The
            // wavelet path scores two quantizer sub-steps (scale 1.0 and 0.9):
            // the stored per-tile quantizer makes both decodable, and the 0.9
            // step fills the one-ladder-notch gap that showed up as the
            // 34-43 dB dead zone in the photo-pattern RD sweep.
            auto consider = [&](TileMode mode, std::vector<uint8_t> raw, const std::vector<uint8_t>* reconstructed,
                                bool rc_coded = false) {
                const bool already_coded = rc_coded || mode == TileMode::Raw || (raw.size() > 5 && raw[5] >= 3);
                auto payload = already_coded ? raw : compress_zstd(raw, scoring_preset);
                double distortion = 0;
                if (!options.lossless && mode == TileMode::Wavelet && reconstructed) {
                    for (size_t i = 0; i < pixels.size(); i += image.bytes_per_sample) {
                        const uint32_t a = image.bytes_per_sample == 1 ? pixels[i] : pixels[i] | static_cast<uint32_t>(pixels[i + 1]) << 8;
                        const uint32_t b = image.bytes_per_sample == 1 ? (*reconstructed)[i] : (*reconstructed)[i] | static_cast<uint32_t>((*reconstructed)[i + 1]) << 8;
                        const double delta = static_cast<double>(a) - b;
                        distortion += delta * delta;
                    }
                    distortion /= pixels.size() / image.bytes_per_sample;
                }
                const double score = options.lossless ? static_cast<double>(payload.size())
                    : payload.size() + distortion * (static_cast<double>(width) * height * image.channels) /
                      std::max(1.0, static_cast<double>((11 - options.quality) * (11 - options.quality))
                                        * WIMF_SCORING_DIVISOR);
                if (score < best_score || (score == best_score && payload.size() < best_size) ||
                    (score == best_score && payload.size() == best_size && static_cast<uint8_t>(mode) < static_cast<uint8_t>(best_mode))) {
                    best_score = score; best_size = payload.size(); best_mode = mode;
                    best_entropy = rc_coded ? kEntropyRC
                        : already_coded ? kEntropyNone : kEntropyZstd;
                    best_is_rc = rc_coded;
                    best_raw = std::move(raw); best_payload = std::move(payload);
                }
            };
            for (const TileMode mode : candidate_modes(tile, options)) {
                if (mode == TileMode::Raw) consider(mode, pixels, nullptr);
                else if (mode == TileMode::Predictive) {
                    consider(mode, encode_predictive(tile), nullptr);
                    // Same tile mode, competing entropy stage: whichever codes
                    // smaller wins the record. Legacy zstd wins exact ties.
                    consider(mode, encode_predictive_rc(tile), nullptr, true);
                }
                else if (mode == TileMode::Palette) {
                    std::vector<uint8_t> raw = encode_palette(tile);
                    if (!raw.empty()) consider(mode, std::move(raw), nullptr);
                } else {
                    // Lossless ignores the quantizer, so a single call suffices.
                    const float scales[] = {1.0f, 0.9f};
                    const int scale_count = options.lossless ? 1 : 2;
                    for (int s = 0; s < scale_count; ++s) {
                        std::vector<uint8_t> reconstructed;
                        std::vector<uint8_t> raw = encode_wavelet_tile(tile, options.quality, options.lossless,
                                                                       options.lossless ? nullptr : &reconstructed, scales[s]);
                        consider(mode, std::move(raw), options.lossless ? nullptr : &reconstructed);
                    }
                }
            }
            // Ship the winner at the full preset strength (see scoring_preset).
            // Range-coded tiles (wavelet RC or predictive RC) are already
            // compressed; skip zstd for them.
            if (!best_is_rc && best_mode != TileMode::Raw && !(best_raw.size() > 5 && best_raw[5] >= 3))
                best_payload = compress_zstd(best_raw, options.preset);
            else
                best_payload = best_raw;
            TileRecord record{};
            record.x = static_cast<uint16_t>(x); record.y = static_cast<uint16_t>(y);
            record.width = static_cast<uint16_t>(width); record.height = static_cast<uint16_t>(height);
            record.mode = static_cast<uint8_t>(best_mode);
            // RC-coded tiles (entropy already chosen during scoring) are
            // stored raw; everything else non-Raw ships zstd.
            record.entropy = best_entropy;
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
            std::vector<uint8_t> raw;
            if (tile.entropy == kEntropyNone) {
                raw.assign(packed, packed + tile.size);
            } else if (tile.entropy == kEntropyZstd) {
                raw = decompress_zstd(packed, tile.size, tile.raw_size);
            } else {
                // kEntropyRC: predictive residuals coded through the range
                // coder; the decoded bytes are the classic predictive payload.
                if (tile.mode != static_cast<uint8_t>(TileMode::Predictive))
                    throw std::runtime_error("RC entropy is only valid for predictive tiles");
                raw = decode_predictive_rc(packed, tile.size, tile.width, tile.height,
                                           container.channels, bytes_per_sample);
            }
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
