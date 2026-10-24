# Whisper turbo on Vulkan

ART's separate `whisper-turbo-vulkan` hearing option uses whisper.cpp v1.9.2,
revision `306c88f4d1286aec1bf96e544632897886af5501`. It uses Vulkan 1.2+ and a compatible
graphics driver, including AMD. NVIDIA users can keep the existing faster-whisper CUDA option.
The native bridge, ggml and whisper are statically linked into one DLL; Windows supplies the
graphics driver's Vulkan loader. The SDK is required only to build, not to use the app.

Build with Visual Studio 2022 C++ tools, CMake and the Vulkan SDK:

```powershell
./tools/build-whisper-vulkan.ps1 -VulkanSdk C:/VulkanSDK/<version>
./tools/build.ps1 -MixerBuild <production-mixer-folder>
```

Use a short build directory: MSBuild's shader-generator tracking files can exceed Windows'
path limit. The helper defaults to `.tools/wvk` and two parallel build jobs; upstream shader
generation also uses multiple threads. SDK build validation used LunarG 1.4.363.0, installed
under the ignored `.tools` folder with `copy_only=1` (no registry or driver installation).
The DLL is ignored by Git and built into `assets/whisper-vulkan`; its upstream MIT license
is included in the app. Pass `-WhisperBuild <runtime-folder>` to package a separately built DLL.
Keep the exported ABI version synchronized with `engine/whisper_vulkan.py` if changing it.

The Download button fetches a pinned 574,041,195-byte Q5_0 turbo model (~547 MiB) with SHA-256
verification and the existing Hugging Face → HF-Mirror network fallback. It has a separate
cache directory and Delete button. No existing model or selection is converted or replaced.

One native context stays loaded across sentences and is warmed up during loading. Model
switching and the hearing worker's normal shutdown free it. A compatible GPU is required;
failure to find/initialize one produces a hearing error. GPU selection favors a discrete GPU,
then the largest memory capacity. The selected device is logged in `engine.log`.
Audio stays in memory; no recording is written or sent to a server. Float32/mono/finite input,
independent sentences, beam size 5, phantom/repetition/silence checks and Chinese routing
are preserved. Auto language detection uses whisper.cpp's result; it does not expose the
faster-whisper adapter's full language probability vector. Multiple selected languages are
still filtered by the shared speech pipeline.

Validation: 536 tests passed before release documentation changes. Actual Vulkan inference
ran on RTX 3080: one recorded EN, ZH and VI clip each, in forced-language and Auto modes,
returned matching languages and recognizable reference wording. This small replay is not an
accuracy comparison with SenseVoice. Initial load plus warmup was 20.4 s; the six later calls
took 403–1,625 ms for 3.3–4.32 s clips. Concurrent GPU load was uncontrolled. AMD hardware,
Cantonese/Japanese/Korean accuracy, VRChat impact and fresh-PC driver compatibility remain
unverified. Evidence is in `.tools/whisper-vulkan/`.

Sources: [whisper.cpp](https://github.com/ggml-org/whisper.cpp/tree/306c88f4d1286aec1bf96e544632897886af5501),
[model files](https://huggingface.co/ggerganov/whisper.cpp/tree/5359861c739e955e79d9a303bcbc70fb988958b1).
