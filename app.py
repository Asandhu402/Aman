from __future__ import annotations

import sys

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from local_engine import AmanEngine
from model_manager import ModelManager

SYSTEM_PROMPT = (
    "You are Aman, one local AI assistant. Be thoughtful, honest, curious, "
    "and clear. Distinguish what you know from what you are uncertain about. "
    "Do not claim to have memories, feelings, independent experiences, or "
    "actions that have not actually occurred. You may discuss ideas openly "
    "and should not invent facts."
)


class TaskWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, task, parent=None):
        super().__init__(parent)
        self.task = task

    def run(self):
        try:
            self.succeeded.emit(self.task(self.progress.emit))
        except Exception as exc:
            self.failed.emit(str(exc))


class AmanWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aman")
        self.resize(980, 720)
        self.engine = AmanEngine()
        self.model_manager = ModelManager()
        self.history: list[dict[str, str]] = []
        self.worker = None
        self._build_ui()
        self._set_status("Ready. Download the model and start the local engine.")

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Aman")
        title.setFont(QFont("Segoe UI", 23, QFont.Weight.Bold))
        subtitle = QLabel("One agent · Local AI · Private by design")
        subtitle.setStyleSheet("color: #888;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch(1)

        self.download_button = QPushButton("Download model")
        self.start_button = QPushButton("Start local AI")
        self.start_button.setObjectName("primary")
        header.addWidget(self.download_button)
        header.addWidget(self.start_button)
        layout.addLayout(header)

        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setAcceptRichText(False)
        self.chat.setPlaceholderText("Your conversation with Aman will appear here.")
        self.chat.setStyleSheet(
            "QTextEdit { background: #17191d; color: #e9e9e9; border: 1px solid #343840; "
            "border-radius: 12px; padding: 16px; font-size: 14px; }"
        )
        layout.addWidget(self.chat, 1)

        composer = QHBoxLayout()
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Message Aman…")
        self.message_input.returnPressed.connect(self.send_message)
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("primary")
        composer.addWidget(self.message_input, 1)
        composer.addWidget(self.send_button)
        layout.addLayout(composer)

        self.status = QLabel()
        self.status.setStyleSheet("color: #888; padding: 4px;")
        layout.addWidget(self.status)

        self.download_button.clicked.connect(self.download_model)
        self.start_button.clicked.connect(self.start_engine)
        self.send_button.clicked.connect(self.send_message)
        self.setCentralWidget(root)
        self.setStyleSheet(
            "QMainWindow { background: #101216; } "
            "QLabel { color: #ededed; } "
            "QPushButton { background: #30343c; color: white; border: 0; "
            "border-radius: 8px; padding: 10px 15px; } "
            "QPushButton#primary { background: #3769d6; } "
            "QPushButton:disabled { background: #555; color: #aaa; } "
            "QLineEdit { background: #1c1f25; color: white; border: 1px solid #3a3f49; "
            "border-radius: 9px; padding: 12px; font-size: 14px; }"
        )

    def _set_status(self, message: str):
        self.status.setText(message)

    def _append(self, speaker: str, message: str):
        self.chat.append(f"{speaker}\n{message}\n")
        self.chat.ensureCursorVisible()

    def _run_worker(self, task, success_message: str):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Aman", "Another task is already running.")
            return
        self.download_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.send_button.setEnabled(False)
        self.worker = TaskWorker(task, self)
        self.worker.progress.connect(self._set_status)
        self.worker.succeeded.connect(lambda _result: self._set_status(success_message))
        self.worker.failed.connect(self._worker_failed)
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

    def download_model(self):
        self._run_worker(
            lambda report: self.model_manager.ensure_model(report),
            "Model downloaded and SHA-256 verified.",
        )

    def start_engine(self):
        def start(report):
            report("Checking the pinned model and local llama.cpp runtime…")
            model_path = self.model_manager.ensure_model(report)
            self.engine.start(model_path, report)
        self._run_worker(start, "Aman's local model is ready.")

    def send_message(self):
        prompt = self.message_input.text().strip()
        if not prompt:
            return
        if not self.engine.is_ready:
            QMessageBox.information(
                self, "Aman", "Start the local AI first. No message has been sent."
            )
            return

        self.message_input.clear()
        self._append("You", prompt)
        self.history.append({"role": "user", "content": prompt})
        self.send_button.setEnabled(False)

        def reply(report):
            report("Aman is thinking on your computer…")
            return self.engine.chat(SYSTEM_PROMPT, self.history)

        self.worker = TaskWorker(reply, self)
        self.worker.progress.connect(self._set_status)
        self.worker.succeeded.connect(self._receive_reply)
        self.worker.failed.connect(self._worker_failed)
        self.worker.finished.connect(lambda: self.send_button.setEnabled(True))
        self.worker.start()

    def _receive_reply(self, answer: str):
        self.history.append({"role": "assistant", "content": answer})
        self._append("Aman", answer)
        self._set_status("Local model ready.")

    def _worker_failed(self, message: str):
        self._set_status("Task failed.")
        QMessageBox.critical(self, "Aman", message)

    def _worker_finished(self):
        self.download_button.setEnabled(True)
        self.start_button.setEnabled(True)
        self.send_button.setEnabled(True)

    def closeEvent(self, event):
        try:
            self.engine.stop()
        finally:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Aman")
    window = AmanWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
