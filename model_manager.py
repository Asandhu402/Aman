from __future__ import annotations

import hashlib
import json
import os
import shutil
import ssl
import tempfile
import urllib.request

import certifi
from pathlib import Path
from typing import Callable

MODEL_URL = (
    "https://huggingface.co/HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive/"
    "resolve/c09cdbcdb1fefad6d335809d445621b5f5ba0c6e/"
    "Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf?download=true"
)
MODEL_FILENAME = "Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf"
MODEL_SHA256 = "79e28ecacf84e75b6056cf4059636d435aa9eb67795780f7b7dbc7d32a962741"
MAX_DOWNLOAD_BYTES = 3_500_000_000
CHUNK_SIZE = 4 * 1024 * 1024


class ModelManager:
    def __init__(self):
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData/Local"))
        self.model_dir = base / "Aman" / "models"
        self.model_path = self.model_dir / MODEL_FILENAME

    @staticmethod
    def sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @property
    def verification_marker(self) -> Path:
        return self.model_dir / ".model-verified.json"

    def _write_verification_marker(self, path: Path) -> None:
        try:
            stat = path.stat()
            marker = {
                "sha256": MODEL_SHA256,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
            temporary = self.verification_marker.with_suffix(".tmp")
            temporary.write_text(json.dumps(marker), encoding="utf-8")
            os.replace(temporary, self.verification_marker)
        except OSError:
            # A future launch can safely hash the file again if marker creation fails.
            pass

    def verify(self, path: Path) -> bool:
        if not path.is_file():
            return False
        stat = path.stat()
        try:
            marker = json.loads(self.verification_marker.read_text(encoding="utf-8"))
            if (
                marker.get("sha256") == MODEL_SHA256
                and marker.get("size") == stat.st_size
                and marker.get("mtime_ns") == stat.st_mtime_ns
            ):
                return True
        except (OSError, ValueError, TypeError):
            pass
        valid = self.sha256(path).lower() == MODEL_SHA256
        if valid:
            self._write_verification_marker(path)
        return valid

    def ensure_model(self, progress: Callable[[str], None] | None = None) -> Path:
        report = progress or (lambda _: None)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        if self.model_path.exists():
            report("Verifying the existing pinned model…")
            if self.verify(self.model_path):
                return self.model_path
            raise RuntimeError(
                f"The model at {self.model_path} failed its SHA-256 check. "
                "Aman will not overwrite or delete it."
            )

        if shutil.disk_usage(self.model_dir).free < 4_500_000_000:
            raise RuntimeError("Aman needs at least 4.5 GB of free disk space for the first download.")

        fd, temp_name = tempfile.mkstemp(
            prefix=".aman-model-", suffix=".part", dir=self.model_dir
        )
        os.close(fd)
        partial = Path(temp_name)
        request = urllib.request.Request(
            MODEL_URL,
            headers={"User-Agent": "Aman-Windows/0.1", "Accept": "application/octet-stream"},
        )
        try:
            report("Downloading the pinned 2.71 GB model…")
            digest = hashlib.sha256()
            downloaded = 0
            context = ssl.create_default_context(cafile=certifi.where())
            with urllib.request.urlopen(request, context=context, timeout=60) as response:
                total = int(response.headers.get("Content-Length", "0") or 0)
                if total < 0 or total > MAX_DOWNLOAD_BYTES:
                    raise RuntimeError("The model server reported an invalid download size.")
                with partial.open("wb") as output:
                    while True:
                        chunk = response.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        downloaded += len(chunk)
                        if downloaded > MAX_DOWNLOAD_BYTES:
                            raise RuntimeError("Model download exceeded the size limit.")
                        output.write(chunk)
                        digest.update(chunk)
                        if total:
                            report(f"Downloading model: {downloaded / total:.0%}")
            if digest.hexdigest().lower() != MODEL_SHA256:
                raise RuntimeError("Model SHA-256 verification failed; the partial download was discarded.")
            if self.model_path.exists():
                raise RuntimeError("The destination appeared during download; it was not overwritten.")
            os.replace(partial, self.model_path)
            self._write_verification_marker(self.model_path)
            report("Model downloaded and verified.")
            return self.model_path
        except Exception:
            partial.unlink(missing_ok=True)
            raise
