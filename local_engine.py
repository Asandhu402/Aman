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

    @property
    def is_ready(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def _runtime_path(self) -> Path:
        return Path(__file__).resolve().parent / "runtime" / "llama-server.exe"

    def start(self, model_path: Path, progress=None):
        report = progress or (lambda _: None)
        executable = self._runtime_path()
        if not executable.is_file():
            raise RuntimeError(
                "Aman could not find runtime\\llama-server.exe. "
                "Add a trusted Windows CPU build of llama.cpp there, then try again."
            )
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

        command = [
            str(executable), "--model", str(model_path),
            "--host", "127.0.0.1", "--port", str(self.port),
            "--ctx-size", os.getenv("AMAN_CONTEXT_SIZE", "4096"),
            "--parallel", "1", "--reasoning-format", "none",
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        report("Starting llama.cpp and loading the local model…")
        self.process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=creationflags,
        )

        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(
                    "llama-server.exe exited during startup. Check the runtime build, "
                    "model, and available memory."
                )
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/health", timeout=1
                ):
                    report("Local AI server is healthy.")
                    return
            except (urllib.error.URLError, TimeoutError, OSError):
                time.sleep(0.5)

        self.stop()
        raise RuntimeError("Timed out while loading the local model.")

    def chat(self, system_prompt: str, history: list[dict[str, str]]) -> str:
        payload = {
            "model": "local-model",
            "messages": [{"role": "system", "content": system_prompt}, *history],
            "temperature": 0.4,
            "top_p": 0.9,
            "max_tokens": 2048,
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

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.process = None
