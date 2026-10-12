"""SQLite 存储：身体数据历史版本、饮食/运动记录、报告。"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    effective_date TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_profiles_date ON profiles(effective_date);
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    meal TEXT,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    grams REAL,
    minutes REAL,
    kcal REAL NOT NULL,
    protein_g REAL,
    carb_g REAL,
    fat_g REAL,
    confidence TEXT,
    basis TEXT,
    raw_text TEXT,
    llm_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entries_date ON entries(date);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    stats TEXT NOT NULL,
    analysis TEXT,
    created_at TEXT NOT NULL
);
"""

ENTRY_COLUMNS = ("date", "meal", "kind", "name", "grams", "minutes", "kcal", "protein_g",
                 "carb_g", "fat_g", "confidence", "basis", "raw_text", "llm_name")
EDITABLE = ("name", "meal", "grams", "minutes", "kcal", "protein_g", "carb_g", "fat_g")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path):
        self._lock = threading.RLock()
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # ---------- 身体数据 ----------
    def profile_on(self, day: str) -> dict:
        with self._lock:
            row = self.conn.execute(
                "SELECT effective_date, data FROM profiles WHERE effective_date <= ? "
                "ORDER BY effective_date DESC, id DESC LIMIT 1", (day,)).fetchone()
        if not row:
            return {}
        return {**json.loads(row["data"]), "effective_date": row["effective_date"]}

    def add_profile_version(self, effective_date: str, data: dict) -> None:
        with self._lock:
            self.conn.execute("INSERT INTO profiles (effective_date, data, created_at) VALUES (?, ?, ?)",
                              (effective_date, json.dumps(data, ensure_ascii=False), _now()))
            self.conn.commit()

    def profile_history(self) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT id, effective_date, data, created_at FROM profiles ORDER BY effective_date DESC, id DESC"
            ).fetchall()
        return [{"id": r["id"], "effective_date": r["effective_date"], "data": json.loads(r["data"]),
                 "created_at": r["created_at"]} for r in rows]

    # ---------- 记录 ----------
    def insert_entries(self, rows: list[dict]) -> list[int]:
        ids = []
        now = _now()
        with self._lock:
            for row in rows:
                values = {c: row.get(c) for c in ENTRY_COLUMNS}
                values["created_at"] = now
                values["updated_at"] = now
                cols = ", ".join(values)
                marks = ", ".join("?" for _ in values)
                cur = self.conn.execute(f"INSERT INTO entries ({cols}) VALUES ({marks})", list(values.values()))
                ids.append(int(cur.lastrowid))
            self.conn.commit()
        return ids

    def list_entries(self, start: str, end: str) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM entries WHERE date BETWEEN ? AND ? ORDER BY date, id", (start, end)).fetchall()
        return [dict(r) for r in rows]

    def get_entry(self, eid: int) -> dict | None:
        with self._lock:
            row = self.conn.execute("SELECT * FROM entries WHERE id = ?", (eid,)).fetchone()
        return dict(row) if row else None

    def update_entry(self, eid: int, fields: dict) -> bool:
        allowed = {k: v for k, v in fields.items() if k in EDITABLE}
        if not allowed:
            return False
        allowed["updated_at"] = _now()
        sets = ", ".join(f"{k} = ?" for k in allowed)
        with self._lock:
            cur = self.conn.execute(f"UPDATE entries SET {sets} WHERE id = ?", [*allowed.values(), eid])
            self.conn.commit()
        return cur.rowcount > 0

    def delete_entry(self, eid: int) -> bool:
        with self._lock:
            cur = self.conn.execute("DELETE FROM entries WHERE id = ?", (eid,))
            self.conn.commit()
        return cur.rowcount > 0

    # ---------- 报告 ----------
    def save_report(self, period: str, start: str, end: str, stats: dict, analysis: dict | None) -> int:
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO reports (period, start, end, stats, analysis, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (period, start, end, json.dumps(stats, ensure_ascii=False),
                 json.dumps(analysis, ensure_ascii=False) if analysis is not None else None, _now()))
            self.conn.commit()
            return int(cur.lastrowid)

    def list_reports(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT id, period, start, end, created_at FROM reports ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get_report(self, rid: int) -> dict | None:
        with self._lock:
            row = self.conn.execute("SELECT * FROM reports WHERE id = ?", (rid,)).fetchone()
        if not row:
            return None
        return {"id": row["id"], "period": row["period"], "start": row["start"], "end": row["end"],
                "stats": json.loads(row["stats"]),
                "analysis": json.loads(row["analysis"]) if row["analysis"] else None,
                "created_at": row["created_at"]}
