"""Import the ten CSV files into an empty Tablemates database, in one transaction."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

# Allow direct execution as: python scripts/seed_data.py
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg
from psycopg import sql
from app.db import connect
from generate_data import FILES

IDENTITY = {
    "app_user": "user_id", "suburb": "suburb_id", "cuisine": "cuisine_id",
    "restaurant": "restaurant_id", "friendship": "friendship_id", "visit": "visit_id",
    "review": "review_id", "review_comment": "comment_id",
}
DEMO_PASSWORD = "DemoPass2026!"


def load_csv(directory: Path) -> dict[str, list[tuple]]:
    result = {}
    for name, (_, columns) in FILES.items():
        with (directory / f"{name}.csv").open(encoding="utf-8-sig", newline="") as file:
            reader = csv.reader(file)
            if next(reader, None) != list(columns):
                raise ValueError(f"{name}.csv has unexpected headings; expected {', '.join(columns)}.")
            values = []
            for line, row in enumerate(reader, 2):
                if len(row) != len(columns):
                    raise ValueError(f"{name}.csv line {line} has the wrong number of fields.")
                values.append(tuple(None if cell == "" else cell for cell in row))
            result[name] = values
    return result


def import_data(connection: psycopg.Connection, directory: Path) -> dict[str, int]:
    data = load_csv(directory)
    expected = {table for table, _ in FILES.values()}
    with connection.transaction():
        tables = {row["tablename"] for row in connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()}
        if tables != expected:
            raise ValueError("Database schema does not match the ten-table version. Use the v2 Docker volume.")
        # Serialise seed imports and prevent application writes during initialisation.
        connection.execute(sql.SQL("LOCK TABLE {} IN EXCLUSIVE MODE").format(
            sql.SQL(", ").join(sql.Identifier(table) for table in sorted(expected))))
        for table in sorted(expected):
            if connection.execute(sql.SQL("SELECT 1 FROM {} LIMIT 1").format(sql.Identifier(table))).fetchone():
                raise ValueError(f"Refusing to import: {table} is not empty. Existing data has not been changed.")
        for name, (table, columns) in FILES.items():
            if table == "app_user":
                statement = sql.SQL("""
                    INSERT INTO app_user (user_id, user_name, user_email, created_at, password_hash)
                    OVERRIDING SYSTEM VALUE VALUES (%s, %s, %s, %s, crypt(%s, gen_salt('bf', 10)))
                """)
                values = [(*row, os.environ.get("DEMO_PASSWORD", DEMO_PASSWORD)) for row in data[name]]
            else:
                statement = sql.SQL("INSERT INTO {} ({}) {} VALUES ({})").format(
                    sql.Identifier(table),
                    sql.SQL(", ").join(map(sql.Identifier, columns)),
                    sql.SQL("OVERRIDING SYSTEM VALUE" if table in IDENTITY else ""),
                    sql.SQL(", ").join(sql.Placeholder() for _ in columns),
                )
                values = data[name]
            with connection.cursor() as cursor:
                cursor.executemany(statement, values)
        # CSV supplies stable IDs; future registrations and reviews must use IDs above them.
        # RESTART is transactional, so it rolls back with a failed import.
        for table, column in IDENTITY.items():
            next_id = connection.execute(sql.SQL("SELECT COALESCE(max({}), 0) + 1 AS next_id FROM {}").format(
                sql.Identifier(column), sql.Identifier(table))).fetchone()["next_id"]
            connection.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN {} RESTART WITH {}").format(
                sql.Identifier(table), sql.Identifier(column), sql.Literal(next_id)))
    return {name: len(rows) for name, rows in data.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    try:
        with connect() as connection:
            counts = import_data(connection, args.data_dir)
    except (OSError, ValueError, psycopg.Error, RuntimeError) as exc:
        parser.exit(1, f"Import failed; no partial data was committed: {exc}\n")
    print("Imported CSV successfully.")
    for name, count in counts.items():
        print(f"  {name}: {count}")


if __name__ == "__main__":
    main()
