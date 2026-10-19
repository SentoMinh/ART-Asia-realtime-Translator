#pragma once
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <algorithm>

namespace vrct {
constexpr uint32_t Magic = 0x56524333;
constexpr uint32_t Capacity = 4800; // 100 ms, fixed 48 kHz stereo music transport.
constexpr uint64_t StaleMs = 150;
static_assert(std::atomic<uint64_t>::is_always_lock_free);
static_assert(std::atomic<uint32_t>::is_always_lock_free);

struct Frame { float left = 0, right = 0; };
struct Slot {
    std::atomic<uint64_t> sequence{0};
    std::atomic<uint64_t> sample{0};
};
struct Shared {
    std::atomic<uint32_t> magic{0};
    std::atomic<uint32_t> enabled{0};
    std::atomic<uint64_t> generation{0};
    std::atomic<uint64_t> written{0};
    std::atomic<uint64_t> heartbeat{0};
    std::atomic<uint64_t> hostHeartbeat{0};
    Slot slots[Capacity];
};

inline float clean(float value) noexcept {
    return std::isfinite(value) ? std::clamp(value, -1.0f, 1.0f) : 0.0f;
}

// A single producer is enforced by an OS mutex outside the real-time path.
inline void begin(Shared& shared) noexcept {
    shared.enabled.store(0);
    shared.generation.fetch_add(1);
    shared.written.store(0);
    shared.heartbeat.store(0);
}
inline void stop(Shared& shared) noexcept { shared.enabled.store(0); }
inline void write(Shared& shared, const float* samples, uint32_t frames, uint64_t now) noexcept {
    if (!frames) return;
    if (frames > Capacity) { samples += (frames - Capacity) * 2; frames = Capacity; }
    uint64_t position = shared.written.load();
    for (uint32_t i = 0; i < frames; ++i) {
        auto& slot = shared.slots[(position + i) % Capacity];
        // Invalidate before overwriting. Atomic samples avoid a C++ data race.
        slot.sequence.store(0);
        const Frame frame{clean(samples[i * 2]), clean(samples[i * 2 + 1])};
        uint64_t packed = 0;
        static_assert(sizeof(frame) == sizeof(packed));
        std::memcpy(&packed, &frame, sizeof(packed));
        slot.sample.store(packed);
        slot.sequence.store(position + i + 1);
    }
    shared.written.store(position + frames);
    shared.heartbeat.store(now);
    shared.enabled.store(1);
}

class Reader {
    uint64_t generation_ = UINT64_MAX, cursor_ = 0;
    double phase_ = 0;
    Frame current_{}, next_{};
    bool primed_ = false;

    bool pop(const Shared& shared, Frame& frame) noexcept {
        const auto written = shared.written.load();
        const auto floor = written > Capacity ? written - Capacity : 0;
        if (cursor_ < floor || cursor_ > written) cursor_ = floor;
        if (cursor_ == written) { frame = {}; return false; }
        const auto& slot = shared.slots[cursor_ % Capacity];
        const uint64_t expected = cursor_ + 1;
        const auto before = slot.sequence.load();
        const auto packed = slot.sample.load();
        const auto after = slot.sequence.load();
        ++cursor_;
        if (before != expected || after != expected) { frame = {}; return false; }
        std::memcpy(&frame, &packed, sizeof(frame));
        frame.left = clean(frame.left);
        frame.right = clean(frame.right);
        return true;
    }
public:
    void reset() noexcept { generation_ = UINT64_MAX; primed_ = false; phase_ = 0; }
    bool mix(const Shared* shared, const float* voice, float* output, uint32_t frames,
             uint32_t channels, double rate, bool voiceSilent, uint64_t now) noexcept {
        const auto count = static_cast<size_t>(frames) * channels;
        if (voiceSilent) std::fill_n(output, count, 0.0f);
        else if (voice != output) std::memcpy(output, voice, count * sizeof(float));
        if (!shared || channels < 1 || channels > 2 || !std::isfinite(rate) || rate < 8000 || rate > 192000)
            return false; // Unsupported music format passes microphone through unchanged.
        const auto heartbeat = shared->heartbeat.load();
        if (shared->magic.load() != Magic || !shared->enabled.load() || now < heartbeat || now - heartbeat > StaleMs) {
            cursor_ = shared->written.load();
            primed_ = false;
            phase_ = 0;
            return false;
        }
        const auto generation = shared->generation.load();
        if (generation != generation_) {
            generation_ = generation;
            const auto end = shared->written.load();
            const auto wanted = std::min<uint64_t>(Capacity, static_cast<uint64_t>(frames * 48000.0 / rate) + 2);
            cursor_ = end > wanted ? end - wanted : 0;
            primed_ = false;
            phase_ = 0;
        }
        bool audible = false;
        for (uint32_t frame = 0; frame < frames; ++frame) {
            // Stop/generation changes never replay a previous writer's samples.
            if (!shared->enabled.load() || shared->generation.load() != generation_) { primed_ = false; break; }
            if (!primed_) {
                if (!pop(*shared, current_)) break;
                pop(*shared, next_);
                primed_ = true;
            }
            const auto fraction = static_cast<float>(phase_);
            Frame music{current_.left + (next_.left - current_.left) * fraction,
                        current_.right + (next_.right - current_.right) * fraction};
            if (channels == 1) {
                const float value = (music.left + music.right) * 0.5f;
                if (value != 0) { output[frame] = clean(output[frame] + value); audible = true; }
            } else {
                if (music.left != 0) { output[frame * 2] = clean(output[frame * 2] + music.left); audible = true; }
                if (music.right != 0) { output[frame * 2 + 1] = clean(output[frame * 2 + 1] + music.right); audible = true; }
            }
            phase_ += 48000.0 / rate;
            while (phase_ >= 1.0) {
                current_ = next_;
                const bool more = pop(*shared, next_);
                phase_ -= 1.0;
                if (!more && current_.left == 0 && current_.right == 0) primed_ = false;
            }
        }
        return audible;
    }
};
}
