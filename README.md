# Aman

Aman is a new, single-agent local AI project. The first milestone is a Windows 11 desktop chat application.

## Design goals

- One chat agent and one conversation identity.
- Local inference only; no paid APIs, API keys, or cloud model calls.
- Same model and inference approach used by the current BabyMind build.
- Model files and chat data stay on the user's computer.
- Later milestones will add persistent memory, self-reflection experiments, and autonomous research/development.

## Pinned local model

Aman is configured for the exact BabyMind model:

- Repository: [HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive](https://huggingface.co/HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive)
- File: `Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf`
- Format: GGUF, Q4_K_M
- Expected size: approximately 2.71 GB
- SHA-256: `79e28ecacf84e75b6056cf4059636d435aa9eb67795780f7b7dbc7d32a962741`
- Inference engine: llama.cpp `llama-server.exe`
- Local endpoint: `http://127.0.0.1:1235/v1`

The application verifies the model's SHA-256 before use. A different model file is rejected rather than silently substituted.

"Uncensored" describes the model fine-tune, not a guarantee that every possible prompt will be answered. Aman does not add a separate content-filter layer in this initial chat client.

## Windows 11 setup

1. Install 64-bit Python 3.11 or newer.
2. Run `setup.bat`.
3. Run `run.bat`.
4. In Aman, click **Install CPU runtime**. This downloads the official llama.cpp Windows x64 CPU bundle (release `b12177`) and verifies its SHA-256 before extraction.
5. Click **Download model**. The first download requires internet and at least 4.5 GB of free disk space.
6. Click **Start local AI**, then chat.

Aman stores its model under `%LOCALAPPDATA%\\Aman\\models`. The local llama.cpp runtime is extracted into the repository's `runtime` folder. The model and inference requests remain on your computer; internet is needed only for the first downloads.

## Current status

The initial Windows GUI, pinned-model downloader, runtime downloader, and local HTTP client are in the development branch. They still need a real Windows 11 run and model-response test before the app can be called verified.

## Planned milestones

1. Windows 11 local chat app using the pinned BabyMind model.
2. Persistent conversation and long-term memory.
3. One-agent self-model and measurable self-reflection experiments.
4. Autonomous research and development with explicit approval for consequential changes.

Aman is independent of the BabyMind source code. It reuses only the same pinned model and local llama.cpp inference approach.
