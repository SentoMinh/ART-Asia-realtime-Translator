"""Produce an isolated, pinned SysVAD derivative. Does not install a driver."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

REVISION = "2dc3fd3a0cc84a2933f2194e7ec0871584979071"
HERE = Path(__file__).resolve().parent


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise ValueError(f"Upstream source mismatch: {before[:80]!r}")
    return text.replace(before, after, 1)


def array(text, name, body):
    pattern = rf"({name}\[\]\s*=\s*)\{{.*?\n\}};"
    text, count = re.subn(pattern, lambda m: m[1] + "{\n" + body + "\n};", text, flags=re.S)
    if count != 1:
        raise ValueError(f"Upstream array mismatch: {name}")
    return text


def guard_sideband_controls(text):
    # Upstream's audio-engine helpers contain eight unguarded sideband branches.
    # Keep their ordinary-device else bodies when sideband support is compiled out.
    matches = list(re.finditer(r"    if \(IsSidebandDevice\(\) && m_pSidebandDevice->", text))
    if len(matches) != 8:
        raise ValueError("Unexpected upstream sideband control branches")
    for match in reversed(matches):
        brace = text.index("{", match.end())
        depth, end = 1, brace + 1
        while depth:
            depth += (text[end] == "{") - (text[end] == "}")
            end += 1
        suffix = "\n    else\n"
        if text.startswith(suffix, end):
            end += len(suffix)
        text = (text[:match.start()] + "#if defined(SYSVAD_BTH_BYPASS) || defined(SYSVAD_USB_SIDEBAND)\n"
                + text[match.start():end] + "\n#endif\n" + text[end:])
    return text


def remove_modern_topology(text):
    """Remove unused physical-speaker properties unavailable at our Win10 target."""
    pattern = (r"[ \t]*else if \([^\n]*(?:KSPROPERTY_JACK_DESCRIPTION3|"
               r"KSPROPSETID_AudioResourceManagement|KSPROPSETID_AudioPosture)[^\n]*\)")
    matches = list(re.finditer(pattern, text))
    if not matches:
        raise ValueError("Missing upstream modern topology branches")
    for match in reversed(matches):
        brace = text.index("{", match.end())
        depth, end = 1, brace + 1
        while depth:
            depth += (text[end] == "{") - (text[end] == "}")
            end += 1
        text = text[:match.start()] + text[end:]
    return text


def remove_section(text, start, end):
    if text.count(start) != 1:
        raise ValueError(f"Missing upstream section: {start}")
    first = text.index(start)
    last = text.index(end, first)
    return text[:first] + text[last:]


PCM = """    {
        { sizeof(KSDATAFORMAT_WAVEFORMATEXTENSIBLE), 0, 0, 0,
          STATICGUIDOF(KSDATAFORMAT_TYPE_AUDIO), STATICGUIDOF(KSDATAFORMAT_SUBTYPE_PCM),
          STATICGUIDOF(KSDATAFORMAT_SPECIFIER_WAVEFORMATEX) },
        { { WAVE_FORMAT_EXTENSIBLE, 2, 48000, 192000, 4, 16,
            sizeof(WAVEFORMATEXTENSIBLE) - sizeof(WAVEFORMATEX) },
          16, KSAUDIO_SPEAKER_STEREO, STATICGUIDOF(KSDATAFORMAT_SUBTYPE_PCM) }
    }"""


def prepare(source: Path, target: Path):
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if revision != REVISION:
        raise ValueError(f"Expected Microsoft source {REVISION}, got {revision}")
    changed = subprocess.check_output(["git", "-C", str(source), "status", "--porcelain", "--", "audio/sysvad", "LICENSE"], text=True)
    if changed.strip():
        raise ValueError("The upstream source has local edits; use a clean pinned checkout.")
    # Never overwrite a developer's previous source/build output.
    target.mkdir(parents=True, exist_ok=False)
    root = target / "audio" / "sysvad"
    shutil.copytree(source / "audio" / "sysvad", root)
    shutil.copy2(source / "LICENSE", target / "MICROSOFT-LICENSE")
    if (source / "wil" / "include").is_dir():
        shutil.copytree(source / "wil", target / "wil", ignore=shutil.ignore_patterns(".git"))

    def edit(relative, transform):
        path = root / relative
        path.write_text(transform(path.read_text(encoding="utf-8-sig")), encoding="utf-8")

    for filename in ("bridge.h", "bridge.cpp"):
        shutil.copy2(HERE / filename, root / filename)
    edit("adapter.cpp", lambda t: replace_once(t, "#include <sysvad.h>", '#include <sysvad.h>\n#include "bridge.h"'))
    edit("adapter.cpp", lambda t: replace_once(t, "    ntStatus =  PcInitializeAdapterDriver", "    VrctBridgeInitialize();\n    ntStatus =  PcInitializeAdapterDriver"))
    # No registry option may re-enable sample audio-to-disk recording.
    edit("adapter.cpp", lambda t: re.sub(r'^.*RTL_QUERY_REGISTRY_DIRECT.*L"DoNotCreateDataFiles".*\n', '', t, flags=re.M))
    def endpoints(t):
        match = re.search(r"ENDPOINT_MINIPAIR HdmiMiniports =\s*\{.*?\n\};", t, re.S)
        if not match:
            raise ValueError("Missing HDMI endpoint template")
        clone = match[0].replace("HdmiMiniports", "VrctMusicMiniports").replace('L"TopologyHdmi"', 'L"TopologyVrctMusic"').replace('L"WaveHdmi"', 'L"WaveVrctMusic"')
        t = t[:match.end()] + "\n\nstatic\n" + clone + t[match.end():]
        return array(array(t, "g_RenderEndpoints", "    &HdmiMiniports,\n    &VrctMusicMiniports,"), "g_CaptureEndpoints", "    &MicInMiniports,")
    edit("TabletAudioSample/minipairs.h", endpoints)

    for file, prefix, mode_prefix in (("hdmiwavtable.h", "HdmiHostPin", "HdmiHostPin"), ("micinwavtable.h", "MicInPin", "MicInPin")):
        def formats(t):
            t = array(t, prefix + "SupportedDeviceFormats", PCM)
            modes = ["RAW", "DEFAULT", "COMMUNICATIONS", "SPEECH", "MEDIA"]
            t = array(t, mode_prefix + "SupportedDeviceModes", ",\n".join(
                "    { STATIC_AUDIO_SIGNALPROCESSINGMODE_" + mode + ", &" + prefix + "SupportedDeviceFormats[0].DataFormat }" for mode in modes))
            t = re.sub(r'(#define\s+(?:HDMI_HOST_MIN_SAMPLE_RATE|HDMI_HOST_MAX_SAMPLE_RATE|MICIN_MIN_SAMPLE_RATE)\s+)\d+', r'\g<1>48000', t)
            t = re.sub(r'(#define\s+MICIN_DEVICE_MAX_CHANNELS\s+)\d+', r'\g<1>2', t)
            t = re.sub(r'(#define\s+HDMI_MAX_INPUT_SYSTEM_STREAMS\s+)\d+', r'\g<1>1', t)
            # The actual format table rejects compressed formats; stop advertising their ranges too.
            if file == "hdmiwavtable.h":
                t = array(t, "HdmiPinDataRangePointersStream", "    PKSDATARANGE(&HdmiPinDataRangesStream[0]),\n    PKSDATARANGE(&PinDataRangeAttributeList),")
            return t
        edit("TabletAudioSample/" + file, formats)

    edit("TabletAudioSample/micintoptable.h", lambda t: t.replace("KSAUDIO_SPEAKER_MONO", "KSAUDIO_SPEAKER_STEREO"))
    edit("EndpointsCommon/MiniportAudioEngineNode.cpp", guard_sideband_controls)
    # These sample-only physical speaker controls require newer Windows APIs.
    # Our virtual endpoints do not expose posture, resource groups or jack v3.
    edit("EndpointsCommon/mintopo.h", lambda t: remove_section(t, "    typedef struct\n", "    union {"))
    edit("EndpointsCommon/mintopo.h", lambda t: replace_once(t, "        m_PostureCache.Orientation = AUDIOPOSTURE_ORIENTATION_NOTROTATED;", ""))
    edit("EndpointsCommon/mintopo.h", lambda t: remove_section(t, "    NTSTATUS PropertyHandlerJackDescription3", "#if defined(SYSVAD_BTH_BYPASS)"))
    edit("EndpointsCommon/mintopo.cpp", lambda t: remove_section(t, 'NTSTATUS\nCMiniportTopology::PropertyHandlerJackDescription3', "#if defined(SYSVAD_BTH_BYPASS)"))
    for speaker in ("Speaker", "SpeakerHp"):
        edit(f"EndpointsCommon/{speaker.lower()}topo.cpp", remove_modern_topology)
        def legacy_properties(t):
            name = f"Properties{speaker}TopoFilter"
            match = re.search(rf"{name}\[\]\s*=\s*\{{(.*?)\n\}};", t, re.S)
            entries = re.findall(r"\{[^{}]*\}", match[1]) if match else []
            entries = [entry for entry in entries if not any(token in entry for token in (
                "KSPROPERTY_JACK_DESCRIPTION3", "KSPROPSETID_AudioResourceManagement", "KSPROPSETID_AudioPosture"))]
            if len(entries) != 2:
                raise ValueError("Unexpected upstream speaker properties")
            return array(t, name, "    " + ",\n    ".join(entries))
        edit(f"EndpointsCommon/{speaker.lower()}toptable.h", legacy_properties)
    edit("EndpointsCommon/speakerhptopo.cpp", lambda t: replace_once(t, "    PCMiniportTopology  pMiniport = (PCMiniportTopology)PropertyRequest->MajorTarget;", ""))

    # Insert a cursor beside an existing per-stream field, preserving the class's layout rules.
    edit("EndpointsCommon/minwavertstream.h", lambda t: replace_once(t, "    KSSTATE", "    ULONGLONG m_VrctReadCursor;\n    bool m_VrctMusicInput;\n    KSSTATE"))
    def stream(t):
        t = replace_once(t, '#include "minwavertstream.h"', '#include "minwavertstream.h"\n#include "bridge.h"')
        t = replace_once(t, "    m_KsState = KSSTATE_STOP;", "    m_VrctMusicInput = false;\n    m_VrctReadCursor = MAXULONGLONG;\n    m_KsState = KSSTATE_STOP;")
        t = replace_once(t, "    m_pMiniport->AddRef();", '    m_pMiniport->AddRef();\n    m_VrctMusicInput = wcscmp(m_pMiniport->m_pMiniportPair->WaveName, L"WaveVrctMusic") == 0;')
        t = replace_once(t, "m_ToneGenerator.GenerateSine(m_pDmaBuffer + bufferOffset, runWrite);", "VrctBridgeRead(m_pDmaBuffer + bufferOffset, runWrite, &m_VrctReadCursor, m_VrctMusicInput);")
        t = replace_once(t, "m_SaveData.WriteData(m_pDmaBuffer + bufferOffset, runWrite);", "VrctBridgeWrite(m_pDmaBuffer + bufferOffset, runWrite, m_VrctMusicInput);")
        t = replace_once(t, "        if (!g_DoNotCreateDataFiles)\n        {\n            // Read from buffer and write to a file.\n            ReadBytes(ByteDisplacement);\n        }", "        ReadBytes(ByteDisplacement);")
        t = replace_once(t, "        case KSSTATE_STOP:", "        case KSSTATE_STOP:\n            m_VrctReadCursor = MAXULONGLONG;\n            if (!m_bCapture) VrctBridgeClear(m_VrctMusicInput);")
        t = replace_once(t, "        case KSSTATE_RUN:", "        case KSSTATE_RUN:\n            m_VrctReadCursor = MAXULONGLONG;")
        t = t.replace("// Write sine wave to buffer.", "// Fill capture from the translator render stream.")
        t = t.replace("This function writes the audio buffer using a sine wave generator", "This function fills capture from the bounded render bridge")
        t = t.replace("This function reads the audio buffer and saves the data in a file.", "This function forwards render data to the bounded capture bridge.")
        return t
    edit("EndpointsCommon/minwavertstream.cpp", stream)
    # Reject every format except the bridge's byte-exact PCM contract, including KS clients.
    edit("EndpointsCommon/minwavertstream.cpp", lambda t: replace_once(t, "    m_ulDmaMovementRate = pWfEx->nAvgBytesPerSec;", """    if (pWfEx->nSamplesPerSec != 48000 || pWfEx->nChannels != 2 ||
        pWfEx->wBitsPerSample != 16 || pWfEx->nBlockAlign != 4 ||
        pWfEx->nAvgBytesPerSec != 192000 ||
        !IsEqualGUIDAligned(DataFormat_->SubFormat, KSDATAFORMAT_SUBTYPE_PCM))
        return STATUS_INVALID_PARAMETER;
    m_ulDmaMovementRate = pWfEx->nAvgBytesPerSec;"""))

    for project in ("EndpointsCommon/EndpointsCommon.vcxproj", "TabletAudioSample/TabletAudioSample.vcxproj"):
        edit(project, lambda t: re.sub(r"\bSYSVAD_(?:BTH_BYPASS|USB_SIDEBAND|A2DP_SIDEBAND);?", "", t))
    edit("EndpointsCommon/EndpointsCommon.vcxproj", lambda t: replace_once(t, '<ClCompile Include="minwavertstream.cpp" />', '<ClCompile Include="minwavertstream.cpp" />\n    <ClCompile Include="..\\bridge.cpp" />'))
    edit("TabletAudioSample/TabletAudioSample.vcxproj", lambda t: replace_once(t, '<Inf Exclude="@(Inx)" Include="*.inx" />', '<Inf Include="VrctAudio.inf"><SpecifyDriverVerDirectiveDate>false</SpecifyDriverVerDirectiveDate><SpecifyDriverVerDirectiveVersion>false</SpecifyDriverVerDirectiveVersion></Inf>'))
    edit("TabletAudioSample/TabletAudioSample.vcxproj", lambda t: replace_once(t, '<OutDir>$(IntDir)</OutDir>', '<OutDir>$(IntDir)</OutDir>\n    <TargetName>VrctAudio</TargetName>'))
    shutil.copy2(HERE / "VrctAudio.inf", root / "TabletAudioSample" / "VrctAudio.inf")
    (target / "vrct-prepared.json").write_text(json.dumps({"upstream": REVISION, "target": "Windows 10 22H2 x64"}), encoding="utf-8")
    return root


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Microsoft Windows-driver-samples checkout at the pinned revision")
    parser.add_argument("target", type=Path, help="New output directory (must not exist)")
    args = parser.parse_args()
    print(prepare(args.source, args.target))
