import json
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from curated_assistant.domain.state import DialogueState


class ChatStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS states(user_id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS turns(user_id TEXT NOT NULL,request_id TEXT NOT NULL,request_hash TEXT NOT NULL,question TEXT NOT NULL,response TEXT NOT NULL,created_at REAL DEFAULT(unixepoch()),PRIMARY KEY(user_id,request_id))')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def load(self, user: str) -> DialogueState:
        with self.connection() as db:
            row = db.execute('SELECT payload FROM states WHERE user_id=?', (user,)).fetchone()
        return DialogueState.from_dict(json.loads(row['payload'])) if row else DialogueState(sender_id=user)

    def previous(self, user, request_id):
        with self.connection() as db:
            row = db.execute('SELECT request_hash,response FROM turns WHERE user_id=? AND request_id=?', (user, request_id)).fetchone()
        return (row['request_hash'], json.loads(row['response'])) if row else None

    def save(self, user, request_id, fingerprint, question, response, state):
        with self.connection() as db:
            db.execute('INSERT OR REPLACE INTO states VALUES(?,?)', (user, json.dumps(state.to_dict(), ensure_ascii=False)))
            db.execute('INSERT INTO turns(user_id,request_id,request_hash,question,response) VALUES(?,?,?,?,?)', (user, request_id, fingerprint, question, json.dumps(response, ensure_ascii=False)))

    def history(self, user):
        with self.connection() as db:
            rows = list(db.execute('SELECT question,response FROM turns WHERE user_id=? ORDER BY rowid DESC LIMIT 100', (user,)))
        result = []
        for row in reversed(rows):
            result.extend([{'role': 'user', 'text': row['question']}, {'role': 'assistant', **json.loads(row['response'])}])
        return result
