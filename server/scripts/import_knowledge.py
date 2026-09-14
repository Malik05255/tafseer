import argparse
import json
import sqlite3
from pathlib import Path

from app.knowledge import KnowledgeStore


def import_jsonl(input_path: Path, db_path: str) -> tuple[int, int]:
    KnowledgeStore(db_path)
    source_count = 0
    case_count = 0
    with sqlite3.connect(db_path) as con, input_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            kind = item.get("kind")
            if kind == "source":
                con.execute(
                    """
                    INSERT INTO knowledge_items(source_title, source_ref, source_type, text, notes, verified)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["source_title"],
                        item["source_ref"],
                        item.get("source_type", "reference"),
                        item["text"],
                        item.get("notes", ""),
                        1 if item.get("verified") is True else 0,
                    ),
                )
                source_count += 1
            elif kind == "case":
                con.execute(
                    """
                    INSERT INTO interpreted_cases(dream_summary, context_json, interpretation,
                                                  reasoning_summary, source_ref, verified)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["dream_summary"],
                        json.dumps(item.get("context", {}), ensure_ascii=False),
                        item["interpretation"],
                        item["reasoning_summary"],
                        item["source_ref"],
                        1 if item.get("verified") is True else 0,
                    ),
                )
                case_count += 1
            else:
                raise ValueError(f"Line {line_number}: unknown kind {kind!r}")
        con.commit()
    return source_count, case_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import verified Tafseer HAI knowledge JSONL")
    parser.add_argument("input", type=Path)
    parser.add_argument("--db", default="knowledge/tafseer.db")
    args = parser.parse_args()
    sources, cases = import_jsonl(args.input, args.db)
    print(f"Imported {sources} sources and {cases} interpreted cases")
