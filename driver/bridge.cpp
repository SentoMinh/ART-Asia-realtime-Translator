#include "bridge.h"

namespace {
// Both WaveRT pins negotiate 48 kHz, stereo, signed 16-bit PCM.
constexpr ULONG FrameBytes = 4;
constexpr ULONG Capacity = 48000 * FrameBytes / 10;
constexpr ULONGLONG StaleTime = 1000000; // 100 ms, in 100 ns units
struct Bank {
    KSPIN_LOCK lock;
    UCHAR samples[Capacity];
    ULONGLONG written;
    ULONGLONG floorPosition;
    ULONGLONG lastWrite;
};
// Never let the Windows 10 music input bypass the app's Start/Stop and gain controls.
Bank banks[2];
}

void VrctBridgeInitialize()
{
    for (auto& bank : banks) KeInitializeSpinLock(&bank.lock);
}

void VrctBridgeClear(bool musicInput)
{
    auto& [lock, samples, written, floorPosition, lastWrite] = banks[musicInput ? 1 : 0];
    KIRQL previous;
    KeAcquireSpinLock(&lock, &previous);
    floorPosition = written;
    lastWrite = 0;
    KeReleaseSpinLock(&lock, previous);
}

void VrctBridgeWrite(const UCHAR* source, ULONG bytes, bool musicInput)
{
    auto& [lock, samples, written, floorPosition, lastWrite] = banks[musicInput ? 1 : 0];
    bytes -= bytes % FrameBytes;
    if (!bytes) return;
    if (bytes > Capacity) {
        source += bytes - Capacity;
        bytes = Capacity;
    }
    KIRQL previous;
    KeAcquireSpinLock(&lock, &previous);
    const auto now = KeQueryInterruptTime();
    if (now - lastWrite > StaleTime) floorPosition = written;
    const ULONG offset = static_cast<ULONG>(written % Capacity);
    const ULONG first = min(bytes, Capacity - offset);
    RtlCopyMemory(samples + offset, source, first);
    RtlCopyMemory(samples, source + first, bytes - first);
    written += bytes;
    if (written - floorPosition > Capacity) floorPosition = written - Capacity;
    lastWrite = now;
    KeReleaseSpinLock(&lock, previous);
}

void VrctBridgeRead(UCHAR* destination, ULONG bytes, ULONGLONG* cursor, bool musicInput)
{
    auto& [lock, samples, written, floorPosition, lastWrite] = banks[musicInput ? 1 : 0];
    // Every capture stream has its own cursor; one reader cannot steal another's audio.
    RtlZeroMemory(destination, bytes);
    bytes -= bytes % FrameBytes;
    if (!bytes) return;
    KIRQL previous;
    KeAcquireSpinLock(&lock, &previous);
    if (!lastWrite || KeQueryInterruptTime() - lastWrite > StaleTime) {
        floorPosition = written;
        *cursor = written;
    }
    if (*cursor == MAXULONGLONG) {
        const ULONG available = static_cast<ULONG>(written - floorPosition);
        *cursor = written - min(bytes, available);
    }
    if (*cursor < floorPosition || *cursor > written) *cursor = floorPosition;
    const ULONG count = min(bytes, static_cast<ULONG>(written - *cursor));
    const ULONG offset = static_cast<ULONG>(*cursor % Capacity);
    const ULONG first = min(count, Capacity - offset);
    RtlCopyMemory(destination, samples + offset, first);
    RtlCopyMemory(destination + first, samples, count - first);
    *cursor += count;
    KeReleaseSpinLock(&lock, previous);
}
