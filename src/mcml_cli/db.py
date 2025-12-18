from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

APP_NAME = "mcml"
DB_FILENAME = "mcml.sqlite"


def default_db_path() -> Path:
    # Linux and macOS friendly.
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        base = Path(xdg)
    else:
        base = Path.home() / ".local" / "share"
    return base / APP_NAME / DB_FILENAME


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or default_db_path()
    ensure_parent_dir(path)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def init_db(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            first_name TEXT,
            last_name TEXT,
            role TEXT,
            note TEXT,
            mcml_url TEXT,
            source_page TEXT,
            last_updated_utc TEXT NOT NULL
        );
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_people_full_name ON people(full_name);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_people_last_name ON people(last_name);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_people_first_name ON people(first_name);")
    con.commit()


def replace_all_people(con: sqlite3.Connection, people: Iterable["Person"]) -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    con.execute("DELETE FROM people;")
    rows = [
        (
            p.full_name,
            p.first_name,
            p.last_name,
            p.role,
            p.note,
            p.mcml_url,
            p.source_page,
            now,
        )
        for p in people
    ]
    con.executemany(
        """
        INSERT INTO people(
            full_name, first_name, last_name, role, note, mcml_url, source_page, last_updated_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """,
        rows,
    )
    con.commit()
    return len(rows)


def fetch_all(con: sqlite3.Connection) -> list[sqlite3.Row]:
    cur = con.execute(
        """
        SELECT full_name, first_name, last_name, role, note, mcml_url, source_page, last_updated_utc
        FROM people
        ORDER BY last_name IS NULL, last_name, first_name;
        """
    )
    return list(cur.fetchall())


def last_updated(con: sqlite3.Connection) -> Optional[str]:
    cur = con.execute("SELECT MAX(last_updated_utc) AS ts FROM people;")
    row = cur.fetchone()
    return row["ts"] if row and row["ts"] else None


@dataclass(frozen=True)
class Person:
    full_name: str
    first_name: str
    last_name: str
    role: str
    note: str
    mcml_url: str
    source_page: str
