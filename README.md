# Aman

Aman is a single-agent local AI chat application for Windows 11.

## Model used

Aman uses the same pinned model as BabyMind:

- Model: `HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive`
- File: `Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf`
- Format: GGUF, Q4_K_M
- Size: approximately 2.71 GB
- Inference: llama.cpp, running locally on the computer

## App release

The Windows installer is being built for publication on the [GitHub Releases page](https://github.com/Asandhu402/Aman/releases). A release will be available there after the installer build succeeds.


## Experimental Intel NPU inference

Aman can optionally test an OpenVINO-enabled llama.cpp runtime on the Intel NPU. The normal bundled runtime remains the Vulkan build and is still used for Intel graphics and CPU fallback.

To enable the experimental NPU path, install the supported Intel NPU driver for Windows 11, then place a **Windows x64 llama.cpp build compiled with `GGML_OPENVINO=ON`** and its required runtime DLLs in Aman's `runtime-openvino/` directory, with `llama-server.exe` at the root (or in one unambiguous subdirectory). Aman sets `GGML_OPENVINO_DEVICE=NPU`, uses stateless execution, and tests the NPU before Vulkan and CPU. If the NPU runtime is absent or fails to start or benchmark, Aman continues with the available Vulkan/CPU modes.

The OpenVINO backend is experimental: supported GGUF operators, model architectures, quantizations, context sizes, and NPU driver versions vary. In particular, the bundled Q4_K_M model must pass an actual local NPU benchmark before NPU can be considered supported on a given machine. The NPU context defaults to 2048 tokens and can be changed with `AMAN_NPU_CONTEXT_SIZE`. This repository change adds runtime discovery and fallback handling; it does **not** bundle or build the OpenVINO runtime, and does not claim that NPU inference is active until the backend starts and completes a benchmark.

References:
- [llama.cpp OpenVINO backend and NPU limitations](https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/OPENVINO.md)
- [Intel NPU driver for Windows](https://www.intel.com/content/www/us/en/download/794734/intel-npu-driver-windows.html)
- [OpenVINO NPU setup](https://docs.openvino.ai/2026/get-started/install-openvino/configurations/configurations-intel-npu.html)
