#define NOMINMAX
#include <objbase.h>
#include <memory>
#include "transport.h"

namespace {
struct Producer {
    vrct::Mapping mapping;
    HANDLE mutex = nullptr;
    DWORD owner = GetCurrentThreadId();
    ~Producer() {
        if (mapping.get()) vrct::stop(*mapping.get());
        if (mutex) { ReleaseMutex(mutex); CloseHandle(mutex); }
    }
};
}
// The producer is called from one dedicated app worker thread, never an audio callback.
extern "C" __declspec(dllexport) void* __cdecl VrctOpen(const wchar_t* token, BOOL localTest) {
  try {
    auto producer = std::make_unique<Producer>();
    const auto name = vrct::mapping_name(token, localTest != FALSE);
    if (name.empty()) return nullptr;
    producer->mutex = CreateMutexW(nullptr, FALSE, (name + L".Writer").c_str());
    if (!producer->mutex) return nullptr;
    if (GetLastError() == ERROR_ALREADY_EXISTS) {
        CloseHandle(producer->mutex); producer->mutex = nullptr;
        return nullptr;
    }
    const DWORD wait = WaitForSingleObject(producer->mutex, 0);
    if (wait != WAIT_OBJECT_0 && wait != WAIT_ABANDONED) {
        CloseHandle(producer->mutex); producer->mutex = nullptr;
        return nullptr;
    }
    if (!producer->mapping.open(name)) return nullptr;
    vrct::begin(*producer->mapping.get());
    return producer.release();
  } catch (...) {
    // ctypes callers cannot handle a C++ exception across this C ABI.
    SetLastError(ERROR_NOT_ENOUGH_MEMORY);
    return nullptr;
  }
}
extern "C" __declspec(dllexport) BOOL __cdecl VrctWrite(void* handle, const float* samples, UINT32 frames) {
    auto* producer = static_cast<Producer*>(handle);
    if (!producer || producer->owner != GetCurrentThreadId() || !samples || frames > vrct::Capacity) return FALSE;
    vrct::write(*producer->mapping.get(), samples, frames, GetTickCount64());
    return TRUE;
}
extern "C" __declspec(dllexport) BOOL __cdecl VrctClose(void* handle) {
    auto* producer = static_cast<Producer*>(handle);
    if (!producer || producer->owner != GetCurrentThreadId()) return FALSE;
    delete producer;
    return TRUE;
}
// Readiness probe does not acquire the writer mutex or change music state.
extern "C" __declspec(dllexport) DWORD __cdecl VrctProbe(const wchar_t* token, BOOL localTest) {
    try {
        vrct::Mapping mapping;
        if (!mapping.open(vrct::mapping_name(token, localTest != FALSE))) return 0;
        const auto tick = mapping.get()->hostHeartbeat.load();
        const auto now = GetTickCount64();
        return tick && now >= tick && now - tick < 1000 ? 2 : 1;
    } catch (...) { return 0; }
}
