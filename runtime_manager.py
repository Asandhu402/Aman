from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

# Official llama.cpp Vulkan build. Intel integrated graphics can use Vulkan
# when a compatible Intel graphics driver is installed.
RUNTIME_URL = (
    "https://github.com/ggml-org/llama.cpp/releases/download/b12177/"
    "llama-b12177-bin-win-vulkan-x64.zip"
)
RUNTIME_SHA256 = "84f0a856431ba9c97eb73a03601f68ce3d509d0eda010ca30a71d3243124ac32"
RUNTIME_MAX_BYTES = 80_000_000
RUNTIME_MARKER = ".aman-vulkan-runtime-b12177"

# Official OpenVINO-enabled Windows x64 build matching the pinned Vulkan runtime.
OPENVINO_RUNTIME_URL = (
    "https://github.com/ggml-org/llama.cpp/releases/download/b12177/"
    "llama-b12177-bin-win-openvino-2026.4.1-x64.zip"
)
OPENVINO_RUNTIME_SHA256 = "b7b6c2aef19cc228f65d4a146ea5825b3d94de8418a2723406f6458531979505"
OPENVINO_RUNTIME_MAX_BYTES = 140_000_000
OPENVINO_RUNTIME_MARKER = ".aman-openvino-runtime-b12177"


class RuntimeManager:
    def __init__(self):
        self.runtime_dir = Path(__file__).resolve().parent / "runtime"
        self.executable = self.runtime_dir / "llama-server.exe"
        self.marker = self.runtime_dir / RUNTIME_MARKER


    @staticmethod
    def has_intel_npu() -> bool:
        """Detect a present, healthy Intel NPU through Windows Plug and Play."""
        if os.name != "nt":
            return False
        command = (
            "Get-PnpDevice -PresentOnly | Where-Object { "
            "$_.Status -eq 'OK' -and "
            "$_.FriendlyName -match 'Intel.*AI Boost|Neural Processing Unit|NPU' "
            "} | Select-Object -First 1 -ExpandProperty FriendlyName"
        )
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True, text=True, timeout=15, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return result.returncode == 0 and bool(result.stdout.strip())
        except (OSError, subprocess.SubprocessError):
            return False

    def ensure_openvino_runtime(self, progress=None) -> Path:
        """Download and verify the matching OpenVINO llama.cpp runtime once."""
        report = progress or (lambda _: None)
        runtime_dir = Path(__file__).resolve().parent / "runtime-openvino"
        executable = runtime_dir / "llama-server.exe"
        marker = runtime_dir / OPENVINO_RUNTIME_MARKER
        if executable.is_file() and marker.is_file():
            try:
                if marker.read_text(encoding="ascii").strip() == OPENVINO_RUNTIME_SHA256:
                    report("Verified OpenVINO NPU runtime is already installed.")
                    return executable
            except OSError:
                pass

        runtime_dir.mkdir(parents=True, exist_ok=True)
        fd, archive_name = tempfile.mkstemp(
            prefix=".aman-openvino-", suffix=".zip", dir=runtime_dir
        )
        os.close(fd)
        archive = Path(archive_name)
        staging = Path(tempfile.mkdtemp(prefix="aman-openvino-stage-", dir=runtime_dir))
        try:
            report("Intel NPU detected · downloading verified OpenVINO runtime (about 100 MB)…")
            request = urllib.request.Request(
                OPENVINO_RUNTIME_URL,
                headers={"User-Agent": "Aman-Windows/0.1", "Accept": "application/octet-stream"},
            )
            digest = hashlib.sha256()
            downloaded = 0
            with urllib.request.urlopen(request, timeout=90) as response:
                with archive.open("wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        downloaded += len(chunk)
                        if downloaded > OPENVINO_RUNTIME_MAX_BYTES:
                            raise RuntimeError("The OpenVINO runtime archive exceeded its size limit.")
                        output.write(chunk)
                        digest.update(chunk)
            if digest.hexdigest().lower() != OPENVINO_RUNTIME_SHA256:
                raise RuntimeError("The OpenVINO runtime failed SHA-256 verification.")

            report("Verifying and extracting the OpenVINO NPU runtime…")
            with zipfile.ZipFile(archive) as bundle:
                for member in bundle.infolist():
                    target = (staging / member.filename).resolve()
                    if not target.is_relative_to(staging.resolve()):
                        raise RuntimeError("The OpenVINO archive contains an unsafe path.")
                bundle.extractall(staging)

            matches = list(staging.rglob("llama-server.exe"))
            if len(matches) != 1:
                raise RuntimeError("The verified OpenVINO archive did not contain exactly one llama-server.exe.")
            source_root = matches[0].parent
            for item in source_root.iterdir():
                destination = runtime_dir / item.name
                if destination.exists():
                    if destination.is_dir():
                        shutil.rmtree(destination)
                    else:
                        destination.unlink()
                if item.is_dir():
                    shutil.copytree(item, destination)
                else:
                    shutil.copy2(item, destination)
            if not executable.is_file():
                raise RuntimeError("The OpenVINO runtime was not installed at the expected path.")
            marker.write_text(OPENVINO_RUNTIME_SHA256, encoding="ascii")
            report("OpenVINO NPU runtime downloaded, verified, and installed.")
            return executable
        finally:
            archive.unlink(missing_ok=True)
            shutil.rmtree(staging, ignore_errors=True)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def ensure_runtime(self, progress=None) -> Path:
        report = progress or (lambda _: None)
        if self.executable.is_file() and self.marker.is_file():
            return self.executable

        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        fd, archive_name = tempfile.mkstemp(
            prefix=".aman-llama-", suffix=".zip", dir=self.runtime_dir
        )
        os.close(fd)
        archive = Path(archive_name)
        staging = Path(tempfile.mkdtemp(prefix="aman-llama-stage-", dir=self.runtime_dir))
        try:
            report("Downloading official llama.cpp Vulkan runtime for Intel graphics…")
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
                            raise RuntimeError("The Vulkan runtime archive exceeded its size limit.")
                        output.write(chunk)
                        digest.update(chunk)
            if digest.hexdigest().lower() != RUNTIME_SHA256:
                raise RuntimeError("The official llama.cpp Vulkan runtime failed SHA-256 verification.")

            report("Verifying and extracting Vulkan runtime…")
            with zipfile.ZipFile(archive) as bundle:
                for member in bundle.infolist():
                    target = (staging / member.filename).resolve()
                    if not target.is_relative_to(staging.resolve()):
                        raise RuntimeError("The runtime archive contains an unsafe path.")
                bundle.extractall(staging)

            matches = list(staging.rglob("llama-server.exe"))
            if len(matches) != 1:
                raise RuntimeError("The verified Vulkan runtime did not contain exactly one llama-server.exe.")

            source_root = matches[0].parent
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
            self.marker.write_text(RUNTIME_SHA256, encoding="ascii")
            report("Vulkan runtime installed and verified.")
            return self.executable
        finally:
            archive.unlink(missing_ok=True)
            shutil.rmtree(staging, ignore_errors=True)
