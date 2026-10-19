#pragma once
#define NOMINMAX
#include <windows.h>
#include <sddl.h>
#include <string>
#include <new>
#include "mixer.h"

namespace vrct {
inline std::wstring mapping_name(const wchar_t* token, bool local = false) {
    GUID id{};
    if (!token || FAILED(CLSIDFromString(token, &id))) return {};
    wchar_t canonical[40]{};
    StringFromGUID2(id, canonical, 40);
    return std::wstring(local ? L"Local\\VRCT.MicMusic." : L"Global\\VRCT.MicMusic.") + canonical;
}

class Mapping {
    HANDLE handle_ = nullptr;
    Shared* data_ = nullptr;
    bool pinned_ = false;
public:
    Mapping() = default;
    Mapping(const Mapping&) = delete;
    Mapping& operator=(const Mapping&) = delete;
    ~Mapping() { close(); }
    Shared* get() const { return data_; }
    void close() {
        if (pinned_) VirtualUnlock(data_, sizeof(Shared));
        if (data_) UnmapViewOfFile(data_);
        if (handle_) CloseHandle(handle_);
        handle_ = nullptr; data_ = nullptr; pinned_ = false;
    }
    bool create(const std::wstring& name, const wchar_t* writerSid) {
        close();
        PSID sid = nullptr;
        if (name.empty() || !writerSid || !ConvertStringSidToSidW(writerSid, &sid)) return false;
        LocalFree(sid);
        // Only the authorized Windows user and audio service identities can access it.
        const std::wstring sddl = L"D:P(A;;GA;;;SY)(A;;GA;;;LS)(A;;GA;;;" + std::wstring(writerSid) + L")";
        PSECURITY_DESCRIPTOR descriptor = nullptr;
        if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl.c_str(), SDDL_REVISION_1, &descriptor, nullptr)) return false;
        SECURITY_ATTRIBUTES security{sizeof(security), descriptor, FALSE};
        handle_ = CreateFileMappingW(INVALID_HANDLE_VALUE, &security, PAGE_READWRITE, 0, sizeof(Shared), name.c_str());
        const bool existed = GetLastError() == ERROR_ALREADY_EXISTS;
        LocalFree(descriptor);
        if (!handle_) return false;
        data_ = static_cast<Shared*>(MapViewOfFile(handle_, FILE_MAP_READ | FILE_MAP_WRITE, 0, 0, sizeof(Shared)));
        if (!data_) { close(); return false; }
        if (!existed) {
            new (data_) Shared{};
            data_->magic.store(Magic);
        }
        if (data_->magic.load() != Magic) { close(); return false; }
        pinned_ = VirtualLock(data_, sizeof(Shared)) != FALSE;
        // Never use pageable music storage in the audio callback.
        if (!pinned_) { close(); return false; }
        return true;
    }
    bool open(const std::wstring& name) {
        close();
        if (name.empty()) return false;
        handle_ = OpenFileMappingW(FILE_MAP_READ | FILE_MAP_WRITE, FALSE, name.c_str());
        if (!handle_) return false;
        data_ = static_cast<Shared*>(MapViewOfFile(handle_, FILE_MAP_READ | FILE_MAP_WRITE, 0, 0, sizeof(Shared)));
        if (!data_ || data_->magic.load() != Magic) { close(); return false; }
        return true;
    }
};
}
