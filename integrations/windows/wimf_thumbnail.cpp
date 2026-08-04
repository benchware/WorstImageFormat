#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <shobjidl.h>
#include <thumbcache.h>

#include <algorithm>
#include <atomic>
#include <new>
#include <vector>

#include "wimf_c.h"

namespace {
// {A11A6D5E-8D61-4AE5-8D44-64C66F7E6B4A}
const CLSID CLSID_WimfThumbnail = {0xa11a6d5e, 0x8d61, 0x4ae5,
                                  {0x8d, 0x44, 0x64, 0xc6, 0x6f, 0x7e, 0x6b, 0x4a}};
// {C747A1CC-95B3-49F0-A066-2D4E3DF98AA1}
const CLSID CLSID_WimfPreview = {0xc747a1cc, 0x95b3, 0x49f0,
                                {0xa0, 0x66, 0x2d, 0x4e, 0x3d, 0xf9, 0x8a, 0xa1}};
std::atomic<long> objects{0};

class Provider final : public IInitializeWithStream, public IThumbnailProvider {
public:
    Provider() { ++objects; }
    ~Provider() { if (stream_) stream_->Release(); --objects; }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID id, void** out) override {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (id == IID_IUnknown || id == IID_IInitializeWithStream)
            *out = static_cast<IInitializeWithStream*>(this);
        else if (id == IID_IThumbnailProvider)
            *out = static_cast<IThumbnailProvider*>(this);
        else return E_NOINTERFACE;
        AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++refs_; }
    ULONG STDMETHODCALLTYPE Release() override {
        const ULONG value = --refs_; if (!value) delete this; return value;
    }
    HRESULT STDMETHODCALLTYPE Initialize(IStream* stream, DWORD) override {
        if (!stream) return E_INVALIDARG;
        if (stream_) return HRESULT_FROM_WIN32(ERROR_ALREADY_INITIALIZED);
        stream_ = stream; stream_->AddRef(); return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetThumbnail(UINT edge, HBITMAP* bitmap, WTS_ALPHATYPE* alpha) override {
        if (!stream_ || !bitmap || !alpha || !edge) return E_INVALIDARG;
        *bitmap = nullptr; *alpha = WTSAT_UNKNOWN;
        STATSTG stat{};
        if (FAILED(stream_->Stat(&stat, STATFLAG_NONAME)) || stat.cbSize.QuadPart > 1024ull * 1024ull * 1024ull)
            return E_FAIL;
        LARGE_INTEGER zero{}; stream_->Seek(zero, STREAM_SEEK_SET, nullptr);
        std::vector<uint8_t> encoded(static_cast<size_t>(stat.cbSize.QuadPart));
        ULONG read = 0;
        if (FAILED(stream_->Read(encoded.data(), static_cast<ULONG>(encoded.size()), &read)) || read != encoded.size())
            return E_FAIL;
        wimf_decode_options options; wimf_decode_options_init(&options);
        options.max_output_bytes = 512ull * 1024ull * 1024ull;
        wimf_decoded_image image{};
        const wimf_status status = wimf_decode(encoded.data(), encoded.size(), &options, &image);
        if (status.code != WIMF_STATUS_OK) return E_FAIL;
        const double scale = std::min(1.0, static_cast<double>(edge) / std::max(image.width, image.height));
        const UINT width = std::max(1u, static_cast<UINT>(image.width * scale));
        const UINT height = std::max(1u, static_cast<UINT>(image.height * scale));
        BITMAPINFO info{}; info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
        info.bmiHeader.biWidth = static_cast<LONG>(width); info.bmiHeader.biHeight = -static_cast<LONG>(height);
        info.bmiHeader.biPlanes = 1; info.bmiHeader.biBitCount = 32; info.bmiHeader.biCompression = BI_RGB;
        void* pixels = nullptr;
        HBITMAP result = CreateDIBSection(nullptr, &info, DIB_RGB_COLORS, &pixels, nullptr, 0);
        if (!result) { wimf_decoded_image_free(&image); return E_OUTOFMEMORY; }
        const unsigned bytes = image.bit_depth == 8 ? 1 : 2;
        auto sample = [&](UINT x, UINT y, UINT channel) {
            const size_t offset = (static_cast<size_t>(y) * image.width * image.channels + x * image.channels + channel) * bytes;
            return bytes == 1 ? image.pixels.data[offset] : image.pixels.data[offset + 1];
        };
        auto* target = static_cast<uint8_t*>(pixels);
        for (UINT y = 0; y < height; ++y) for (UINT x = 0; x < width; ++x) {
            const UINT sx = std::min(image.width - 1, static_cast<UINT>(x / scale));
            const UINT sy = std::min(image.height - 1, static_cast<UINT>(y / scale));
            const uint8_t r = sample(sx, sy, 0);
            const uint8_t g = image.channels >= 3 ? sample(sx, sy, 1) : r;
            const uint8_t b = image.channels >= 3 ? sample(sx, sy, 2) : r;
            const uint8_t a = (image.channels == 2 || image.channels == 4) ? sample(sx, sy, image.channels - 1) : 255;
            const size_t out = (static_cast<size_t>(y) * width + x) * 4;
            target[out] = b; target[out + 1] = g; target[out + 2] = r; target[out + 3] = a;
        }
        const bool has_alpha = image.channels == 2 || image.channels == 4;
        wimf_decoded_image_free(&image);
        *bitmap = result; *alpha = has_alpha ? WTSAT_ARGB : WTSAT_RGB; return S_OK;
    }
private:
    std::atomic<ULONG> refs_{1}; IStream* stream_ = nullptr;
};

class Preview final : public IInitializeWithStream, public IPreviewHandler, public IOleWindow {
public:
    Preview() { ++objects; }
    ~Preview() { Unload(); if (stream_) stream_->Release(); --objects; }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID id, void** out) override {
        if (!out) return E_POINTER; *out = nullptr;
        if (id == IID_IUnknown || id == IID_IInitializeWithStream)
            *out = static_cast<IInitializeWithStream*>(this);
        else if (id == IID_IPreviewHandler) *out = static_cast<IPreviewHandler*>(this);
        else if (id == IID_IOleWindow) *out = static_cast<IOleWindow*>(this);
        else return E_NOINTERFACE;
        AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++refs_; }
    ULONG STDMETHODCALLTYPE Release() override { const ULONG value = --refs_; if (!value) delete this; return value; }
    HRESULT STDMETHODCALLTYPE Initialize(IStream* stream, DWORD) override {
        if (!stream) return E_INVALIDARG;
        if (stream_) return HRESULT_FROM_WIN32(ERROR_ALREADY_INITIALIZED);
        stream_ = stream; stream_->AddRef(); return S_OK;
    }
    HRESULT STDMETHODCALLTYPE SetWindow(HWND parent, const RECT* rect) override {
        if (!rect) return E_POINTER; parent_ = parent; rect_ = *rect; return S_OK;
    }
    HRESULT STDMETHODCALLTYPE SetRect(const RECT* rect) override {
        if (!rect) return E_POINTER; rect_ = *rect;
        if (window_) MoveWindow(window_, rect_.left, rect_.top, rect_.right - rect_.left, rect_.bottom - rect_.top, TRUE);
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE DoPreview() override {
        if (!stream_ || !parent_) return E_UNEXPECTED;
        auto* provider = new (std::nothrow) Provider();
        if (!provider) return E_OUTOFMEMORY;
        provider->Initialize(stream_, STGM_READ);
        const UINT edge = std::max(1L, std::max(rect_.right - rect_.left, rect_.bottom - rect_.top));
        WTS_ALPHATYPE alpha{};
        const HRESULT rendered = provider->GetThumbnail(edge, &bitmap_, &alpha);
        provider->Release();
        if (FAILED(rendered)) return rendered;
        window_ = CreateWindowExW(0, L"STATIC", nullptr, WS_CHILD | WS_VISIBLE | SS_BITMAP | SS_CENTERIMAGE,
                                  rect_.left, rect_.top, rect_.right - rect_.left, rect_.bottom - rect_.top,
                                  parent_, nullptr, GetModuleHandleW(nullptr), nullptr);
        if (!window_) { DeleteObject(bitmap_); bitmap_ = nullptr; return HRESULT_FROM_WIN32(GetLastError()); }
        SendMessageW(window_, STM_SETIMAGE, IMAGE_BITMAP, reinterpret_cast<LPARAM>(bitmap_));
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE Unload() override {
        if (window_) { DestroyWindow(window_); window_ = nullptr; }
        if (bitmap_) { DeleteObject(bitmap_); bitmap_ = nullptr; }
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE SetFocus() override { return window_ ? (::SetFocus(window_), S_OK) : S_FALSE; }
    HRESULT STDMETHODCALLTYPE QueryFocus(HWND* window) override {
        if (!window) return E_POINTER; *window = GetFocus(); return S_OK;
    }
    HRESULT STDMETHODCALLTYPE TranslateAccelerator(MSG*) override { return S_FALSE; }
    HRESULT STDMETHODCALLTYPE GetWindow(HWND* window) override {
        if (!window) return E_POINTER; *window = window_; return window_ ? S_OK : E_FAIL;
    }
    HRESULT STDMETHODCALLTYPE ContextSensitiveHelp(BOOL) override { return E_NOTIMPL; }
private:
    std::atomic<ULONG> refs_{1}; IStream* stream_ = nullptr; HWND parent_ = nullptr;
    HWND window_ = nullptr; HBITMAP bitmap_ = nullptr; RECT rect_{};
};

class Factory final : public IClassFactory {
public:
    explicit Factory(bool preview) : preview_(preview) {}
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID id, void** out) override {
        if (!out) return E_POINTER; *out = nullptr;
        if (id != IID_IUnknown && id != IID_IClassFactory) return E_NOINTERFACE;
        *out = this; AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++refs_; }
    ULONG STDMETHODCALLTYPE Release() override { const ULONG value = --refs_; if (!value) delete this; return value; }
    HRESULT STDMETHODCALLTYPE CreateInstance(IUnknown* outer, REFIID id, void** out) override {
        if (outer) return CLASS_E_NOAGGREGATION;
        IUnknown* object = preview_ ? static_cast<IUnknown*>(static_cast<IInitializeWithStream*>(new (std::nothrow) Preview()))
                                    : static_cast<IUnknown*>(static_cast<IInitializeWithStream*>(new (std::nothrow) Provider()));
        if (!object) return E_OUTOFMEMORY;
        const HRESULT result = object->QueryInterface(id, out); object->Release(); return result;
    }
    HRESULT STDMETHODCALLTYPE LockServer(BOOL lock) override { objects += lock ? 1 : -1; return S_OK; }
private:
    std::atomic<ULONG> refs_{1}; bool preview_;
};
}

STDAPI DllGetClassObject(REFCLSID clsid, REFIID id, void** out) {
    const bool preview = IsEqualCLSID(clsid, CLSID_WimfPreview);
    if (!preview && !IsEqualCLSID(clsid, CLSID_WimfThumbnail)) return CLASS_E_CLASSNOTAVAILABLE;
    auto* factory = new (std::nothrow) Factory(preview);
    if (!factory) return E_OUTOFMEMORY;
    const HRESULT result = factory->QueryInterface(id, out); factory->Release(); return result;
}
STDAPI DllCanUnloadNow() { return objects == 0 ? S_OK : S_FALSE; }
