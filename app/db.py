"""PostgreSQL connection management for Flask requests."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
from flask import g
from psycopg.rows import dict_row


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DatabaseConfigError(RuntimeError):
    """The local PostgreSQL connection is not configured."""


def _local_password() -> str | None:
    """Read only the Compose password from this project's simple .env file."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == "POSTGRES_PASSWORD":
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            return value or None
    return None


def connect() -> psycopg.Connection:
    options = {
        "row_factory": dict_row,
        "autocommit": True,
        "connect_timeout": 4,
        "options": "-c timezone=Australia/Sydney",
    }
    url = os.environ.get("DATABASE_URL")
    if url:
        return psycopg.connect(url, **options)
    password = os.environ.get("POSTGRES_PASSWORD") or _local_password()
    if not password:
        raise DatabaseConfigError(
            "Set DATABASE_URL or POSTGRES_PASSWORD, or create the project's .env file."
        )
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.environ.get("POSTGRES_PORT", "5433")),
        dbname=os.environ.get("POSTGRES_DB", "friend_review"),
        user=os.environ.get("POSTGRES_USER", "friend_app"),
        password=password,
        **options,
    )


def get_db() -> psycopg.Connection:
    if "db_connection" not in g:
        g.db_connection = connect()
    return g.db_connection


def close_db(_error: BaseException | None = None) -> None:
    connection = g.pop("db_connection", None)
    if connection is not None:
        connection.close()
