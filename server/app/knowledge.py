import json
import re
import sqlite3
from pathlib import Path

from .config import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_title TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    source_type TEXT NOT NULL,
    text TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    verified INTEGER NOT NULL DEFAULT 0
);
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
    text, source_title, source_ref, content='knowledge_items', content_rowid='id', tokenize='unicode61'
);
CREATE TRIGGER IF NOT EXISTS knowledge_ai AFTER INSERT ON knowledge_items BEGIN
    INSERT INTO knowledge_fts(rowid, text, source_title, source_ref)
    VALUES (new.id, new.text, new.source_title, new.source_ref);
END;

CREATE TABLE IF NOT EXISTS interpreted_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dream_summary TEXT NOT NULL,
    context_json TEXT NOT NULL DEFAULT '{}',
    interpretation TEXT NOT NULL,
    reasoning_summary TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0
);
CREATE VIRTUAL TABLE IF NOT EXISTS cases_fts USING fts5(
    dream_summary, interpretation, reasoning_summary,
    content='interpreted_cases', content_rowid='id', tokenize='unicode61'
);
CREATE TRIGGER IF NOT EXISTS cases_ai AFTER INSERT ON interpreted_cases BEGIN
    INSERT INTO cases_fts(rowid, dream_summary, interpretation, reasoning_summary)
    VALUES (new.id, new.dream_summary, new.interpretation, new.reasoning_summary);
END;
"""


class KnowledgeStore:
    def __init__(self, path: str | None = None) -> None:
        self.path = Path(path or settings.knowledge_db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    @staticmethod
    def _query(text: str) -> str:
        words = re.findall(r"[\w\u0600-\u06FF]{2,}", text.lower())
        # FTS OR improves recall; downstream model must reason over context rather than count matches.
        return " OR ".join(f'"{word}"' for word in dict.fromkeys(words[:24]))

    def retrieve(self, dream: str, limit: int = 8) -> list[dict]:
        q = self._query(dream)
        if not q:
            return []
        results: list[dict] = []
        with self._connect() as con:
            try:
                rows = con.execute(
                    """
                    SELECT k.source_title, k.source_ref, k.source_type, k.text, k.notes,
                           bm25(knowledge_fts) AS score
                    FROM knowledge_fts
                    JOIN knowledge_items k ON k.id = knowledge_fts.rowid
                    WHERE knowledge_fts MATCH ? AND k.verified = 1
                    ORDER BY score LIMIT ?
                    """,
                    (q, limit),
                ).fetchall()
                for row in rows:
                    results.append({"kind": "source", **dict(row)})
            except sqlite3.OperationalError:
                pass

            try:
                rows = con.execute(
                    """
                    SELECT c.dream_summary, c.context_json, c.interpretation,
                           c.reasoning_summary, c.source_ref, bm25(cases_fts) AS score
                    FROM cases_fts
                    JOIN interpreted_cases c ON c.id = cases_fts.rowid
                    WHERE cases_fts MATCH ? AND c.verified = 1
                    ORDER BY score LIMIT ?
                    """,
                    (q, max(3, limit // 2)),
                ).fetchall()
                for row in rows:
                    item = dict(row)
                    try:
                        item["context"] = json.loads(item.pop("context_json"))
                    except Exception:
                        item["context"] = {}
                    results.append({"kind": "case", **item})
            except sqlite3.OperationalError:
                pass
        return results
