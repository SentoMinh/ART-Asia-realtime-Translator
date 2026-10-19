// Host-test shim ONLY. Not copied into the WDK tree and never used in the driver.
#pragma once
#include <cstdint>
#include <cstring>
#include <mutex>
#include <algorithm>
using UCHAR = unsigned char;
using ULONG = uint32_t;
using ULONGLONG = uint64_t;
using KIRQL = unsigned char;
using KSPIN_LOCK = std::mutex;
constexpr ULONGLONG MAXULONGLONG = UINT64_MAX;
inline ULONGLONG testTime = 1;
inline void KeInitializeSpinLock(KSPIN_LOCK*) {}
inline void KeAcquireSpinLock(KSPIN_LOCK* lock, KIRQL* previous) { *previous = 0; lock->lock(); }
inline void KeReleaseSpinLock(KSPIN_LOCK* lock, KIRQL) { lock->unlock(); }
inline ULONGLONG KeQueryInterruptTime() { return testTime; }
inline void RtlCopyMemory(void* to, const void* from, size_t bytes) { std::memcpy(to, from, bytes); }
inline void RtlZeroMemory(void* to, size_t bytes) { std::memset(to, 0, bytes); }
using std::min;
