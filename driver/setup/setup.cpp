// Own-driver setup. Device changes are disabled unless a verified package is embedded.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <initguid.h>
#include <devguid.h>
#include <setupapi.h>
#include <newdev.h>
#include <cfgmgr32.h>
#include <sddl.h>
#include <shellapi.h>
#include <objbase.h>
#include <algorithm>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr wchar_t HardwareId[] = L"Root\\VRCT_Audio";
constexpr wchar_t Title[] = L"VRChat Translator audio setup";

struct Failure : std::runtime_error {
    DWORD code;
    Failure(const char* action, DWORD value = GetLastError()) : std::runtime_error(action), code(value) {}
};
void require(BOOL ok, const char* action) { if (!ok) throw Failure(action); }

struct DeviceSet {
    HDEVINFO value;
    explicit DeviceSet(HDEVINFO handle) : value(handle) {
        if (value == INVALID_HANDLE_VALUE) throw Failure("Open device list");
    }
    ~DeviceSet() { SetupDiDestroyDeviceInfoList(value); }
    DeviceSet(const DeviceSet&) = delete;
    DeviceSet& operator=(const DeviceSet&) = delete;
};

// Bound parsing to the returned REG_MULTI_SZ buffer, even if Windows data is malformed.
bool matches(const std::vector<wchar_t>& ids) {
    size_t start = 0;
    while (start < ids.size() && ids[start]) {
        auto end = std::find(ids.begin() + start, ids.end(), L'\0');
        if (end == ids.end()) throw Failure("Invalid hardware ID property", ERROR_INVALID_DATA);
        const std::wstring id(ids.begin() + start, end);
        if (_wcsicmp(id.c_str(), HardwareId) == 0) return true;
        start = static_cast<size_t>(end - ids.begin()) + 1;
    }
    return false;
}

std::vector<SP_DEVINFO_DATA> devices(HDEVINFO set) {
    std::vector<SP_DEVINFO_DATA> found;
    for (DWORD index = 0;; ++index) {
        SP_DEVINFO_DATA device{};
        device.cbSize = sizeof(device);
        if (!SetupDiEnumDeviceInfo(set, index, &device)) {
            if (GetLastError() == ERROR_NO_MORE_ITEMS) break;
            throw Failure("Enumerate audio devices");
        }
        DWORD bytes = 0, type = 0;
        if (!SetupDiGetDeviceRegistryPropertyW(set, &device, SPDRP_HARDWAREID, &type, nullptr, 0, &bytes)) {
            const DWORD error = GetLastError();
            if (error == ERROR_INVALID_DATA) continue; // Device has no hardware IDs.
            if (error != ERROR_INSUFFICIENT_BUFFER) throw Failure("Read hardware IDs", error);
        }
        if (bytes == 0 || bytes % sizeof(wchar_t) || bytes > 1024 * 1024)
            throw Failure("Invalid hardware ID length", ERROR_INVALID_DATA);
        std::vector<wchar_t> ids(bytes / sizeof(wchar_t));
        require(SetupDiGetDeviceRegistryPropertyW(set, &device, SPDRP_HARDWAREID, &type,
            reinterpret_cast<BYTE*>(ids.data()), bytes, nullptr), "Read hardware IDs");
        if (type != REG_MULTI_SZ) throw Failure("Invalid hardware ID type", ERROR_INVALID_DATA);
        if (matches(ids)) found.push_back(device);
    }
    return found;
}

bool payload_present() { return FindResourceW(nullptr, MAKEINTRESOURCEW(201), RT_RCDATA) != nullptr; }

void status() {
    // Include disconnected devices so reinstallation does not silently duplicate one.
    DeviceSet set(SetupDiGetClassDevsW(&GUID_DEVCLASS_MEDIA, nullptr, nullptr, 0));
    auto found = devices(set.value);
    std::wcout << L"Matching Root\\VRCT_Audio devices: " << found.size() << L"\n";
    for (auto& device : found) {
        wchar_t id[MAX_DEVICE_ID_LEN]{};
        require(SetupDiGetDeviceInstanceIdW(set.value, &device, id, MAX_DEVICE_ID_LEN, nullptr), "Read instance ID");
        ULONG flags = 0, problem = 0;
        const auto result = CM_Get_DevNode_Status(&flags, &problem, device.DevInst, 0);
        std::wcout << id << L": ";
        if (result != CR_SUCCESS) std::wcout << L"not present or status unavailable";
        else std::wcout << L"started=" << ((flags & DN_STARTED) != 0) << L", problem=" << problem;
        std::wcout << L"\n";
    }
    std::wcout << (payload_present() ? L"Driver package embedded.\n" : L"Diagnostic build: no driver package; installation/removal disabled.\n");
}

bool elevated() {
    HANDLE token = nullptr;
    require(OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token), "Read process token");
    TOKEN_ELEVATION elevation{};
    DWORD bytes = 0;
    const BOOL ok = GetTokenInformation(token, TokenElevation, &elevation, sizeof(elevation), &bytes);
    const auto error = GetLastError();
    CloseHandle(token);
    if (!ok) throw Failure("Read elevation", error);
    return elevation.TokenIsElevated != 0;
}

DWORD elevate(const wchar_t* action) {
    wchar_t path[32768]{};
    const DWORD count = GetModuleFileNameW(nullptr, path, ARRAYSIZE(path));
    if (!count || count >= ARRAYSIZE(path)) throw Failure("Resolve setup executable");
    SHELLEXECUTEINFOW info{};
    info.cbSize = sizeof(info);
    info.fMask = SEE_MASK_NOCLOSEPROCESS;
    info.lpVerb = L"runas";
    info.lpFile = path;
    info.lpParameters = action;
    info.nShow = SW_SHOWNORMAL;
    require(ShellExecuteExW(&info), "Administrator approval");
    WaitForSingleObject(info.hProcess, INFINITE);
    DWORD result = ERROR_GEN_FAILURE;
    const BOOL ok = GetExitCodeProcess(info.hProcess, &result);
    CloseHandle(info.hProcess);
    require(ok, "Read setup result");
    return result;
}

void platform_check() {
    using VersionFunction = LONG(WINAPI*)(OSVERSIONINFOW*);
    const auto module = GetModuleHandleW(L"ntdll.dll");
    const auto address = GetProcAddress(module, "RtlGetVersion");
    if (!address) throw Failure("Read Windows version");
    VersionFunction version = nullptr;
    static_assert(sizeof(version) == sizeof(address));
    memcpy(&version, &address, sizeof(version));
    OSVERSIONINFOW info{};
    info.dwOSVersionInfoSize = sizeof(info);
    if (version(&info) != 0 || info.dwMajorVersion != 10 || info.dwBuildNumber < 19045)
        throw Failure("Requires Windows 10 22H2 or Windows 11", ERROR_OLD_WIN_VERSION);
    SYSTEM_INFO system{};
    GetNativeSystemInfo(&system);
    if (system.wProcessorArchitecture != PROCESSOR_ARCHITECTURE_AMD64)
        throw Failure("Requires an Intel/AMD x64 PC", ERROR_BAD_EXE_FORMAT);
}

struct Package {
    std::wstring directory;
    std::vector<std::wstring> files;
    Package() {
        // Use the protected Windows temp directory, not a user-supplied TEMP path.
        wchar_t windows[MAX_PATH]{};
        const UINT count = GetWindowsDirectoryW(windows, MAX_PATH);
        if (!count || count >= MAX_PATH) throw Failure("Find Windows directory");
        GUID id{};
        if (FAILED(CoCreateGuid(&id))) throw Failure("Create package ID", ERROR_GEN_FAILURE);
        wchar_t guid[40]{};
        StringFromGUID2(id, guid, ARRAYSIZE(guid));
        directory = std::wstring(windows) + L"\\Temp\\VrctAudio-" + guid;
        PSECURITY_DESCRIPTOR descriptor = nullptr;
        require(ConvertStringSecurityDescriptorToSecurityDescriptorW(
            L"D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)", SDDL_REVISION_1, &descriptor, nullptr), "Create package permissions");
        SECURITY_ATTRIBUTES attributes{sizeof(attributes), descriptor, FALSE};
        const BOOL ok = CreateDirectoryW(directory.c_str(), &attributes);
        const DWORD error = GetLastError();
        LocalFree(descriptor);
        if (!ok) throw Failure("Create protected package directory", error);
    }
    ~Package() {
        for (const auto& file : files) DeleteFileW(file.c_str());
        RemoveDirectoryW(directory.c_str());
    }
    void extract(int resource, const wchar_t* name) {
        const auto item = FindResourceW(nullptr, MAKEINTRESOURCEW(resource), RT_RCDATA);
        if (!item) throw Failure("Missing embedded driver file");
        const auto loaded = LoadResource(nullptr, item);
        const DWORD size = SizeofResource(nullptr, item);
        const void* data = LockResource(loaded);
        if (!data || !size) throw Failure("Empty driver resource", ERROR_INVALID_DATA);
        const auto path = directory + L"\\" + name;
        files.push_back(path);
        HANDLE output = CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (output == INVALID_HANDLE_VALUE) throw Failure("Extract driver file");
        DWORD written = 0;
        const BOOL ok = WriteFile(output, data, size, &written, nullptr);
        const DWORD error = GetLastError();
        CloseHandle(output);
        if (!ok || written != size) throw Failure("Write driver file", ok ? ERROR_WRITE_FAULT : error);
    }
};

DWORD change_device(bool remove) {
    // Serialize two setup instances before enumeration and device creation.
    HANDLE mutex = CreateMutexW(nullptr, FALSE, L"Global\\VRCT_Audio_Setup");
    if (!mutex) throw Failure("Open setup lock");
    struct Lock {
        HANDLE handle;
        bool acquired = false;
        ~Lock() { if (acquired) ReleaseMutex(handle); CloseHandle(handle); }
    } lock{mutex};
    const auto wait = WaitForSingleObject(mutex, 0);
    if (wait != WAIT_OBJECT_0 && wait != WAIT_ABANDONED)
        throw Failure("Another audio setup is running", ERROR_BUSY);
    lock.acquired = true;
    DeviceSet set(SetupDiGetClassDevsW(&GUID_DEVCLASS_MEDIA, nullptr, nullptr, 0));
    auto found = devices(set.value);
    if (found.size() > 1) throw Failure("Multiple translator audio devices found; resolve duplicates in Device Manager first", ERROR_DUP_NAME);
    BOOL reboot = FALSE;
    if (remove) {
        if (!found.empty()) require(DiUninstallDevice(nullptr, set.value, &found[0], 0, &reboot), "Remove translator audio device");
        // Retain the driver-store package; no unrelated OEM package is removed.
    } else {
        Package package;
        package.extract(201, L"VrctAudio.sys");
        package.extract(202, L"VrctAudio.inf");
        package.extract(203, L"VrctAudio.cat");
        const auto inf = package.directory + L"\\VrctAudio.inf";
        // Windows validates/stages the signed package before creating the root device.
        require(SetupCopyOEMInfW(inf.c_str(), nullptr, SPOST_PATH, 0, nullptr, 0, nullptr, nullptr), "Stage signed driver package");
        SP_DEVINFO_DATA created{};
        created.cbSize = sizeof(created);
        const bool isNew = found.empty();
        if (isNew) {
            require(SetupDiCreateDeviceInfoW(set.value, L"MEDIA", &GUID_DEVCLASS_MEDIA,
                L"VRChat Translator Audio", nullptr, DICD_GENERATE_ID, &created), "Create audio device");
            constexpr wchar_t ids[] = L"Root\\VRCT_Audio\0";
            require(SetupDiSetDeviceRegistryPropertyW(set.value, &created, SPDRP_HARDWAREID,
                reinterpret_cast<const BYTE*>(ids), sizeof(ids)), "Set audio hardware ID");
            require(SetupDiCallClassInstaller(DIF_REGISTERDEVICE, set.value, &created), "Register audio device");
        }
        // No FORCE: preserve a newer installed driver instead of silently downgrading it.
        if (!UpdateDriverForPlugAndPlayDevicesW(nullptr, HardwareId, inf.c_str(), 0, &reboot)) {
            const DWORD error = GetLastError();
            if (isNew) {
                BOOL rollbackReboot = FALSE;
                if (!DiUninstallDevice(nullptr, set.value, &created, 0, &rollbackReboot))
                    std::wcerr << L"Rollback failed; remove the new translator device in Device Manager.\n";
                if (rollbackReboot) std::wcerr << L"Restart Windows to finish rollback.\n";
                throw Failure("Install driver on new device", error);
            }
            if (error != ERROR_NO_MORE_ITEMS) throw Failure("Update audio driver", error);
            std::wcout << L"Windows kept the current driver because it is the same or a better match.\n";
        }
    }
    const wchar_t* message = reboot ? L"Setup finished. Restart Windows, then restart the translator."
        : remove ? L"Translator audio device removed. Its package remains in the Windows driver store."
        : L"Setup finished. Restart the translator. In VRChat, select VRChat Translator Microphone.";
    MessageBoxW(nullptr, message, Title, MB_OK | MB_ICONINFORMATION);
    return reboot ? ERROR_SUCCESS_REBOOT_REQUIRED : ERROR_SUCCESS;
}
}

int wmain(int argc, wchar_t** argv) {
    try {
        const std::wstring action = argc == 1 ? (payload_present() ? L"--install" : L"--status") : argv[1];
        if (argc > 2) throw Failure("Expected one action", ERROR_INVALID_PARAMETER);
        if (action == L"--status") { status(); return 0; }
        if (action != L"--install" && action != L"--remove") {
            std::wcout << L"VrctAudioSetup.exe [--status | --install | --remove]\n";
            return ERROR_INVALID_PARAMETER;
        }
        if (!payload_present()) throw Failure("No signed driver package embedded. This build cannot change devices", ERROR_NOT_SUPPORTED);
        platform_check();
        if (!elevated()) return static_cast<int>(elevate(action.c_str()));
        const bool remove = action == L"--remove";
        if (MessageBoxW(nullptr, remove ? L"Remove the VRChat Translator virtual audio device? Close VRChat and the translator first."
            : L"Install or update the VRChat Translator virtual audio driver? Close VRChat and the translator first.",
            Title, MB_YESNO | MB_DEFBUTTON2 | MB_ICONQUESTION) != IDYES) return ERROR_CANCELLED;
        return static_cast<int>(change_device(remove));
    } catch (const Failure& error) {
        std::cerr << error.what() << " (Windows error " << error.code << ")\n";
        // Diagnostic builds must be safe for unattended read-only checks.
        if (payload_present()) {
            const std::string narrow = std::string(error.what()) + " (Windows error " + std::to_string(error.code) + ")";
            MessageBoxA(nullptr, narrow.c_str(), "VRChat Translator audio setup", MB_OK | MB_ICONERROR);
        }
        return static_cast<int>(error.code ? error.code : ERROR_GEN_FAILURE);
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
        return ERROR_GEN_FAILURE;
    }
}
