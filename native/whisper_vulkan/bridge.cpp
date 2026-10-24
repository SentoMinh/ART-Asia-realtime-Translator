// A small, versioned C ABI: Python never mirrors upstream C++ parameter structs.
#include "whisper.h"
#include "ggml-vulkan.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <exception>
#include <memory>
#include <string>

#define ART extern "C" __declspec(dllexport)
struct Model {
    whisper_context * ctx = nullptr;
    std::string device;
    ~Model() { if (ctx) whisper_free(ctx); }
};
static thread_local std::string error;
static void log_message(ggml_log_level level, const char * text, void *) {
    if (level == GGML_LOG_LEVEL_ERROR && text) error = std::string(text).substr(0, 2048);
}
ART int art_whisper_abi() { return 1; }
ART const char * art_whisper_error() { return error.c_str(); }

ART Model * art_whisper_open(const wchar_t * path) {
    error.clear();
    whisper_log_set(log_message, nullptr);
    try {
        int count = ggml_backend_vk_get_device_count();
        if (!count) { error = "No compatible Vulkan GPU found. Update your graphics driver."; return nullptr; }
        // Prefer the card with most memory over a small integrated GPU.
        int best = 0;
        size_t most = 0;
        bool discrete = false;
        for (int i = 0; i < count; ++i) {
            size_t available, total;
            ggml_backend_vk_get_device_memory(i, &available, &total);
            auto device = ggml_backend_reg_dev_get(ggml_backend_vk_reg(), i);
            bool is_discrete = ggml_backend_dev_type(device) == GGML_BACKEND_DEVICE_TYPE_GPU;
            if ((is_discrete && !discrete) || (is_discrete == discrete && total > most)) {
                best = i; most = total; discrete = is_discrete;
            }
        }
        auto model = std::make_unique<Model>();
        char description[256] = {};
        ggml_backend_vk_get_device_description(best, description, sizeof(description));
        model->device = description;
        // Probe initialization first: do not silently accept CPU-only operation.
        auto backend = ggml_backend_vk_init(best);
        if (!backend) { error = "The Vulkan GPU could not be initialized."; return nullptr; }
        ggml_backend_free(backend);
        FILE * file = _wfopen(path, L"rb");
        if (!file) { error = "Could not open the downloaded Whisper Vulkan model."; return nullptr; }
        whisper_model_loader loader{};
        loader.context = file;
        loader.read = [](void * f, void * data, size_t size) { return fread(data, 1, size, static_cast<FILE *>(f)); };
        loader.eof = [](void * f) { return feof(static_cast<FILE *>(f)) != 0; };
        loader.close = [](void * f) { fclose(static_cast<FILE *>(f)); };
        auto params = whisper_context_default_params();
        params.use_gpu = true;
        params.gpu_device = best;
        params.flash_attn = true;
        model->ctx = whisper_init_with_params(&loader, params);
        if (!model->ctx) {
            if (error.empty()) error = "Whisper Vulkan could not load. Check GPU memory and graphics driver.";
            return nullptr;
        }
        return model.release();
    } catch (const std::exception & ex) { error = ex.what(); return nullptr; }
}
ART void art_whisper_free(Model * model) { delete model; }
ART const char * art_whisper_device(Model * model) { return model->device.c_str(); }
ART int art_whisper_run(Model * model, const float * samples, int count, const char * language) {
    error.clear();
    if (!model || !samples || count <= 0) { error = "Invalid speech samples."; return -1; }
    try {
        auto params = whisper_full_default_params(WHISPER_SAMPLING_BEAM_SEARCH);
        params.n_threads = 2;
        params.beam_search.beam_size = 5;
        params.language = language && *language ? language : "auto";
        params.translate = false;
        params.no_context = true;
        params.no_timestamps = true;
        params.print_progress = params.print_realtime = params.print_timestamps = params.print_special = false;
        int result = whisper_full(model->ctx, params, samples, count);
        if (result && error.empty()) error = "Whisper Vulkan inference failed or was stopped.";
        return result;
    } catch (const std::exception & ex) { error = ex.what(); return -1; }
}
ART const char * art_whisper_language(Model * model) {
    return whisper_lang_str(whisper_full_lang_id(model->ctx));
}
ART int art_whisper_segments(Model * model) { return whisper_full_n_segments(model->ctx); }
ART const char * art_whisper_text(Model * model, int segment) {
    return whisper_full_get_segment_text(model->ctx, segment);
}
ART float art_whisper_no_speech(Model * model, int segment) {
    return whisper_full_get_segment_no_speech_prob(model->ctx, segment);
}
ART float art_whisper_logprob(Model * model, int segment) {
    int count = whisper_full_n_tokens(model->ctx, segment);
    double sum = 0;
    for (int i = 0; i < count; ++i)
        sum += std::log(std::max(1e-10f, whisper_full_get_token_p(model->ctx, segment, i)));
    return count ? static_cast<float>(sum / count) : -100.f;
}
