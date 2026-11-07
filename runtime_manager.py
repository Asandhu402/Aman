from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

RUNTIME_URL = (
    "https://github.com/ggml-org/llama.cpp/releases/download/b12177/"
    "llama-b12177-bin-win-cpu-x64.zip"
)
RUNTIME_SHA256 = "2d53212b57ccfc50128ec2e704c8ae44fb12df5206a731eef7be63f7669ebc74"
RUNTIME_MAX_BYTES = 100_000_000


class RuntimeManager:
    def __init__(self):
        self.runtime_dir = Path(__file__).resolve().parent / "runtime"
        self.executable = self.runtime_dir / "llama-server.exe"

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def ensure_runtime(self, progress=None) -> Path:
        report = progress or (lambda _: None)
        if self.executable.is_file():
            return self.executable

        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        fd, archive_name = tempfile.mkstemp(
            prefix=".aman-llama-", suffix=".zip", dir=self.runtime_dir
        )
        os.close(fd)
        archive = Path(archive_name)
        staging = Path(tempfile.mkdtemp(prefix="aman-llama-stage-", dir=self.runtime_dir))
        try:
            report("Downloading official llama.cpp Windows CPU runtime…")
            request = urllib.request.Request(
                RUNTIME_URL,
                headers={"User-Agent": "Aman-Windows/0.1", "Accept": "application/octet-stream"},
            )
            digest = hashlib.sha256()
            downloaded = 0
            with urllib.request.urlopen(request, timeout=60) as response:
                with archive.open("wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        downloaded += len(chunk)
                        if downloaded > RUNTIME_MAX_BYTES:
                            raise RuntimeError("The llama.cpp runtime archive exceeded its size limit.")
                        output.write(chunk)
                        digest.update(chunk)
            if digest.hexdigest().lower() != RUNTIME_SHA256:
                raise RuntimeError("The official llama.cpp runtime failed SHA-256 verification.")

            report("Verifying and extracting llama.cpp…")
            with zipfile.ZipFile(archive) as bundle:
                for member in bundle.infolist():
                    target = (staging / member.filename).resolve()
                    if not target.is_relative_to(staging.resolve()):
                        raise RuntimeError("The runtime archive contains an unsafe path.")
                bundle.extractall(staging)

            matches = list(staging.rglob("llama-server.exe"))
            if len(matches) != 1:
                raise RuntimeError("The verified runtime archive did not contain exactly one llama-server.exe.")

            source_root = matches[0].parent
            # Keep all DLLs beside the server; they are part of the official CPU bundle.
            for item in source_root.iterdir():
                destination = self.runtime_dir / item.name
                if destination.exists():
                    if destination.is_dir():
                        shutil.rmtree(destination)
                    else:
                        destination.unlink()
                if item.is_dir():
                    shutil.copytree(item, destination)
                else:
                    shutil.copy2(item, destination)

            if not self.executable.is_file():
                raise RuntimeError("llama-server.exe was not installed at the expected runtime path.")
            report("Official llama.cpp CPU runtime installed and verified.")
            return self.executable
        finally:
            archive.unlink(missing_ok=True)
            shutil.rmtree(staging, ignore_errors=True)
