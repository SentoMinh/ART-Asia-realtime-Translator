cmake_minimum_required(VERSION 3.21)
project(art_whisper_vulkan LANGUAGES C CXX)

# Keep the C ABI in bridge.cpp tied to this reviewed upstream revision.
include(FetchContent)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(GGML_VULKAN ON CACHE BOOL "" FORCE)
set(GGML_NATIVE OFF CACHE BOOL "" FORCE)
set(GGML_AVX OFF CACHE BOOL "" FORCE)
set(GGML_AVX2 OFF CACHE BOOL "" FORCE)
set(GGML_FMA OFF CACHE BOOL "" FORCE)
set(GGML_F16C OFF CACHE BOOL "" FORCE)
set(GGML_BMI2 OFF CACHE BOOL "" FORCE)
set(GGML_SSE42 OFF CACHE BOOL "" FORCE)
set(GGML_OPENMP OFF CACHE BOOL "" FORCE)
FetchContent_Declare(whisper
    GIT_REPOSITORY https://github.com/ggml-org/whisper.cpp.git
    GIT_TAG 306c88f4d1286aec1bf96e544632897886af5501
    BINARY_DIR "${CMAKE_BINARY_DIR}/w")
FetchContent_MakeAvailable(whisper)
configure_file("${whisper_SOURCE_DIR}/LICENSE" "${CMAKE_BINARY_DIR}/whisper.cpp-LICENSE.txt" COPYONLY)
add_library(art_whisper_vulkan SHARED bridge.cpp)
target_compile_features(art_whisper_vulkan PRIVATE cxx_std_17)
target_link_libraries(art_whisper_vulkan PRIVATE whisper ggml-vulkan)
