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


## Automatic Intel NPU acceleration

On Windows, Aman checks whether a healthy Intel AI Boost/NPU device is present. If one is detected, it automatically downloads the official OpenVINO-enabled Windows x64 llama.cpp runtime matching the pinned Vulkan runtime, verifies the archive against its SHA-256 digest, and installs it locally. No manual runtime placement or build tools are required.

Aman then benchmarks OpenVINO NPU, Intel Vulkan graphics, and CPU thread configurations with the selected local model. It starts the fastest mode that successfully completes the benchmark and caches that choice. If NPU detection, download, driver initialization, model compatibility, or benchmarking fails, Aman continues with Vulkan and CPU. The OpenVINO NPU context defaults to 2048 tokens and can be changed with `AMAN_NPU_CONTEXT_SIZE`.

NPU support remains hardware-, driver-, model-, and quantization-dependent. In particular, the bundled Q4_K_M model must pass a real local NPU benchmark before Aman will select NPU. The runtime is downloaded on first startup only when a healthy Intel NPU is detected; the first download is about 100 MB. A successful benchmark is the evidence that NPU inference is active on that machine.

References:
- [Official llama.cpp OpenVINO backend](https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/OPENVINO.md)
- [Pinned official OpenVINO runtime release and SHA-256](https://github.com/ggml-org/llama.cpp/releases/tag/b12177)
- [Intel NPU driver for Windows](https://www.intel.com/content/www/us/en/download/794734/intel-npu-driver-windows.html)
