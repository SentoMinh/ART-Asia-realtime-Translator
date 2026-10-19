#define NOMINMAX
#include <atlbase.h>
#include <mmreg.h>
#include <audioenginebaseapo.h>
#include <audiomediatype.h>
#include <propsys.h>
#include <propvarutil.h>
#include <sddl.h>
#include <ks.h>
#include <ksmedia.h>
#include <iostream>
#include <vector>
#include <stdexcept>
#include <memory>
#include "ids.h"
#include "mixer.h"

void expect(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
void check(HRESULT value, const char* message) {
    if (FAILED(value)) { std::cerr << message << ": HRESULT=" << std::hex << value << "\n"; throw std::runtime_error(message); }
}
template<class T> T function(HMODULE module, const char* name) {
    const auto address = GetProcAddress(module, name);
    expect(address != nullptr, name);
    T result = nullptr;
    static_assert(sizeof(result) == sizeof(address));
    memcpy(&result, &address, sizeof(result));
    return result;
}

void core_tests() {
    auto shared = std::make_unique<vrct::Shared>();
    shared->magic.store(vrct::Magic);
    vrct::Reader reader, other;
    std::vector<float> voice(960, 0.25f), output(960), music(960, 0.1f);
    reader.mix(shared.get(), voice.data(), output.data(), 480, 2, 48000, false, 100);
    expect(output == voice, "Inactive transport must preserve voice");
    vrct::begin(*shared);
    vrct::write(*shared, music.data(), 480, 100);
    reader.mix(shared.get(), voice.data(), output.data(), 480, 2, 48000, false, 100);
    for (auto value : output) expect(std::abs(value - 0.35f) < 0.0001, "Voice/music mix");
    other.mix(shared.get(), voice.data(), output.data(), 480, 2, 48000, false, 100);
    expect(std::abs(output[0] - 0.35f) < 0.0001, "Independent readers");
    vrct::stop(*shared);
    reader.mix(shared.get(), voice.data(), output.data(), 480, 2, 48000, false, 100);
    expect(output == voice, "Stop keeps voice and removes music");
    vrct::write(*shared, music.data(), 480, 100);
    reader.mix(shared.get(), voice.data(), output.data(), 480, 2, 48000, false, 251);
    expect(output == voice, "Expired producer must preserve voice");
    vrct::begin(*shared);
    std::fill(music.begin(), music.end(), 0.9f);
    vrct::write(*shared, music.data(), 480, 300);
    reader.mix(shared.get(), voice.data(), output.data(), 480, 2, 48000, false, 300);
    expect(std::all_of(output.begin(), output.end(), [](float v) { return v == 1; }), "Clipping protection");
    vrct::begin(*shared);
    for (size_t i = 0; i < music.size(); i += 2) { music[i] = 0.1f; music[i + 1] = 0.3f; }
    vrct::write(*shared, music.data(), 480, 400);
    reader.mix(shared.get(), nullptr, output.data(), 400, 1, 44100, true, 400);
    expect(std::all_of(output.begin(), output.begin() + 400, [](float v) { return std::abs(v - 0.2f) < 0.0001f; }), "44.1k mono downmix");
    vrct::begin(*shared);
    std::fill(music.begin(), music.end(), NAN);
    vrct::write(*shared, music.data(), 480, 500);
    reader.mix(shared.get(), voice.data(), output.data(), 480, 2, 48000, false, 500);
    expect(output == voice, "Invalid music samples never poison voice");
    // Writer wrap and slow-reader resynchronization stay bounded.
    for (int i = 0; i < 40; ++i) vrct::write(*shared, voice.data(), 480, 600);
    reader.mix(shared.get(), nullptr, output.data(), 480, 2, 48000, true, 600);
    expect(std::all_of(output.begin(), output.end(), [](float v) { return v == 0.25f; }), "Ring wrap");
}

std::wstring current_sid() {
    HANDLE token = nullptr;
    expect(OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token) != FALSE, "Current user token");
    DWORD size = 0;
    GetTokenInformation(token, TokenUser, nullptr, 0, &size);
    std::vector<BYTE> bytes(size);
    const bool ok = GetTokenInformation(token, TokenUser, bytes.data(), size, &size) != FALSE;
    CloseHandle(token);
    expect(ok, "Current user SID");
    wchar_t* text = nullptr;
    expect(ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER*>(bytes.data())->User.Sid, &text) != FALSE, "SID text");
    std::wstring result(text);
    LocalFree(text);
    return result;
}

void set_string(IPropertyStore* store, REFPROPERTYKEY key, const wchar_t* value) {
    PROPVARIANT data{};
    check(InitPropVariantFromString(value, &data), "Set string");
    check(store->SetValue(key, data), "Set property");
    PropVariantClear(&data);
}

void com_test(HMODULE apoModule, HMODULE producerModule, const wchar_t* executable, const wchar_t* producerPath,
              const wchar_t* python = nullptr, const wchar_t* wav = nullptr) {
    using GetClass = HRESULT(STDAPICALLTYPE*)(REFCLSID, REFIID, void**);
    using Open = void*(__cdecl*)(const wchar_t*, BOOL);
    using Write = BOOL(__cdecl*)(void*, const float*, UINT32);
    using Close = BOOL(__cdecl*)(void*);
    const auto getClass = function<GetClass>(apoModule, "DllGetClassObject");
    const auto open = function<Open>(producerModule, "VrctOpen");
    const auto write = function<Write>(producerModule, "VrctWrite");
    const auto close = function<Close>(producerModule, "VrctClose");
    const auto probe = function<DWORD(__cdecl*)(const wchar_t*, BOOL)>(producerModule, "VrctProbe");
    CComPtr<IClassFactory> factory;
    check(getClass(CLSID_VrctMicApo, IID_PPV_ARGS(&factory)), "Get class factory");
    CComPtr<IAudioProcessingObject> apo;
    check(factory->CreateInstance(nullptr, IID_PPV_ARGS(&apo)), "Create APO without registration");
    CComPtr<IPropertyStore> properties;
    check(PSCreateMemoryPropertyStore(IID_PPV_ARGS(&properties)), "Memory property store");
    GUID id{}; check(CoCreateGuid(&id), "Token GUID");
    wchar_t token[40]{}; StringFromGUID2(id, token, 40);
    expect(probe(token, TRUE) == 0, "Probe cannot invent a host");
    set_string(properties, PKEY_VrctToken, token);
    set_string(properties, PKEY_VrctUserSid, current_sid().c_str());
    PROPVARIANT local{}; local.vt = VT_BOOL; local.boolVal = VARIANT_TRUE;
    check(properties->SetValue(PKEY_VrctTestLocal, local), "Local namespace");
    // RAW/discovery must not create a transport even with valid configuration.
    for (int mode = 0; mode < 3; ++mode) {
        CComPtr<IAudioProcessingObject> bypass;
        check(factory->CreateInstance(nullptr, IID_PPV_ARGS(&bypass)), "Create bypass APO");
        APOInitSystemEffects2 bypassInit{};
        bypassInit.APOInit.cbSize = sizeof(bypassInit);
        bypassInit.APOInit.clsid = CLSID_VrctMicApo;
        bypassInit.AudioProcessingMode = mode == 0 ? AUDIO_SIGNALPROCESSINGMODE_RAW : AUDIO_SIGNALPROCESSINGMODE_DEFAULT;
        bypassInit.InitializeForDiscoveryOnly = mode == 1;
        bypassInit.pAPOSystemEffectsProperties = mode == 2 ? nullptr : properties.p;
        check(bypass->Initialize(sizeof(bypassInit), reinterpret_cast<BYTE*>(&bypassInit)), "Bypass initializes without music");
        expect(open(token, TRUE) == nullptr, "RAW/discovery/missing config cannot connect music");
    }
    expect(open(L"invalid-guid", TRUE) == nullptr, "Invalid endpoint token rejected");
    expect(open(nullptr, TRUE) == nullptr, "Missing endpoint token rejected");
    APOInitSystemEffects init{};
    init.APOInit.cbSize = sizeof(init); init.APOInit.clsid = CLSID_VrctMicApo;
    init.pAPOSystemEffectsProperties = properties;
    check(apo->Initialize(sizeof(init), reinterpret_cast<BYTE*>(&init)), "Initialize APO");
    expect(probe(token, TRUE) == 1, "Loaded host is distinct from live processing");
    expect(apo->Initialize(sizeof(init), reinterpret_cast<BYTE*>(&init)) == APOERR_ALREADY_INITIALIZED, "Double initialization rejected");
    CComQIPtr<IAudioProcessingObjectConfiguration> config(apo);
    CComQIPtr<IAudioProcessingObjectRT> realtime(apo);
    expect(config && realtime, "Required APO interfaces");
    WAVEFORMATEX wave{};
    wave.wFormatTag = WAVE_FORMAT_IEEE_FLOAT;
    wave.nChannels = 2; wave.nSamplesPerSec = 48000; wave.wBitsPerSample = 32;
    wave.nBlockAlign = 8; wave.nAvgBytesPerSec = 384000;
    CComPtr<IAudioMediaType> format;
    check(CreateAudioMediaType(&wave, sizeof(wave), &format), "Float media type");
    std::vector<float> input(960, 0.2f), output(960), music(960, 0.1f);
    APO_CONNECTION_DESCRIPTOR in{APO_CONNECTION_BUFFER_TYPE_EXTERNAL, reinterpret_cast<UINT_PTR>(input.data()), 480, format, APO_CONNECTION_DESCRIPTOR_SIGNATURE};
    APO_CONNECTION_DESCRIPTOR out{APO_CONNECTION_BUFFER_TYPE_EXTERNAL, reinterpret_cast<UINT_PTR>(output.data()), 480, format, APO_CONNECTION_DESCRIPTOR_SIGNATURE};
    auto* inPtr = &in; auto* outPtr = &out;
    check(config->LockForProcess(1, &inPtr, 1, &outPtr), "Lock APO");
    APO_CONNECTION_PROPERTY source{}, dest{};
    source.pBuffer = reinterpret_cast<UINT_PTR>(input.data()); source.u32ValidFrameCount = 480;
    source.u32BufferFlags = BUFFER_VALID; source.u32Signature = APO_CONNECTION_PROPERTY_SIGNATURE;
    dest.pBuffer = reinterpret_cast<UINT_PTR>(output.data()); dest.u32Signature = APO_CONNECTION_PROPERTY_SIGNATURE;
    auto* sourcePtr = &source; auto* destPtr = &dest;
    realtime->APOProcess(1, &sourcePtr, 1, &destPtr);
    expect(output == input, "COM microphone passthrough");
    expect(probe(token, TRUE) == 2, "Probe detects real processing without sending music");
    source.u32ValidFrameCount = 481;
    realtime->APOProcess(1, &sourcePtr, 1, &destPtr);
    expect(dest.u32ValidFrameCount == 480 && output == input, "Oversized frame count bounded by locked buffers");
    source.u32ValidFrameCount = 480;
    source.u32BufferFlags = BUFFER_INVALID;
    realtime->APOProcess(1, &sourcePtr, 1, &destPtr);
    expect(dest.u32BufferFlags == BUFFER_INVALID && dest.u32ValidFrameCount == 0, "Invalid input not processed");
    source.u32BufferFlags = BUFFER_VALID;
    void* writer = open(token, TRUE);
    expect(writer != nullptr, "Open producer transport");
    expect(open(token, TRUE) == nullptr, "Reject duplicate producer");
    expect(write(writer, music.data(), 480) != FALSE, "Publish music");
    realtime->APOProcess(1, &sourcePtr, 1, &destPtr);
    expect(dest.u32BufferFlags == BUFFER_VALID && dest.u32ValidFrameCount == 480, "COM valid output metadata");
    for (auto value : output) expect(std::abs(value - 0.3f) < 0.0001f, "COM voice plus music");
    expect(close(writer) != FALSE, "Close producer");
    realtime->APOProcess(1, &sourcePtr, 1, &destPtr);
    expect(output == input, "COM stop preserves voice");
    source.u32BufferFlags = BUFFER_SILENT;
    realtime->APOProcess(1, &sourcePtr, 1, &destPtr);
    expect(dest.u32BufferFlags == BUFFER_SILENT, "Silent microphone flag");
    expect(std::all_of(output.begin(), output.end(), [](float v) { return v == 0; }), "Silent microphone data");
    // Exercise a separate writer process and abrupt exit without VrctClose.
    source.u32BufferFlags = BUFFER_VALID;
    std::wstring command = L"\"" + std::wstring(executable) + L"\" --writer \"" + token + L"\" \"" + producerPath + L"\"";
    if (python && wav) {
        command = L"\"" + std::wstring(python) + L"\" -m vrc.apo_music --local-test --library \"" +
            producerPath + L"\" --token \"" + token + L"\" --wav \"" + wav + L"\" --gain 1";
    }
    STARTUPINFOW startup{}; startup.cb = sizeof(startup);
    PROCESS_INFORMATION process{};
    expect(CreateProcessW(nullptr, command.data(), nullptr, nullptr, FALSE, CREATE_NO_WINDOW,
        nullptr, nullptr, &startup, &process) != FALSE, "Start isolated music producer");
    CloseHandle(process.hThread);
    bool heard = false;
    const auto deadline = GetTickCount64() + 10000;
    while (GetTickCount64() < deadline && WaitForSingleObject(process.hProcess, 0) == WAIT_TIMEOUT) {
        realtime->APOProcess(1, &sourcePtr, 1, &destPtr);
        heard = heard || output[0] > 0.25f;
        Sleep(10);
    }
    DWORD exit = STILL_ACTIVE;
    GetExitCodeProcess(process.hProcess, &exit);
    if (exit == STILL_ACTIVE) {
        TerminateProcess(process.hProcess, 1); // Only the child created by this test.
        WaitForSingleObject(process.hProcess, 1000);
    }
    CloseHandle(process.hProcess);
    expect(exit == 0 && heard, "Separate-process music reaches APO");
    Sleep(200);
    realtime->APOProcess(1, &sourcePtr, 1, &destPtr);
    expect(output == input, "Crashed writer expires without muting microphone");
    check(config->UnlockForProcess(), "Unlock APO");
}

int wmain(int argc, wchar_t** argv) {
    try {
        if (argc == 4 && std::wstring(argv[1]) == L"--writer") {
            const HMODULE dll = LoadLibraryExW(argv[3], nullptr, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
            expect(dll != nullptr, "Writer DLL");
            const auto open = function<void*(__cdecl*)(const wchar_t*, BOOL)>(dll, "VrctOpen");
            const auto write = function<BOOL(__cdecl*)(void*, const float*, UINT32)>(dll, "VrctWrite");
            void* writer = open(argv[2], TRUE);
            expect(writer != nullptr, "Cross-process writer connection");
            std::vector<float> music(960, 0.1f);
            for (int i = 0; i < 25; ++i) { expect(write(writer, music.data(), 480) != FALSE, "Cross-process write"); Sleep(10); }
            ExitProcess(0); // Deliberately bypass close to test crash/stale handling.
        }
        expect(argc == 3 || argc == 5, "Usage: ApoTests.exe test-apo.dll producer.dll [python.exe fixture.wav]");
        check(CoInitializeEx(nullptr, COINIT_MULTITHREADED), "COM initialization");
        core_tests();
        const HMODULE apo = LoadLibraryExW(argv[1], nullptr, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
        const HMODULE producer = LoadLibraryExW(argv[2], nullptr, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
        expect(apo && producer, "Load prototype DLLs");
        com_test(apo, producer, argv[0], argv[2]);
        if (argc == 5) {
            com_test(apo, producer, argv[0], argv[2], argv[3], argv[4]);
            std::cout << "Python WAV playback reached the native APO through the actual producer DLL.\n";
        }
        FreeLibrary(producer); FreeLibrary(apo);
        CoUninitialize();
        std::cout << "APO core and standalone COM/transport tests passed. No Windows audio device was modified.\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << "\n"; return 1; }
}
