from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from auto_curso.constants import get_database_path


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(
        get_database_path(), check_same_thread=False, timeout=5.0
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
