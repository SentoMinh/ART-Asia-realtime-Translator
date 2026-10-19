#define NOMINMAX
#include <atlbase.h>
#include <atlcom.h>
#include <mmreg.h>
#include <audioenginebaseapo.h>
#include <baseaudioprocessingobject.h>
#include <propvarutil.h>
#include <ks.h>
#include <ksmedia.h>
#include "ids.h"
#include "transport.h"

namespace {
struct PropertyValue {
    PROPVARIANT value{};
    ~PropertyValue() { PropVariantClear(&value); }
};
}

class ATL_NO_VTABLE MicApo : public CComObjectRootEx<CComMultiThreadModel>,
    public CComCoClass<MicApo, &CLSID_VrctMicApo>,
    public CBaseAudioProcessingObject, public IAudioSystemEffects2 {
    vrct::Mapping mapping_;
    vrct::Reader reader_;
    UINT32 maximum_ = 0;
public:
    static const CRegAPOProperties<1> properties;
    MicApo() : CBaseAudioProcessingObject(properties) {}
    DECLARE_NO_REGISTRY()
    DECLARE_PROTECT_FINAL_CONSTRUCT()
    BEGIN_COM_MAP(MicApo)
        COM_INTERFACE_ENTRY(IAudioSystemEffects)
        COM_INTERFACE_ENTRY(IAudioSystemEffects2)
        COM_INTERFACE_ENTRY(IAudioProcessingObject)
        COM_INTERFACE_ENTRY(IAudioProcessingObjectRT)
        COM_INTERFACE_ENTRY(IAudioProcessingObjectConfiguration)
    END_COM_MAP()

    STDMETHOD(GetEffectsList)(LPGUID* effects, UINT* count, HANDLE) override {
        if (!effects || !count) return E_POINTER;
        *effects = nullptr;
        *count = 0;
        return S_OK;
    }

    STDMETHOD(Initialize)(UINT32 bytes, BYTE* data) override {
        if (m_bIsInitialized) return APOERR_ALREADY_INITIALIZED;
        if (!data) return E_INVALIDARG;
        IPropertyStore* store = nullptr;
        if (bytes == sizeof(APOInitSystemEffects)) store = reinterpret_cast<APOInitSystemEffects*>(data)->pAPOSystemEffectsProperties;
        else if (bytes == sizeof(APOInitSystemEffects2)) {
            const auto* init = reinterpret_cast<APOInitSystemEffects2*>(data);
            if (!init->InitializeForDiscoveryOnly && init->AudioProcessingMode != AUDIO_SIGNALPROCESSINGMODE_RAW)
                store = init->pAPOSystemEffectsProperties;
        }
        else return E_INVALIDARG;
        const auto* init = reinterpret_cast<APOInitBaseStruct*>(data);
        if (init->cbSize != bytes || init->clsid != CLSID_VrctMicApo) return E_INVALIDARG;
        try {
          if (store) {
            PropertyValue token, sid, local;
            if (SUCCEEDED(store->GetValue(PKEY_VrctToken, &token.value)) && token.value.vt == VT_LPWSTR &&
                SUCCEEDED(store->GetValue(PKEY_VrctUserSid, &sid.value)) && sid.value.vt == VT_LPWSTR) {
                bool localNamespace = false;
#ifdef VRCT_APO_TESTING
                if (SUCCEEDED(store->GetValue(PKEY_VrctTestLocal, &local.value)) && local.value.vt == VT_BOOL)
                    localNamespace = local.value.boolVal == VARIANT_TRUE;
#endif
                mapping_.create(vrct::mapping_name(token.value.pwszVal, localNamespace), sid.value.pwszVal);
            }
          }
        } catch (...) {
            // Allocation/configuration failure must not escape the COM boundary.
            mapping_.close();
        }
        // Absent/unavailable transport must never disable the user's microphone.
        m_bIsInitialized = true;
        return S_OK;
    }

    HRESULT ValidateAndCacheConnectionInfo(UINT32 inputs, APO_CONNECTION_DESCRIPTOR** in,
                                           UINT32 outputs, APO_CONNECTION_DESCRIPTOR** out) override {
        const HRESULT hr = CBaseAudioProcessingObject::ValidateAndCacheConnectionInfo(inputs, in, outputs, out);
        if (FAILED(hr)) return hr;
        maximum_ = std::min(in[0]->u32MaxFrameCount, out[0]->u32MaxFrameCount);
        reader_.reset();
        return S_OK;
    }

    STDMETHOD(Reset)() override { reader_.reset(); return S_OK; }

    #pragma AVRT_CODE_BEGIN
    STDMETHOD_(void, APOProcess)(UINT32 inputs, APO_CONNECTION_PROPERTY** in,
                               UINT32 outputs, APO_CONNECTION_PROPERTY** out) override {
        if (outputs != 1 || !out || !out[0]) return;
        auto& destination = *out[0];
        destination.u32ValidFrameCount = 0;
        destination.u32BufferFlags = BUFFER_INVALID;
        if (!m_bIsLocked || inputs != 1 || !in || !in[0] || !destination.pBuffer) return;
        const auto& source = *in[0];
        if (source.u32BufferFlags != BUFFER_VALID && source.u32BufferFlags != BUFFER_SILENT) return;
        const bool silent = source.u32BufferFlags == BUFFER_SILENT;
        if (!silent && !source.pBuffer) return;
        const UINT32 frames = std::min(source.u32ValidFrameCount, maximum_);
        if (mapping_.get()) mapping_.get()->hostHeartbeat.store(GetTickCount64());
        const bool music = reader_.mix(mapping_.get(), reinterpret_cast<const float*>(source.pBuffer),
            reinterpret_cast<float*>(destination.pBuffer), frames, GetSamplesPerFrame(),
            GetFramesPerSecond(), silent, GetTickCount64());
        destination.u32ValidFrameCount = frames;
        destination.u32BufferFlags = silent && !music ? BUFFER_SILENT : BUFFER_VALID;
    }
    #pragma AVRT_CODE_END
};

#pragma warning(push)
#pragma warning(disable:4815) // SDK CRegAPOProperties<1> has an intentional zero-length IID tail.
const CRegAPOProperties<1> MicApo::properties(CLSID_VrctMicApo,
    L"VRChat Translator microphone mixer", L"VRChat Translator", 0, 1,
    __uuidof(IAudioProcessingObject));
#pragma warning(pop)
OBJECT_ENTRY_AUTO(CLSID_VrctMicApo, MicApo)
class ApoModule : public CAtlDllModuleT<ApoModule> {};
ApoModule module;
extern "C" BOOL WINAPI DllMain(HINSTANCE, DWORD reason, LPVOID reserved) { return module.DllMain(reason, reserved); }
STDAPI DllCanUnloadNow() { return module.DllCanUnloadNow(); }
STDAPI DllGetClassObject(REFCLSID clsid, REFIID iid, void** object) { return module.DllGetClassObject(clsid, iid, object); }
extern "C" int __cdecl VrctApoBuildKind() {
#ifdef VRCT_APO_TESTING
    return 0;
#else
    return 1;
#endif
}
