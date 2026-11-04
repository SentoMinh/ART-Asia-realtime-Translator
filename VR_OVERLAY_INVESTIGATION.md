# SteamVR cursor investigation — 30 October 2026

Status: the focused overlay fix was completed for 1.0.8 and now ships in **1.2.0**; source is committed and published. The 1.0.8 investigation below records the original behavior at the 1.0.8 development head and the final validation. Executable: `dist/1.2.0/VRChat-Translator-1.2.0.exe`. The 1.2.0 suite passed **859 tests**, and the packaged self-check passed. No saved model/provider changes or live SteamVR session were performed.

## Findings reproduced locally

The findings in this section describe the original 1.0.7 implementation. The implementation and validation results for the approved fix are recorded at the end of this report.

1. **Input and cursor positions normally update every 50 ms (nominally 20 Hz).** `vr/display.py:14` sets that timer interval; settings changes can invoke extra ticks, and scheduling delays can reduce the actual rate. Pose queries, controller input, scrolling, content rendering/upload and cursor submission share its GUI callback (`:205–228`). The panel itself is attached relative to a tracked controller, so this describes application input/cursor updates, not a claim that SteamVR renders the whole panel at 20 FPS.
2. **Crossing the panel edge can flicker the cursor.** `vr/pose.py:62` rejects an out-of-bounds ray immediately; `vr/display.py:115` cancels interaction and `vr/overlay.py:215` hides the cursor. A fake-controller trace alternating horizontal coordinates 0.9995/1.0005 (0.24 mm peak-to-peak at 24 cm panel width) produced visible/hidden/visible/hidden cursor states while the subtitle panel remained visible.
3. **One invalid input sample also hides the cursor.** The next valid pose restores it. Current click cancellation correctly prevents a held trigger from clicking after recovery. Preserve this protection; invalid tracking is not permission to reuse stale input.
4. **Faster ticking alone changes scrolling and fading.** Scroll moves 30 pixels per tick at full deflection (`vr/display.py:125`); fade changes by 0.25 per tick (`:19,211`). A one-second fake-clock replay scrolled 600 pixels with 20 ticks and 1,800 pixels with 60 ticks.
5. **Rendering can delay an already-sampled cursor.** The cursor is submitted after panel rendering/upload (`vr/display.py:218–228`). `vr/texture.py:54` also waits for GPU completion. That wait is a potential stall location, not a measured cause in this investigation; removing it without verifying compositor synchronization is not justified.

Evidence: `.tools/vr-overlay-investigation/pointer_diagnostics.py` and its JSON output. These use the existing FakeVR/FakeTextures, isolated temporary AppData and no headset or audio capture. They reproduce mechanisms, not the user's actual controller tracking or compositor behavior.

## CPU rendering sample

Thirty synthetic utterances, 720 × 480 panel, offscreen Qt, ten warmups and 100 measured iterations per case:

| Operation | Median | p95 | Subtitle uploads per 100 ticks |
| --- | ---: | ---: | ---: |
| Panel image plus RGBA conversion | 1.800 ms | 1.977 ms | N/A |
| Pointer motion tick | 0.080 ms | 0.132 ms | 0 |
| Scrolling tick | 1.944 ms | 2.111 ms | 100 |

Evidence: `.tools/vr-overlay-investigation/panel_benchmark.py` and its JSON output. Fake texture submission excludes real GPU uploads, SteamVR, compositor costs and contention with a game. This supports separating input cadence from content redraw frequency; it is not an end-to-end latency or FPS benchmark.

## Comparison with the suggested features

| Suggestion | Existing ART behavior | Assessment |
| --- | --- | --- |
| 16 kHz Silero with 0.50/0.35 hysteresis | Already present for the default microphone threshold; game audio defaults to 0.70/0.55. Threshold is held for each sentence. See `engine/vad.py:23,33,151,159` and `engine/speech.py:37`. | Keep the current detector. |
| 200 ms onset buffer | Nominal 300 ms rolling buffer; nine 32 ms frames including the activation frame. See `engine/vad.py:28,95,149`. | Reducing it does not address overlay lag. |
| Sherpa streaming Zipformer with four threads | Sherpa already runs offline SenseVoice using the app's one-thread budget (`engine/local_inference.py:67`); no streaming Zipformer path. | Separate optional project requiring language, accuracy and game-load benchmarks. Four threads conflict with the current gaming budget. |
| Opus to a FastAPI/WebSocket server | Current cloud adapters send 16 kHz WAV over HTTP (`engine/stt.py:258,360,369,390`). | Requires a compatible selected endpoint and separate latency/quality tests; not an overlay fix. |
| Tracked wrist overlay and controller interaction | Already implemented with tracked-device-relative placement, a separate cursor and persistent OpenGL textures (`vr/overlay.py:196,213`). | Improve the existing path. A switch to raw bitmap submission is not supported by current evidence. |
| Passive waits, below-normal priority, 3 GiB VRAM reserve | Already implemented in `engine/runtime.py` and `engine/gpu_budget.py`. | Preserve. The reserve applies to NLLB/Qwen CUDA translation; it is sampled admission/pressure checking, not a continuous reservation or guarantee against game frame drops. |

The user's VRCLS summary is a comparison target; local findings above do not independently verify its upstream implementation. The required `agy` lookup could not complete: the first attempt was automatically denied command permission in headless mode; a native-web-only retry timed out after 180 seconds without source content. No permission bypass or alternate research tool was used. Exact outputs and limits are in `.tools/vr-overlay-investigation/vrcls-research.md`. No production speaker identification is proposed; that roadmap item remains deferred.

## Approaches and recommended approval scope

**Recommended first pass: improve the current Qt/OpenVR path.** Target approximately 60 Hz input/cursor updates while separately limiting expensive content rendering (initial target at most 30 Hz during continuous scrolling). Keep disabled/disconnected work at the current low cadence. Submit cursor movement before expensive content work when the initial panel texture is ready. Convert scrolling and fading to elapsed-time rates, bounding elapsed time after stalls/reconnects so recovery cannot jump through the log. Retain existing persistent GPU textures and controller attachment.

For the reproduced edge flicker, add a small bounded visual-only grace for near-edge misses, with separate visual and interaction state. Out-of-bounds rays must immediately cancel clicks/drags; recovery with a held trigger must remain disarmed. Invalid tracking, looking away, hand switching and disconnect still hide the cursor immediately. Distinguish near-edge misses from the other reasons `pointer_hit()` returns `None`: behind-panel, distant and wrong-facing rays must not receive grace. Exact grace limits should be conservative and covered by deterministic tests; this does not claim to fix flicker in the middle of the panel.

Include lightweight opt-in timing and input-loss counters to distinguish late GUI callbacks, rendering/upload stalls, missed rays and invalid tracking during a later live session. Avoid per-frame disk logging. Extend `tests/test_vr.py` for elapsed-time invariance, redraw caps, safe loss/recovery, edge jitter, and idle behavior. Run the full pytest gate and native texture check after implementation. Include a separate test export in a new version directory, preserving existing artifacts, for the user's source/EXE comparison; publication is outside this proposal. A live headset/controller check is still needed to assess perceived smoothness and flicker.

**Alternative if measured stalls persist: a dedicated input worker.** Keep Qt widgets on the GUI thread and exchange only the latest input/render state. This can separate input from GUI painting but introduces thread ownership, OpenVR synchronization and shutdown complexity. Current evidence supports trying the smaller change first.

Rejected for this pass: a raw-upload/C# rewrite, blanket pointer smoothing (adds latency), recognition-model changes, more inference threads, changing GPU admission defaults, and unverified removal of GPU synchronization. These do not target the established mechanisms or need additional evidence.

## Validation and limits

- `.venv-app\Scripts\python.exe -m pytest tests/test_vr.py -q`: **83 passed in 12.84 seconds** against unchanged product code.
- `.venv-app\Scripts\python.exe tools\check_vr_texture.py`: **600 native GPU uploads/readbacks passed**, including stable texture IDs, RGBA/orientation and cleanup. It uses a fake receiver, not the SteamVR compositor.
- No full-suite rerun in this investigation. The latest handoff records 756 tests for 1.0.7; older guide references to 750 tests/1.0.6 are historical and are not fresh verification.
- The user confirms lag/flicker also occurs with recognition and translation paused, in both `run_ui.bat` source runs and separate exported test builds. This supports prioritizing the shared overlay path; it does not establish the exact cause of live flicker. Exact affected build versions are unspecified.
- No live headset, VRChat, tracking, GPU contention, service or packaged-executable timing test was performed by the agents.

## Approved implementation: local 1.0.8 test build

The resumed work keeps Qt/OpenVR and persistent textures on the existing GUI thread. Active input uses a precise 16 ms timer; disabled/disconnected polling stays at 1000 ms. Cursor submission precedes content rendering once the first panel texture is initialized. Continuous content redraws are capped at 30 Hz; changes remain pending until rendered. With an ideal 16 ms callback cadence, this strict minimum interval permits a content redraw every third tick, approximately 20.8 Hz. Cursor input still runs each tick.

Scrolling uses 600 pixels/second at full thumbstick deflection, with fractional accumulation. Fading uses 5 opacity units/second. Elapsed time is clamped to 100 ms after a stall; repeated timestamps add no scroll/fade. Backward samples retain the last good elapsed-time reference, preventing duplicate motion when the clock recovers; production uses `time.monotonic`. Tiny misses up to 3 pixels beyond an edge retain only the last cursor position for at most 75 ms after a valid hit. Clicks and drags cancel immediately; held triggers remain disarmed on re-entry. Invalid tracking, gaze, nonfinite geometry and distant/wrong-facing rays receive no grace.

`VRCT_VR_DIAGNOSTICS=1` enables aggregate callback gaps, panel rendering/upload times and input-loss reasons through `engine.vr` in the existing application log. Summaries are at least five seconds apart and contain no speech or credentials. Disabled diagnostics do not sample performance clocks. CPU/GPU inference settings, recognition models and texture synchronization are unchanged.

### Replays and CPU sample

The isolated replay (`.tools/release-1.0.8/pointer_diagnostics.json`) retained all six cursor frames for the same 0.24 mm edge jitter that previously alternated visible/hidden. One invalid pose immediately hid the cursor and cancelled the pressed button; recovery with a held trigger produced no click. One second of scrolling moved **600 pixels at both 20 and 60 input samples/second**, versus the original 600/1800 result.

The updated CPU harness (`.tools/release-1.0.8/panel_benchmark.json`) used the same 30 synthetic utterances, 720 × 480 panel, ten warmups and 100 measured samples, now advancing input by 16 ms:

| Operation | Median | p95 | Subtitle uploads per 100 samples |
| --- | ---: | ---: | ---: |
| Panel image plus RGBA conversion | 1.813 ms | 1.959 ms | 0 (conversion only) |
| Pointer motion tick | 0.091 ms | 0.130 ms | 0 |
| Scrolling tick | 0.176 ms | 1.991 ms | 33 |

This measures CPU work with fake texture submission and a fake clock. The lower scrolling median reflects skipped panel redraws, not faster individual rendering or a measured headset latency improvement. The changed sampling interval means the upload counts should not be compared as equal-duration workloads. Live compositor/controller smoothness and game contention remain unverified.

### Final source and package validation

- **789 source tests passed in 81.13 seconds**, including 116 VR cases. The independent review's backward-clock recovery issue was reproduced by two failing fade/scroll tests and fixed by retaining the last good elapsed timestamp. Final evidence: `.tools/release-1.0.8/tests-final.xml` and `tests-final.txt`.
- **600 native GPU uploads/readbacks passed**, including texture identity, RGBA/orientation and cleanup (`texture-check-resumed.txt`). The receiver is synthetic, not SteamVR.
- **236 bundled VR/UI tests passed in 26.05 seconds** using the EXE's bytecode in development Python, fake devices and isolated profiles (`packaged-tests.xml`, `packaged-checks.json`). This is separate from actual EXE execution.
- The actual **1.0.8 EXE self-check passed**, including bundled native/mixer/VR components and HTTPS 200, with isolated AppData and no downloaded models (`selfcheck.txt`). Bundled English/Chinese/Vietnamese update notices rendered correctly and were visually inspected; previews closed automatically (`preview/`).
- Bundle/privacy scans, native asset equality, required packaged modules, ZIP integrity and all 70 build-input hashes passed. Ten user-file/settings records and 1090 prior artifact size/mtime records matched the original baseline. Results: `verification.json`; checksums: `dist/1.0.8/SHA256SUMS.txt`.

The output folder contains the versioned EXE, test ZIP and SHA-256 manifest; the separate installer helper and headset checklist were removed from later source exports. The 1.0.8 build used the existing PowerShell script with the absolute validated mixer path. Windows PowerShell replaced unavailable `pwsh`; direct subprocess log handles avoided treating PyInstaller informational stderr as a shell error. Final build exited 0 (`build-final.txt`).

Still unverified: live controller/headset/compositor behavior, the actual cause of the user's flicker, VRChat/game FPS, Windows 10 and fresh-PC installation. Automated results establish the reproduced mechanisms and package integrity, not subjective smoothness. Compare 1.0.7 and the local 1.0.8 EXE under the same headset conditions, first with recognition/translation paused, then with VRChat running.
