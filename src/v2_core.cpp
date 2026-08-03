#include "v2_core.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <cstdlib>
#include <limits>
#include <stdexcept>
#include <thread>
#include <unordered_map>

namespace wimf::v2 {
namespace {

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
    const char* arch="x86_64";
#if defined(__AVX2__)
    const char* simd="avx2";
#else
    const char* simd="scalar";
#endif
#else
    const char* arch="unknown"; const char* simd="scalar";
#endif
    return {arch,simd,std::max(1u,std::thread::hardware_concurrency())};
}

TileMode classify_tile(const ImageView& v) {
    validate(v); std::unordered_map<std::string,uint8_t> colors; colors.reserve(257);
    long double sum=0,sum2=0,edge=0; size_t n=0;
    const uint32_t step=std::max(1u,std::min(v.width,v.height)/64u);
    for(uint32_t y=0;y<v.height;y+=step)for(uint32_t x=0;x<v.width;x+=step){
        std::string key; key.resize(v.channels*v.bytes_per_sample);
        for(uint8_t c=0;c<v.channels;++c){const uint32_t s=sample(v,x,y,c); key[c*v.bytes_per_sample]=static_cast<char>(s); if(v.bytes_per_sample==2)key[c*2+1]=static_cast<char>(s>>8);}
        if(colors.size()<=256)colors.emplace(std::move(key),0);
        const double gray=sample(v,x,y,0); sum+=gray; sum2+=gray*gray; ++n;
        if(x>=step)edge+=std::abs(static_cast<int64_t>(sample(v,x,y,0))-sample(v,x-step,y,0));
    }
    if(colors.size()<=256)return TileMode::Palette;
    const double variance=static_cast<double>(sum2/n-(sum/n)*(sum/n));
    return edge/std::max<size_t>(1,n)>25.0&&variance<5000.0?TileMode::Predictive:TileMode::Wavelet;
}

std::vector<uint8_t> encode_predictive(const ImageView& v) {
    validate(v); const uint32_t modulus=v.bytes_per_sample==1?256u:65536u;
    std::vector<uint8_t> out; out.reserve(static_cast<size_t>(v.height)*(1+v.width*v.bytes_per_sample)*v.channels);
    for(uint8_t c=0;c<v.channels;++c)for(uint32_t y=0;y<v.height;++y){
        std::array<uint64_t,4> costs{};
        for(uint32_t x=0;x<v.width;++x){const uint32_t cur=sample(v,x,y,c),l=x?sample(v,x-1,y,c):0,u=y?sample(v,x,y-1,c):0,ul=x&&y?sample(v,x-1,y-1,c):0; const uint32_t ps[4]={0,l,u,paeth(l,u,ul)}; for(int k=0;k<4;++k){uint32_t r=(cur+modulus-ps[k])%modulus; costs[k]+=std::min(r,modulus-r);}}
        const uint8_t kind=static_cast<uint8_t>(std::min_element(costs.begin(),costs.end())-costs.begin()); out.push_back(kind);
        for(uint32_t x=0;x<v.width;++x){const uint32_t cur=sample(v,x,y,c),l=x?sample(v,x-1,y,c):0,u=y?sample(v,x,y-1,c):0,ul=x&&y?sample(v,x-1,y-1,c):0; const uint32_t ps[4]={0,l,u,paeth(l,u,ul)}; append_sample(out,(cur+modulus-ps[kind])%modulus,v.bytes_per_sample);}
    } return out;
}

std::vector<uint8_t> decode_predictive(const uint8_t* data,size_t size,uint32_t w,uint32_t h,uint8_t ch,uint8_t bps){
    const size_t expected=static_cast<size_t>(ch)*h*(1+static_cast<size_t>(w)*bps); if(size!=expected)throw std::runtime_error("invalid predictive payload");
    const uint32_t mod=bps==1?256u:65536u; std::vector<uint8_t> out(static_cast<size_t>(w)*h*ch*bps); ImageView view{out.data(),w,h,ch,bps,static_cast<size_t>(w)*ch*bps}; size_t p=0;
    for(uint8_t c=0;c<ch;++c)for(uint32_t y=0;y<h;++y){const uint8_t kind=data[p++];if(kind>3)throw std::runtime_error("invalid predictor");for(uint32_t x=0;x<w;++x){uint32_t r=data[p++];if(bps==2)r|=static_cast<uint32_t>(data[p++])<<8;const uint32_t l=x?sample(view,x-1,y,c):0,u=y?sample(view,x,y-1,c):0,ul=x&&y?sample(view,x-1,y-1,c):0,ps[4]={0,l,u,paeth(l,u,ul)},value=(ps[kind]+r)%mod;uint8_t* dst=out.data()+(static_cast<size_t>(y)*w*ch+x*ch+c)*bps;dst[0]=static_cast<uint8_t>(value);if(bps==2)dst[1]=static_cast<uint8_t>(value>>8);}}
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
    if(count!=static_cast<size_t>(w)*h)throw std::invalid_argument("invalid coefficient count");std::vector<double>a(coeff,coeff+count);for(auto&x:a)x*=q;
    for(int level=static_cast<int>(levels)-1;level>=0;--level){const uint32_t rw=(w+(1u<<level)-1)>>level,rh=(h+(1u<<level)-1)>>level;for(uint32_t x=0;x<rw;++x){std::vector<double>line(rh);for(uint32_t y=0;y<rh;++y)line[y]=a[y*w+x];line=rev?lift53_inverse(line):lift97_inverse(line);for(uint32_t y=0;y<rh;++y)a[y*w+x]=line[y];}for(uint32_t y=0;y<rh;++y){std::vector<double>line(a.begin()+y*w,a.begin()+y*w+rw);line=rev?lift53_inverse(line):lift97_inverse(line);std::copy(line.begin(),line.end(),a.begin()+y*w);}}
    const uint32_t max=bps==1?255u:65535u;std::vector<uint8_t>out(count*bps);for(size_t i=0;i<count;++i){const uint32_t v=static_cast<uint32_t>(std::clamp<int64_t>(std::llround(a[i]),0,max));out[i*bps]=static_cast<uint8_t>(v);if(bps==2)out[i*2+1]=static_cast<uint8_t>(v>>8);}return out;
}

uint32_t crc32(const uint8_t* data,size_t size){uint32_t crc=0xffffffffu;for(size_t i=0;i<size;++i){crc^=data[i];for(int k=0;k<8;++k)crc=(crc>>1)^(0xedb88320u&-(static_cast<int32_t>(crc&1)));}return ~crc;}

}  // namespace wimf::v2
