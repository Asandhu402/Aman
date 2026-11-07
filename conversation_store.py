from __future__ import annotations
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

class ConversationStore:
    """SQLite storage for private, on-device conversations."""
    def __init__(self):
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData/Local"))
        folder = base / "Aman"
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / "conversations.sqlite3"
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL, updated_at TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE)")
            db.execute("CREATE INDEX IF NOT EXISTS messages_by_chat ON messages(conversation_id, id)")
    def _db(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db
    def _now(self):
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    def create_conversation(self, first_message):
        chat_id = uuid.uuid4().hex
        title = " ".join(first_message.split()).strip()[:52] or "New conversation"
        with self._db() as db:
            db.execute("INSERT INTO conversations VALUES (?, ?, ?)", (chat_id, title, self._now()))
        return chat_id
    def add_message(self, chat_id, role, content):
        with self._db() as db:
            db.execute("INSERT INTO messages(conversation_id, role, content) VALUES (?, ?, ?)", (chat_id, role, content))
            db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (self._now(), chat_id))
    def list_conversations(self):
        with self._db() as db:
            return [dict(x) for x in db.execute("SELECT id,title,updated_at FROM conversations ORDER BY updated_at DESC")]
    def get_messages(self, chat_id):
        with self._db() as db:
            return [dict(x) for x in db.execute("SELECT role,content FROM messages WHERE conversation_id=? ORDER BY id", (chat_id,))]
    def delete_conversation(self, chat_id):
        with self._db() as db:
            db.execute("DELETE FROM messages WHERE conversation_id=?", (chat_id,))
            db.execute("DELETE FROM conversations WHERE id=?", (chat_id,))
