import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "astro_memory.db"


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize():
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


def save_memory(content):
    content = content.strip()
    if not content:
        return False

    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM memories WHERE LOWER(TRIM(content)) = LOWER(TRIM(?))",
            (content,)
        ).fetchone()

        if existing:
            return False

        conn.execute(
            "INSERT INTO memories (content) VALUES (?)",
            (content,)
        )

    return True

def get_memories():
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, content, created_at FROM memories ORDER BY id DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def clear_memories():
    with connect() as conn:
        conn.execute("DELETE FROM memories")


def delete_memory(memory_id):
    with connect() as conn:
        cursor = conn.execute(
            "DELETE FROM memories WHERE id = ?",
            (memory_id,)
        )
        return cursor.rowcount > 0