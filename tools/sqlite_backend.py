"""The only module that talks to SQLite. Tools wrap these helpers; agents
never import this file."""
from __future__ import annotations

import asyncio
import sqlite3
from typing import Any

from config import settings


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(settings.db_path)
    con.row_factory = sqlite3.Row
    return con


async def fetch_all(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    def run() -> list[dict[str, Any]]:
        with _connect() as con:
            return [dict(r) for r in con.execute(sql, params)]
    return await asyncio.to_thread(run)


async def fetch_one(sql: str, params: tuple = ()) -> dict[str, Any] | None:
    rows = await fetch_all(sql, params)
    return rows[0] if rows else None
