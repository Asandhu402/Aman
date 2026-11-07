from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


class AmanEngine:
    def __init__(self):
        self.process: subprocess.Popen | None = None
        self.port = int(os.getenv("AMAN_LLAMA_PORT", "1235"))
        self.base_url = f"http://127.0.0.1:{self.port}/v1"
        self.acceleration = "Not started"
        self.generation_speed = 0.0
        self.selected_threads: int | None = None
        self.backend_device = "CPU/Vulkan"

    @property
    def is_ready(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def _openvino_runtime_path(self) -> Path | None:
        root = Path(__file__).resolve().parent / "runtime-openvino"
        direct = root / "llama-server.exe"
        if direct.is_file():
            return direct
        matches = list(root.rglob("llama-server.exe")) if root.exists() else []
        return matches[0] if len(matches) == 1 else None

    def _runtime_path(self) -> Path:
        runtime_dir = Path(__file__).resolve().parent / "runtime"
        direct = runtime_dir / "llama-server.exe"
        if direct.is_file():
            return direct
        matches = list(runtime_dir.rglob("llama-server.exe")) if runtime_dir.exists() else []
        if len(matches) == 1:
            return matches[0]
        return direct

    def _wait_until_healthy(self, timeout: int = 180) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process is None or self.process.poll() is not None:
                return False
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/health", timeout=1
                ):
                    return True
            except (urllib.error.URLError, TimeoutError, OSError):
                time.sleep(0.5)
        return False

    def _launch(
        self, executable: Path, model_path: Path, gpu_layers: int,
        report, threads: int | None = None, runtime_env: dict[str, str] | None = None,
        context_size: int | None = None,
    ) -> bool:
        command = [
            str(executable), "--model", str(model_path),
            "--host", "127.0.0.1", "--port", str(self.port),
            "--ctx-size", str(context_size or os.getenv("AMAN_CONTEXT_SIZE", "4096")),
            "--parallel", "1", "--reasoning-format", "none",
            "--n-gpu-layers", str(gpu_layers),
        ]
        if threads is not None:
            command.extend(["--threads", str(threads), "--threads-batch", str(threads)])
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process_env = os.environ.copy()
        if runtime_env:
            process_env.update(runtime_env)
        self.process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=creationflags, env=process_env,
        )
        if self._wait_until_healthy():
            return True
        self.stop()
        return False

    def _benchmark(self) -> float:
        payload = {
            "model": "local-model",
            "messages": [
                {"role": "system", "content": "You are a concise assistant."},
                {"role": "user", "content": "Write a short paragraph about why clean energy matters."},
            ],
            "temperature": 0,
            "max_tokens": 64,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        started = time.perf_counter()
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))
        elapsed = max(time.perf_counter() - started, 0.001)
        usage = result.get("usage", {})
        tokens = usage.get("completion_tokens", 0)
        if not tokens:
            raise RuntimeError("The local server did not report benchmark token usage.")
        return tokens / elapsed

    def _performance_cache_path(self) -> Path:
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData/Local"))
        folder = base / "Aman"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / "performance.json"

    def _load_cached_choice(self, executable: Path, model_path: Path, npu_executable: Path | None = None):
        cache_path = self._performance_cache_path()
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            model_stat = model_path.stat()
            selected_runtime = Path(cache.get("runtime_path", str(executable)))
            runtime_stat = selected_runtime.stat()
            current_npu_mtime = (
                npu_executable.stat().st_mtime_ns
                if npu_executable is not None and npu_executable.is_file() else None
            )
            if (
                cache.get("model_path") == str(model_path.resolve())
                and cache.get("model_size") == model_stat.st_size
                and cache.get("model_mtime_ns") == model_stat.st_mtime_ns
                and cache.get("runtime_mtime_ns") == runtime_stat.st_mtime_ns
                and cache.get("npu_runtime_mtime_ns") == current_npu_mtime
            ):
                return (
                    str(cache["label"]), int(cache["gpu_layers"]),
                    cache.get("threads"), float(cache.get("speed", 0.0)),
                    selected_runtime,
                )
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def _save_cached_choice(self, executable: Path, model_path: Path, choice, npu_executable: Path | None = None):
        label, gpu_layers, threads, speed = choice
        model_stat = model_path.stat()
        runtime_stat = executable.stat()
        npu_runtime_mtime = (
            npu_executable.stat().st_mtime_ns
            if npu_executable is not None and npu_executable.is_file() else None
        )
        payload = {
            "model_path": str(model_path.resolve()),
            "model_size": model_stat.st_size,
            "model_mtime_ns": model_stat.st_mtime_ns,
            "runtime_path": str(executable.resolve()),
            "runtime_mtime_ns": runtime_stat.st_mtime_ns,
            "npu_runtime_mtime_ns": npu_runtime_mtime,
            "label": label,
            "gpu_layers": gpu_layers,
            "threads": threads,
            "speed": speed,
        }
        self._performance_cache_path().write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    def start(self, model_path: Path, progress=None):
        report = progress or (lambda _: None)
        executable = self._runtime_path()
        if not executable.is_file():
            raise RuntimeError("Aman could not find llama-server.exe in its local runtime.")
        if not model_path.is_file():
            raise RuntimeError(f"The model file does not exist: {model_path}")
        if self.process and self.process.poll() is None:
            return

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind(("127.0.0.1", self.port))
        except OSError as exc:
            raise RuntimeError(
                f"Local port {self.port} is already in use. Close the other service "
                "or set AMAN_LLAMA_PORT to a free port."
            ) from exc

        openvino_executable = self._openvino_runtime_path()
        cached = self._load_cached_choice(executable, model_path, openvino_executable)
        if cached is not None:
            label, gpu_layers, threads, speed, selected_runtime = cached
            selected_env = None
            selected_context = None
            if label == "OpenVINO NPU":
                selected_env = {
                    "GGML_OPENVINO_DEVICE": "NPU",
                    "GGML_OPENVINO_STATEFUL_EXECUTION": "0",
                    "GGML_OPENVINO_CACHE_DIR": str(
                        Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData/Local"))
                        / "Aman" / "openvino-cache"
                    ),
                }
                selected_context = int(os.getenv("AMAN_NPU_CONTEXT_SIZE", "2048"))
            report(f"Starting with your previously benchmarked {label} settings…")
            if self._launch(selected_runtime, model_path, gpu_layers, report, threads, selected_env, selected_context):
                self.acceleration = label
                self.backend_device = "NPU" if label == "OpenVINO NPU" else label
                self.generation_speed = speed
                self.selected_threads = threads
                report(f"Local AI ready · {label} · cached benchmark {speed:.1f} tokens/second.")
                return
            report("Saved performance settings did not start; testing available modes again.")

        # Benchmark only when the model/runtime or available hardware changed.
        candidates = []
        if openvino_executable is not None:
            cache_dir = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Aman" / "openvino-cache"
            candidates.append(("OpenVINO NPU", openvino_executable, 0, None, {
                "GGML_OPENVINO_DEVICE": "NPU",
                "GGML_OPENVINO_STATEFUL_EXECUTION": "0",
                "GGML_OPENVINO_CACHE_DIR": str(cache_dir),
            }, int(os.getenv("AMAN_NPU_CONTEXT_SIZE", "2048"))))
        candidates.extend([
            ("Vulkan GPU", executable, 99, None, None, None),
            ("CPU · 8 threads", executable, 0, 8, None, None),
            ("CPU · 10 threads", executable, 0, 10, None, None),
            ("CPU · 12 threads", executable, 0, 12, None, None),
        ])
        results: list[tuple[float, str, int, int | None, Path, dict[str, str] | None, int | None]] = []
        for label, candidate_executable, gpu_layers, threads, runtime_env, context_size in candidates:
            report(f"Benchmarking {label}…")
            if not self._launch(candidate_executable, model_path, gpu_layers, report, threads, runtime_env, context_size):
                report(f"{label} could not start; skipping this option.")
                continue
            try:
                speed = self._benchmark()
                results.append((speed, label, gpu_layers, threads, candidate_executable, runtime_env, context_size))
                report(f"{label}: {speed:.1f} tokens/second.")
            except Exception as exc:
                report(f"{label} benchmark failed: {exc}")
            finally:
                self.stop()

        if not results:
            raise RuntimeError(
                "Aman could not benchmark either Intel Vulkan or CPU inference. "
                "Check the Intel graphics driver and available memory."
            )

        speed, label, gpu_layers, threads, selected_executable, selected_env, selected_context = max(results, key=lambda item: item[0])
        self._save_cached_choice(selected_executable, model_path, (label, gpu_layers, threads, speed), openvino_executable)
        report(f"Fastest tested mode: {label} at {speed:.1f} tokens/second. Starting it…")
        if not self._launch(selected_executable, model_path, gpu_layers, report, threads, selected_env, selected_context):
            raise RuntimeError(f"Aman benchmarked {label} successfully but could not restart it.")
        self.acceleration = label
        self.backend_device = "NPU" if label == "OpenVINO NPU" else label
        self.generation_speed = speed
        self.selected_threads = threads
        report(f"Local AI ready · {label} · benchmark {speed:.1f} tokens/second.")

    def chat(self, system_prompt: str, history: list[dict[str, str]]) -> str:
        # Keep recent context bounded so every turn does not re-process an
        # ever-growing transcript. Saved history remains complete on disk.
        recent_history = history[-12:]
        payload = {
            "model": "local-model",
            "messages": [{"role": "system", "content": system_prompt}, *recent_history],
            "temperature": 0.4,
            "top_p": 0.9,
            "max_tokens": 1024,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                result = json.loads(response.read().decode("utf-8"))
            answer = result["choices"][0]["message"]["content"]
            if not isinstance(answer, str) or not answer.strip():
                raise RuntimeError("The local model returned an empty answer.")
            return answer.strip()
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Could not reach Aman's local model server: {exc}") from exc
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("The local model returned an invalid chat response.") from exc

    def chat_stream(self, system_prompt: str, history: list[dict[str, str]], on_chunk):
        """Stream generated text from the local llama.cpp OpenAI-compatible endpoint."""
        recent_history = history[-12:]
        payload = {
            "model": "local-model",
            "messages": [{"role": "system", "content": system_prompt}, *recent_history],
            "temperature": 0.4,
            "top_p": 0.9,
            "max_tokens": 1024,
            "stream": True,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            method="POST",
        )
        pieces = []
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        pieces.append(content)
                        on_chunk(content)
            answer = "".join(pieces).strip()
            if not answer:
                raise RuntimeError("The local model returned an empty answer.")
            return answer
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Could not reach Aman's local model server: {exc}") from exc

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.process = None
