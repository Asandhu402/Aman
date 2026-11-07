from __future__ import annotations

import html
import re
import sys

from PySide6.QtCore import QThread, Signal, QTimer, Qt, QPropertyAnimation, QEasingCurve, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QTextBrowser, QVBoxLayout, QWidget,
)

from local_engine import AmanEngine
from model_manager import ModelManager
from runtime_manager import RuntimeManager

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
            detail = str(exc).strip()
            if not detail and getattr(exc, "reason", None) is not None:
                detail = repr(exc.reason)
            self.failed.emit(f"{type(exc).__name__}: {detail or repr(exc)}")


class AmanWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aman")
        self.resize(1180, 780)
        self.setMinimumSize(820, 600)
        self.engine = AmanEngine()
        self.model_manager = ModelManager()
        self.runtime_manager = RuntimeManager()
        self.history: list[dict[str, str]] = []
        self.worker = None
        self._animations = []
        self._sidebar_animation = None
        self._last_answer = ""
        self._thinking_dots = 0
        self._thinking_timer = QTimer(self)
        self._thinking_timer.setInterval(420)
        self._thinking_timer.timeout.connect(self._animate_thinking)
        self._welcome_prompts = {
            "learn": "Teach me something interesting in simple words.",
            "write": "Help me write a clear and professional message.",
            "ideas": "Help me brainstorm some creative ideas.",
            "explain": "Explain a complex topic step by step.",
        }
        self._build_ui()
        self._set_status("Preparing your private local assistant…")

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ChatGPT-inspired compact navigation rail.
        self.sidebar = QFrame()
        sidebar = self.sidebar
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(0)
        sidebar.setMaximumWidth(238)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 22, 16, 18)
        side.setSpacing(14)

        brand = QHBoxLayout()
        mark = QLabel("A")
        mark.setObjectName("brandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(36, 36)
        brand_name = QLabel("Aman")
        brand_name.setObjectName("brandName")
        brand.addWidget(mark)
        brand.addWidget(brand_name)
        brand.addStretch(1)
        side.addLayout(brand)

        self.new_chat_button = QPushButton("+   New chat")
        self.new_chat_button.setObjectName("newChat")
        self.new_chat_button.clicked.connect(self.new_chat)
        side.addWidget(self.new_chat_button)

        section = QLabel("YOUR SPACE")
        section.setObjectName("sectionLabel")
        side.addWidget(section)

        current = QLabel("●   Current conversation")
        current.setObjectName("currentConversation")
        side.addWidget(current)
        side.addStretch(1)

        privacy = QLabel("◉  Runs locally on this device\n\nYour conversations stay on your computer.")
        privacy.setObjectName("privacyNote")
        privacy.setWordWrap(True)
        side.addWidget(privacy)
        outer.addWidget(sidebar)

        # Main conversation area.
        main = QWidget()
        main.setObjectName("mainArea")
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        topbar = QFrame()
        topbar.setObjectName("topbar")
        top_layout = QHBoxLayout(topbar)
        top_layout.setContentsMargins(22, 18, 30, 18)
        self.sidebar_toggle = QPushButton("☰")
        self.sidebar_toggle.setObjectName("iconButton")
        self.sidebar_toggle.setFixedSize(38, 38)
        self.sidebar_toggle.setToolTip("Show or hide sidebar")
        self.sidebar_toggle.clicked.connect(self.toggle_sidebar)
        top_layout.addWidget(self.sidebar_toggle)
        heading = QVBoxLayout()
        title = QLabel("New conversation")
        title.setObjectName("topTitle")
        subtitle = QLabel("A private space to think, explore and create")
        subtitle.setObjectName("topSubtitle")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        top_layout.addLayout(heading)
        top_layout.addStretch(1)
        self.copy_button = QPushButton("Copy last reply")
        self.copy_button.setObjectName("copyButton")
        self.copy_button.setToolTip("Copy Aman's latest response")
        self.copy_button.clicked.connect(self.copy_last_answer)
        self.copy_button.hide()
        top_layout.addWidget(self.copy_button)
        self.ready_badge = QLabel("●  Starting")
        self.ready_badge.setObjectName("statusBadge")
        top_layout.addWidget(self.ready_badge)
        main_layout.addWidget(topbar)

        self.chat = QTextBrowser()
        self.chat.setObjectName("conversation")
        self.chat.setOpenExternalLinks(False)
        self.chat.setOpenLinks(False)
        self.chat.setFrameShape(QFrame.Shape.NoFrame)
        self.chat.setViewportMargins(0, 0, 0, 0)
        self.chat.document().setDefaultStyleSheet(
            "body { color:#e8eaf0; font-family:'Segoe UI'; font-size:14px; } "
            ".welcome-wrap { max-width:720px; margin:72px auto 0 auto; text-align:center; } "
            ".welcome-mark { display:inline-block; background:#e8edf7; color:#171a20; border-radius:18px; padding:13px 18px; font-size:23px; font-weight:700; margin-bottom:20px; } "
            ".welcome { color:#f5f6fa; font-size:30px; font-weight:650; margin:8px 0 12px 0; } "
            ".hint { color:#929bad; font-size:14px; line-height:1.6; margin-bottom:30px; } "
            ".suggestions { text-align:center; margin:0 auto; } "
            ".suggestions a { display:inline-block; color:#dbe4f4; background:#202631; border:1px solid #343e4e; border-radius:13px; padding:13px 16px; margin:6px; text-decoration:none; font-size:12px; } "
            ".suggestions a:hover { background:#303b4d; border-color:#667b9b; color:#ffffff; } "
            ".row { margin:22px auto; max-width:760px; } "
            ".who { color:#a5b1c4; font-size:12px; font-weight:600; margin-bottom:9px; } "
            ".user { background:#252c38; border:1px solid #394456; border-radius:16px; padding:14px 17px; color:#f4f5f7; } "
            ".assistant { color:#e8eaf0; padding:5px 2px 18px 2px; line-height:1.8; } "
        )
        self.chat.anchorClicked.connect(self._welcome_link_clicked)
        self._show_welcome("Ask Aman anything. Your AI runs right here on your computer.")
        self.chat.setStyleSheet(
            "QTextBrowser { background:#111318; color:#e8eaf0; border:0; padding:20px 8%; }"
        )
        main_layout.addWidget(self.chat, 1)

        bottom = QFrame()
        bottom.setObjectName("bottomPanel")
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 12, 0, 18)
        bottom_layout.setSpacing(8)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("modelProgress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Preparing model · %p%")
        self.progress_bar.setMaximumWidth(760)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.hide()
        bottom_layout.addWidget(self.progress_bar, 0, Qt.AlignmentFlag.AlignHCenter)

        composer_frame = QFrame()
        composer_frame.setObjectName("composer")
        composer_frame.setMaximumWidth(800)
        composer_shadow = QGraphicsDropShadowEffect(composer_frame)
        composer_shadow.setBlurRadius(30)
        composer_shadow.setOffset(0, 5)
        composer_shadow.setColor(Qt.GlobalColor.black)
        composer_frame.setGraphicsEffect(composer_shadow)
        composer = QHBoxLayout(composer_frame)
        composer.setContentsMargins(16, 9, 9, 9)
        composer.setSpacing(10)
        self.message_input = QLineEdit()
        self.message_input.setObjectName("messageInput")
        self.message_input.setPlaceholderText("Message Aman…")
        self.message_input.returnPressed.connect(self.send_message)
        self.send_button = QPushButton("↑")
        self.send_button.setObjectName("sendButton")
        self.send_button.setFixedSize(42, 42)
        self.send_button.setToolTip("Send message")
        self.send_button.clicked.connect(self.send_message)
        composer.addWidget(self.message_input, 1)
        composer.addWidget(self.send_button)
        bottom_layout.addWidget(composer_frame, 0, Qt.AlignmentFlag.AlignHCenter)

        self.status = QLabel("Starting local AI…")
        self.status.setObjectName("footerStatus")
        self.status.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        bottom_layout.addWidget(self.status)
        main_layout.addWidget(bottom)

        outer.addWidget(main, 1)
        self.setCentralWidget(root)
        self._focus_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        self._focus_shortcut.activated.connect(self.message_input.setFocus)
        self._new_chat_shortcut = QShortcut(QKeySequence("Ctrl+Shift+N"), self)
        self._new_chat_shortcut.activated.connect(self.new_chat)
        self._copy_shortcut = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        self._copy_shortcut.activated.connect(self.copy_last_answer)
        self._root_opacity = QGraphicsOpacityEffect(root)
        self._root_opacity.setOpacity(0.0)
        root.setGraphicsEffect(self._root_opacity)
        self.setStyleSheet("""
            QMainWindow, QWidget#root { background:#101218; }
            QFrame#sidebar { background:#171a21; border-right:1px solid #292e38; }
            QLabel#brandMark { background:#e8edf7; color:#171a20; border-radius:11px; font-size:20px; font-weight:700; }
            QLabel#brandName { color:#f4f5f7; font-size:19px; font-weight:650; }
            QLabel#sectionLabel { color:#737d8e; font-size:10px; font-weight:700; letter-spacing:1px; margin-top:20px; }
            QLabel#currentConversation { color:#e7eaf0; background:#292e39; border-radius:8px; padding:11px 9px; font-size:12px; }
            QLabel#privacyNote { color:#8992a2; background:#20242d; border:1px solid #2d333e; border-radius:10px; padding:12px; font-size:11px; }
            QPushButton#newChat { background:#252a34; color:#f0f2f6; border:1px solid #3a414e; border-radius:9px; padding:12px; text-align:left; font-size:13px; }
            QPushButton#newChat:hover { background:#343c4b; border-color:#56647b; }
            QPushButton#newChat:pressed { background:#202630; }
            QFrame#topbar { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #151923,stop:0.55 #111318,stop:1 #171b25); border-bottom:1px solid #2a303c; }
            QLabel#topTitle { color:#f1f2f5; font-size:15px; font-weight:600; }
            QPushButton#iconButton { background:#202630; color:#dce3ef; border:1px solid #343d4c; border-radius:10px; font-size:17px; }
            QPushButton#iconButton:hover { background:#303949; }
            QPushButton#copyButton { background:#202630; color:#cbd5e4; border:1px solid #343d4c; border-radius:9px; padding:8px 11px; font-size:11px; }
            QPushButton#copyButton:hover { background:#303949; }
            QLabel#topSubtitle { color:#7f8999; font-size:11px; }
            QLabel#statusBadge { color:#a8b4c7; background:#202630; border:1px solid #303947; border-radius:12px; padding:7px 11px; font-size:11px; }
            QFrame#bottomPanel { background:#111318; }
            QFrame#composer { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #252c38,stop:1 #1a1f28); border:1px solid #465267; border-radius:20px; }
            QFrame#composer:hover { border-color:#58677f; }
            QLineEdit#messageInput { background:transparent; color:#f3f4f6; border:0; padding:9px 4px; font-size:14px; }
            QPushButton#sendButton { background:#e9edf5; color:#171a20; border:0; border-radius:13px; font-size:23px; font-weight:600; }
            QPushButton#sendButton:hover { background:#ffffff; }
            QPushButton#sendButton:pressed { background:#cbd5e6; }
            QPushButton:disabled { background:#525966; color:#aeb4bf; }
            QLabel#footerStatus { color:#747e8e; font-size:10px; }
            QProgressBar#modelProgress { background:#292f3a; border:0; border-radius:4px; }
            QProgressBar#modelProgress::chunk { background:#8da9e8; border-radius:4px; }
        """)

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_intro_animation_started", False):
            self._intro_animation_started = True
            self._animate_opacity(self._root_opacity, 0.0, 1.0, 420)

    def _animate_opacity(self, effect, start: float, end: float, duration: int):
        effect.setOpacity(start)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(duration)
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(lambda: self._animations.remove(animation) if animation in self._animations else None)
        self._animations.append(animation)
        animation.start()

    def _show_welcome(self, hint: str):
        self.chat.setHtml(
            "<div class='welcome-wrap'>"
            "<div class='welcome-mark'>A</div>"
            "<div class='welcome'>A little space for big ideas.</div>"
            f"<div class='hint'>{html.escape(hint)}</div>"
            "<div class='suggestions'>"
            "<a href='prompt:learn'>✦ &nbsp; Learn something</a>"
            "<a href='prompt:write'>✎ &nbsp; Write together</a>"
            "<a href='prompt:ideas'>◇ &nbsp; Brainstorm ideas</a>"
            "<a href='prompt:explain'>◎ &nbsp; Explain a topic</a>"
            "</div></div>"
        )

    def _welcome_link_clicked(self, url):
        link = url.toString()
        if link.startswith("prompt:"):
            key = link.replace("prompt:", "", 1)
            prompt = self._welcome_prompts.get(key)
            if prompt:
                self.message_input.setText(prompt)
                self.message_input.setFocus()
        elif url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)

    def toggle_sidebar(self):
        if self._sidebar_animation and self._sidebar_animation.state() == QPropertyAnimation.State.Running:
            self._sidebar_animation.stop()
        opening = not self.sidebar.isVisible()
        if opening:
            self.sidebar.show()
            start, end = 0, 238
        else:
            start, end = self.sidebar.width(), 0
        self._sidebar_animation = QPropertyAnimation(self.sidebar, b"maximumWidth", self)
        self._sidebar_animation.setDuration(220)
        self._sidebar_animation.setStartValue(start)
        self._sidebar_animation.setEndValue(end)
        self._sidebar_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        if not opening:
            self._sidebar_animation.finished.connect(lambda: self.sidebar.hide() if self.sidebar.maximumWidth() == 0 else None)
        self._sidebar_animation.start()

    def copy_last_answer(self):
        if self._last_answer:
            QApplication.clipboard().setText(self._last_answer)
            self._set_status("Latest reply copied to clipboard.")

    def _start_thinking(self):
        self._thinking_dots = 0
        self.status.setText("Aman is thinking on your computer")
        self._thinking_timer.start()

    def _animate_thinking(self):
        self._thinking_dots = (self._thinking_dots + 1) % 4
        self.status.setText("Aman is thinking on your computer" + "." * self._thinking_dots)

    def _stop_thinking(self):
        self._thinking_timer.stop()

    def _set_status(self, message: str):
        self.status.setText(message)

    def _handle_progress(self, message: str):
        self._set_status(message)
        match = re.search(r"Downloading model:\\s*(\\d{1,3})%", message)
        if match:
            value = min(100, int(match.group(1)))
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(value)
            self.progress_bar.setFormat(f"Downloading model · {value}%")
            self.progress_bar.show()
            self.ready_badge.setText("●  Downloading")
        elif "Downloading the pinned" in message:
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setFormat("Starting model download…")
            self.progress_bar.show()
            self.ready_badge.setText("●  Preparing")
        elif "Verifying" in message:
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setFormat("Verifying model…")
            self.progress_bar.show()
            self.ready_badge.setText("●  Verifying")
        elif "Local AI ready ·" in message:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat("Performance test complete")
            self.progress_bar.show()
            mode = message.split("Local AI ready ·", 1)[1].split("·", 1)[0].strip()
            self.ready_badge.setText(f"●  {mode}")
        elif "downloaded and verified" in message or "ready" in message.lower():
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat("Model ready")
            self.progress_bar.show()
            self.ready_badge.setText("●  Ready")

    def _append(self, speaker: str, message: str):
        # Never show hidden reasoning blocks in the conversation UI.
        message = re.sub(r"<think>.*?</think>", "", message, flags=re.I | re.S).strip()
        message = re.sub(r"</?think>", "", message, flags=re.I).strip()
        safe = html.escape(message).replace("\n", "<br>")
        if speaker == "You":
            block = f"<div class='row'><div class='who'>You</div><div class='user'>{safe}</div></div>"
        else:
            block = f"<div class='row'><div class='who'>✦ &nbsp; Aman</div><div class='assistant'>{safe}</div></div>"
        cursor = self.chat.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(block)
        cursor.insertBlock()
        self.chat.setTextCursor(cursor)
        self.chat.ensureCursorVisible()
        if not hasattr(self, "_chat_opacity"):
            self._chat_opacity = QGraphicsOpacityEffect(self.chat)
            self.chat.setGraphicsEffect(self._chat_opacity)
        self._animate_opacity(self._chat_opacity, 0.78, 1.0, 220)

    def _run_worker(self, task, success_message: str):
        if self.worker and self.worker.isRunning():
            return
        self.send_button.setEnabled(False)
        self.worker = TaskWorker(task, self)
        self.worker.progress.connect(self._handle_progress)
        self.worker.succeeded.connect(lambda _result: self._set_status(success_message))
        self.worker.failed.connect(self._worker_failed)
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

    def start_engine(self):
        def start(report):
            report("Checking the model and local runtime…")
            model_path = self.model_manager.ensure_model(report)
            self.runtime_manager.ensure_runtime(report)
            self.engine.start(model_path, report)
        self._run_worker(start, "Aman's local model is ready.")

    def send_message(self):
        prompt = self.message_input.text().strip()
        if not prompt:
            return
        if not self.engine.is_ready:
            self._set_status("Aman is still getting ready. You can chat in a moment.")
            return
        self.message_input.clear()
        if not self.history:
            self.chat.clear()
        self._append("You", prompt)
        self.history.append({"role": "user", "content": prompt})
        self.send_button.setEnabled(False)
        self._start_thinking()

        def reply(report):
            report("Aman is thinking on your computer…")
            return self.engine.chat(SYSTEM_PROMPT, self.history)

        self.worker = TaskWorker(reply, self)
        self.worker.progress.connect(self._handle_progress)
        self.worker.succeeded.connect(self._receive_reply)
        self.worker.failed.connect(self._worker_failed)
        self.worker.finished.connect(lambda: self.send_button.setEnabled(True))
        self.worker.start()

    def new_chat(self):
        if self.worker and self.worker.isRunning():
            return
        self.history.clear()
        self._last_answer = ""
        self.copy_button.hide()
        self.chat.clear()
        self._show_welcome("A fresh conversation. Choose a starting point or ask anything.")
        self._set_status("New conversation")

    def _receive_reply(self, answer: str):
        self._stop_thinking()
        clean = re.sub(r"<think>.*?</think>", "", answer, flags=re.I | re.S).strip()
        clean = re.sub(r"</?think>", "", clean, flags=re.I).strip()
        self.history.append({"role": "assistant", "content": clean})
        self._last_answer = clean
        self.copy_button.show()
        self._append("Aman", clean)
        self._set_status("Local model ready.")
        self.ready_badge.setText("●  Ready")

    def _worker_failed(self, message: str):
        self._stop_thinking()
        self._set_status("Something went wrong. Please try again.")
        self.ready_badge.setText("●  Needs attention")
        self.progress_bar.hide()
        QMessageBox.critical(self, "Aman", message)

    def _worker_finished(self):
        self.send_button.setEnabled(True)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Aman", "Please wait for the current task to finish before closing Aman.")
            event.ignore()
            return
        self.engine.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Aman")
    app.setFont(QFont("Segoe UI", 10))
    window = AmanWindow()
    window.show()
    QTimer.singleShot(0, window.start_engine)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
