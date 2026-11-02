from __future__ import annotations

import csv
import sqlite3
import threading
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from .image_ops import ProcessResult

DEFAULT_DB = Path.home() / ".hulagway" / "history.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    operation TEXT NOT NULL,
    source_path TEXT NOT NULL,
    output_path TEXT,
    orig_size INTEGER DEFAULT 0,
    new_size INTEGER DEFAULT 0,
    orig_dims TEXT,
    new_dims TEXT,
    src_format TEXT,
    out_format TEXT,
    status TEXT NOT NULL,
    message TEXT
);
CREATE INDEX IF NOT EXISTS idx_ops_time ON operations(timestamp);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
"""


class Database:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else DEFAULT_DB
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._lock, closing(self._connect()) as conn, conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _run(self, sql: str, params=(), many=False, fetch=False):
        with self._lock, closing(self._connect()) as conn, conn:
            cur = conn.executemany(sql, params) if many else conn.execute(sql, params)
            return cur.fetchall() if fetch else None

    def add_results(self, operation: str, results: Iterable[ProcessResult]) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = []
        for r in results:
            if r.status == "cancelled":
                continue
            dims = lambda d: f"{d[0]}x{d[1]}" if d and d[0] else ""
            rows.append((now, operation, str(r.src), str(r.dest) if r.dest else None,
                         r.orig_size, r.new_size, dims(r.orig_dims), dims(r.new_dims),
                         r.src_format, r.out_format, r.status, r.error or r.note))
        if rows:
            self._run("INSERT INTO operations (timestamp, operation, source_path, output_path, orig_size,"
                      " new_size, orig_dims, new_dims, src_format, out_format, status, message)"
                      " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows, many=True)

    def delete(self, op_id: int) -> None:
        self._run("DELETE FROM operations WHERE id = ?", (op_id,))

    def clear(self) -> None:
        self._run("DELETE FROM operations")

    def set_setting(self, key: str, value: str) -> None:
        self._run("INSERT INTO settings (key, value) VALUES (?, ?) "
                  "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    def get_setting(self, key: str, default: str = "") -> str:
        rows = self._run("SELECT value FROM settings WHERE key = ?", (key,), fetch=True)
        return rows[0]["value"] if rows else default

    def recent(self, limit: int = 8) -> list:
        return self._run("SELECT * FROM operations ORDER BY id DESC LIMIT ?", (limit,), fetch=True)

    def search(self, text: str = "", operation: str = "All", status: str = "All", limit: int = 500) -> list:
        sql, params = "SELECT * FROM operations WHERE 1=1", []
        if text.strip():
            sql += " AND (source_path LIKE ? OR output_path LIKE ?)"
            params += [f"%{text.strip()}%"] * 2
        if operation != "All":
            sql += " AND operation = ?"
            params.append(operation)
        if status != "All":
            sql += " AND status = ?"
            params.append(status.lower())
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return self._run(sql, params, fetch=True)

    def stats(self) -> dict:
        row = self._run(
            "SELECT COUNT(*) AS total,"
            " COALESCE(SUM(status='success'),0) AS ok,"
            " COALESCE(SUM(status='failed'),0) AS failed,"
            " COALESCE(SUM(CASE WHEN status='success' THEN orig_size END),0) AS orig,"
            " COALESCE(SUM(CASE WHEN status='success' THEN new_size END),0) AS new"
            " FROM operations", fetch=True)[0]
        orig, new = row["orig"], row["new"]
        return {"total": row["total"], "ok": row["ok"], "failed": row["failed"],
                "saved": orig - new, "avg_pct": (1 - new / orig) * 100 if orig else 0.0}

    def breakdown(self) -> list:
        return self._run(
            "SELECT operation, COUNT(*) AS n,"
            " COALESCE(SUM(CASE WHEN status='success' THEN orig_size - new_size END),0) AS saved"
            " FROM operations GROUP BY operation ORDER BY n DESC", fetch=True)

    def export_csv(self, dest: Path) -> int:
        rows = self._run("SELECT * FROM operations ORDER BY id", fetch=True)
        with open(dest, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(rows[0].keys() if rows else
                            ["id", "timestamp", "operation", "source_path", "output_path"])
            writer.writerows([tuple(r) for r in rows])
        return len(rows)
