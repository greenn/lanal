from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .curl_presets import normalized_domain


SCHEMA_VERSION = 1


@dataclass
class StoredRequest:
    id: int | None
    domain: str
    url: str
    preset_name: str
    display_command: str
    started_at: str
    duration_ms: int
    exit_code: int
    stdout: str
    stderr: str
    status_code: int | None
    remote_ip: str | None
    remote_port: str | None
    http_version: str | None
    final_url: str | None
    server: str | None
    headers_raw: str
    body: str
    timing: dict[str, Any]
    note: str = ""
    is_sample: bool = False


def default_db_path() -> Path:
    root = Path(os.environ.get("APPDATA") or Path.home() / ".lanal")
    folder = root / "Lanal"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "lanal.db"


class Database:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain TEXT NOT NULL,
                    url TEXT NOT NULL,
                    preset_name TEXT NOT NULL,
                    display_command TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    exit_code INTEGER NOT NULL DEFAULT 0,
                    stdout TEXT NOT NULL DEFAULT '',
                    stderr TEXT NOT NULL DEFAULT '',
                    status_code INTEGER,
                    remote_ip TEXT,
                    remote_port TEXT,
                    http_version TEXT,
                    final_url TEXT,
                    server TEXT,
                    headers_raw TEXT NOT NULL DEFAULT '',
                    body TEXT NOT NULL DEFAULT '',
                    timing_json TEXT NOT NULL DEFAULT '{}',
                    note TEXT NOT NULL DEFAULT '',
                    is_sample INTEGER NOT NULL DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_requests_domain_time
                    ON requests(domain, started_at DESC);
                """
            )
            db.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def add_request(self, item: StoredRequest) -> int:
        values = asdict(item)
        values.pop("id", None)
        timing = values.pop("timing")
        values["timing_json"] = json.dumps(timing, ensure_ascii=False)
        values["is_sample"] = int(bool(values["is_sample"]))
        columns = ", ".join(values.keys())
        placeholders = ", ".join("?" for _ in values)
        with self.connect() as db:
            cursor = db.execute(
                f"INSERT INTO requests ({columns}) VALUES ({placeholders})",
                tuple(values.values()),
            )
            return int(cursor.lastrowid)

    def list_requests(self, limit: int = 500) -> list[StoredRequest]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM requests ORDER BY started_at DESC, id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def get_request(self, request_id: int) -> StoredRequest | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        return self._row_to_item(row) if row else None

    def update_note(self, request_id: int, note: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE requests SET note = ? WHERE id = ?", (note, request_id))

    def delete_request(self, request_id: int) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM requests WHERE id = ?", (request_id,))

    def count(self) -> int:
        with self.connect() as db:
            return int(db.execute("SELECT COUNT(*) FROM requests").fetchone()[0])

    def seed_demo_if_empty(self) -> None:
        if self.count() != 0:
            return
        timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        sample_headers = (
            "HTTP/2 403\n"
            "server: cloudflare\n"
            "content-type: text/html; charset=UTF-8\n"
            "cf-ray: sample-FRA\n"
        )
        self.add_request(
            StoredRequest(
                id=None,
                domain=normalized_domain("https://novelcrow.com/"),
                url="https://novelcrow.com/",
                preset_name="Info · sample",
                display_command='curl -I -4 --http2 -A "Mozilla/5.0" --compressed https://novelcrow.com/',
                started_at=timestamp,
                duration_ms=184,
                exit_code=0,
                stdout="",
                stderr="",
                status_code=403,
                remote_ip="104.21.43.32",
                remote_port="443",
                http_version="2",
                final_url="https://novelcrow.com/",
                server="cloudflare",
                headers_raw=sample_headers,
                body=(
                    "Sample from the initial NovelCrow investigation.\n"
                    "The observed page said: Sorry, you have been blocked.\n"
                    "Run the request locally to replace this sample with live data."
                ),
                timing={
                    "dns": 0.021,
                    "connect": 0.054,
                    "tls": 0.118,
                    "ttfb": 0.183,
                    "total": 0.184,
                },
                note="Sample data only. Run again for current results from your connection.",
                is_sample=True,
            )
        )

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> StoredRequest:
        return StoredRequest(
            id=row["id"],
            domain=row["domain"],
            url=row["url"],
            preset_name=row["preset_name"],
            display_command=row["display_command"],
            started_at=row["started_at"],
            duration_ms=row["duration_ms"],
            exit_code=row["exit_code"],
            stdout=row["stdout"],
            stderr=row["stderr"],
            status_code=row["status_code"],
            remote_ip=row["remote_ip"],
            remote_port=row["remote_port"],
            http_version=row["http_version"],
            final_url=row["final_url"],
            server=row["server"],
            headers_raw=row["headers_raw"],
            body=row["body"],
            timing=json.loads(row["timing_json"] or "{}"),
            note=row["note"],
            is_sample=bool(row["is_sample"]),
        )
