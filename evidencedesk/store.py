"""SQLite conversation history, isolated by an opaque session identifier."""

import json
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import time


class ConversationStore:
    def __init__(self, directory):
        Path(directory).mkdir(parents=True, exist_ok=True)
        self.path = Path(directory) / "conversations.sqlite"
        with self.connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY, session_id TEXT NOT NULL,
                question TEXT NOT NULL, response_json TEXT NOT NULL,
                created_at REAL NOT NULL)""")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def history(self, session_id, limit=8):
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT question,response_json FROM turns WHERE session_id=? ORDER BY id DESC LIMIT ?",
                (session_id, int(limit)),
            ).fetchall()
        return [{"question": q, "response": json.loads(r)} for q, r in reversed(rows)]

    def save(self, session_id, question, response):
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO turns(session_id,question,response_json,created_at) VALUES(?,?,?,?)",
                (session_id, question, json.dumps(response, ensure_ascii=False), time.time()),
            )
