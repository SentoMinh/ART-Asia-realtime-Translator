#include "../bridge.h"
#include <array>
#include <cassert>
#include <iostream>
#include <vector>

int main()
{
    VrctBridgeInitialize();
    ULONGLONG reader = MAXULONGLONG;
    std::array<UCHAR, 16> output;
    output.fill(99);
    VrctBridgeRead(output.data(), 16, &reader);
    assert(output == (std::array<UCHAR, 16>{}));

    std::array<UCHAR, 8> input{1,2,3,4,5,6,7,8};
    VrctBridgeWrite(input.data(), 8);
    ULONGLONG second = MAXULONGLONG;
    VrctBridgeRead(output.data(), 16, &reader);
    assert(std::equal(input.begin(), input.end(), output.begin()));
    assert(output[8] == 0 && output[15] == 0);
    output.fill(99);
    VrctBridgeRead(output.data(), 16, &second);
    assert(std::equal(input.begin(), input.end(), output.begin()));

    // Oversized writes retain newest frames; a slow reader resynchronizes.
    std::vector<UCHAR> large(24000);
    for (size_t i = 0; i < large.size(); ++i) large[i] = static_cast<UCHAR>(i % 251);
    VrctBridgeWrite(large.data(), static_cast<ULONG>(large.size()));
    std::vector<UCHAR> retained(19200);
    VrctBridgeRead(retained.data(), 19200, &reader);
    assert(std::equal(retained.begin(), retained.end(), large.begin() + 4800));

    // Exercise wraparound with small, frame-aligned chunks.
    for (unsigned i = 0; i < 5000; ++i) {
        input[0] = static_cast<UCHAR>(i);
        VrctBridgeWrite(input.data(), 8);
        VrctBridgeRead(output.data(), 8, &reader);
        assert(std::equal(input.begin(), input.end(), output.begin()));
    }
    VrctBridgeWrite(input.data(), 8);
    VrctBridgeClear();
    VrctBridgeRead(output.data(), 16, &reader);
    assert(output == (std::array<UCHAR, 16>{}));

    VrctBridgeWrite(input.data(), 8);
    testTime += 1000001;
    VrctBridgeRead(output.data(), 16, &reader);
    assert(output == (std::array<UCHAR, 16>{}));
    VrctBridgeWrite(input.data(), 8);
    VrctBridgeRead(output.data(), 8, &reader);
    assert(std::equal(input.begin(), input.end(), output.begin()));

    // Partial frames are ignored, never exposing uninitialized bytes.
    VrctBridgeWrite(input.data(), 3);
    output.fill(99);
    VrctBridgeRead(output.data(), 7, &reader);
    assert(std::all_of(output.begin(), output.begin() + 7, [](UCHAR b) { return b == 0; }));
    // Music-input audio must not become microphone audio until the app forwards it.
    VrctBridgeClear(false);
    VrctBridgeClear(true);
    ULONGLONG musicReader = MAXULONGLONG;
    VrctBridgeWrite(input.data(), 8, true);
    VrctBridgeRead(output.data(), 16, &reader, false);
    assert(output == (std::array<UCHAR, 16>{}));
    VrctBridgeRead(output.data(), 8, &musicReader, true);
    assert(std::equal(input.begin(), input.end(), output.begin()));
    VrctBridgeWrite(output.data(), 8, false);
    VrctBridgeClear(true); // Stopping the music source must not clear the voice mix.
    VrctBridgeRead(output.data(), 8, &reader, false);
    assert(std::equal(input.begin(), input.end(), output.begin()));
    std::cout << "Bridge host tests passed (not a Windows kernel/driver test).\n";
}
