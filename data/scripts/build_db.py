"""
ETL script: Convert DILA MySQL dump → SQLite database.

Parses the MySQL SQL dump, extracts INSERT statements, and loads data
into a normalized SQLite schema optimized for calendar conversion queries.

Usage:
    python -m data.scripts.build_db
"""

import re
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SQL_DUMP = PROJECT_ROOT / "data" / "raw" / "authority_time" / "authority_time.sql"
DB_PATH = PROJECT_ROOT / "data" / "calendar.db"

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS dynasty (
    id          INTEGER PRIMARY KEY,
    type        TEXT NOT NULL  -- 'chinese', 'japanese', 'korean'
);

CREATE TABLE IF NOT EXISTS dynasty_name (
    dynasty_id  INTEGER NOT NULL REFERENCES dynasty(id),
    name        TEXT NOT NULL,
    ranking     INTEGER NOT NULL DEFAULT 0,
    language_id INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (dynasty_id, ranking)
);
CREATE INDEX IF NOT EXISTS idx_dynasty_name_name ON dynasty_name(name);

CREATE TABLE IF NOT EXISTS emperor (
    id          INTEGER PRIMARY KEY,
    dynasty_id  INTEGER NOT NULL REFERENCES dynasty(id)
);

CREATE TABLE IF NOT EXISTS emperor_name (
    emperor_id  INTEGER NOT NULL REFERENCES emperor(id),
    name        TEXT NOT NULL,
    ranking     INTEGER NOT NULL DEFAULT 0,
    language_id INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (emperor_id, ranking)
);
CREATE INDEX IF NOT EXISTS idx_emperor_name_name ON emperor_name(name);

CREATE TABLE IF NOT EXISTS era (
    id          INTEGER PRIMARY KEY,
    emperor_id  INTEGER NOT NULL REFERENCES emperor(id)
);

CREATE TABLE IF NOT EXISTS era_name (
    era_id      INTEGER NOT NULL REFERENCES era(id),
    name        TEXT NOT NULL,
    ranking     INTEGER NOT NULL DEFAULT 0,
    language_id INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (era_id, ranking)
);
CREATE INDEX IF NOT EXISTS idx_era_name_name ON era_name(name);

CREATE TABLE IF NOT EXISTS month (
    id          INTEGER PRIMARY KEY,
    year        INTEGER NOT NULL,       -- ordinal year within era
    month       INTEGER NOT NULL,       -- month number
    month_name  TEXT NOT NULL,           -- Chinese month name
    leap_month  INTEGER NOT NULL DEFAULT 0,
    era_id      INTEGER NOT NULL REFERENCES era(id),
    first_jdn   INTEGER NOT NULL,       -- JDN of first day
    last_jdn    INTEGER NOT NULL,       -- JDN of last day
    ganzhi      TEXT NOT NULL DEFAULT '',-- sexagenary year
    start_from  INTEGER NOT NULL DEFAULT 1,
    status      TEXT NOT NULL DEFAULT 'S', -- 'S' standard, 'P' proleptic
    eclipse     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_month_era_id ON month(era_id);
CREATE INDEX IF NOT EXISTS idx_month_first_jdn ON month(first_jdn);
CREATE INDEX IF NOT EXISTS idx_month_last_jdn ON month(last_jdn);
CREATE INDEX IF NOT EXISTS idx_month_jdn_range ON month(first_jdn, last_jdn);

CREATE TABLE IF NOT EXISTS period (
    id          INTEGER PRIMARY KEY,
    dynasty_id  INTEGER REFERENCES dynasty(id),
    first_jdn   INTEGER NOT NULL,
    last_jdn    INTEGER NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    note        TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS day_comment (
    id          INTEGER PRIMARY KEY,
    jdn         INTEGER NOT NULL,
    comment     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_day_comment_jdn ON day_comment(jdn);

-- Materialized view: era with computed JDN range and dynasty info
CREATE VIEW IF NOT EXISTS era_summary AS
SELECT
    e.id AS era_id,
    en.name AS era_name,
    emp.id AS emperor_id,
    empn.name AS emperor_name,
    d.id AS dynasty_id,
    dn.name AS dynasty_name,
    d.type AS country,
    MIN(m.first_jdn) AS start_jdn,
    MAX(m.last_jdn) AS end_jdn
FROM era e
JOIN era_name en ON en.era_id = e.id AND en.ranking = 0
JOIN emperor emp ON emp.id = e.emperor_id
LEFT JOIN emperor_name empn ON empn.emperor_id = emp.id AND empn.ranking = 0
JOIN dynasty d ON d.id = emp.dynasty_id
LEFT JOIN dynasty_name dn ON dn.dynasty_id = d.id AND dn.ranking = 0
LEFT JOIN month m ON m.era_id = e.id
GROUP BY e.id;
"""


def parse_mysql_values(values_str: str) -> list[tuple[str, ...]]:
    """Parse MySQL VALUES (...),(...) into list of tuples."""
    rows = []
    # Match individual value groups: (val1,val2,...)
    for match in re.finditer(r"\(([^)]*)\)", values_str):
        inner = match.group(1)
        fields: list[str] = []
        current = ""
        in_string = False
        escape_next = False
        for ch in inner:
            if escape_next:
                current += ch
                escape_next = False
                continue
            if ch == "\\":
                escape_next = True
                current += ch
                continue
            if ch == "'" and not in_string:
                in_string = True
                continue
            if ch == "'" and in_string:
                in_string = False
                continue
            if ch == "," and not in_string:
                fields.append(current)
                current = ""
                continue
            current += ch
        fields.append(current)
        rows.append(tuple(f.strip() for f in fields))
    return rows


# Map MySQL table names to SQLite table names
TABLE_MAP = {
    "t_dynasty": "dynasty",
    "t_dynasty_names": "dynasty_name",
    "t_emperor": "emperor",
    "t_emperor_names": "emperor_name",
    "t_era": "era",
    "t_era_names": "era_name",
    "t_month": "month",
    "t_period": "period",
    "t_day_comments": "day_comment",
}

# Column mappings: MySQL columns → SQLite columns
COLUMN_MAP = {
    "dynasty": ("id", "type"),
    "dynasty_name": ("dynasty_id", "name", "ranking", "language_id"),
    "emperor": ("id", "dynasty_id"),
    "emperor_name": ("emperor_id", "name", "ranking", "language_id"),
    "era": ("id", "emperor_id"),
    "era_name": ("era_id", "name", "ranking", "language_id"),
    "month": (
        "id", "year", "month", "month_name", "leap_month",
        "era_id", "first_jdn", "last_jdn", "ganzhi", "start_from",
        "status", "eclipse",
    ),
    "period": ("id", "dynasty_id", "first_jdn", "last_jdn", "description", "note"),
    "day_comment": ("id", "jdn", "comment"),
}


def convert_value(val: str, col_name: str) -> int | str | None:
    """Convert a parsed MySQL value to appropriate Python type."""
    if val == "NULL":
        return None
    # Integer columns
    int_cols = {
        "id", "dynasty_id", "emperor_id", "era_id", "ranking",
        "language_id", "year", "month", "leap_month", "first_jdn",
        "last_jdn", "start_from", "eclipse", "jdn",
    }
    if col_name in int_cols:
        try:
            return int(val)
        except ValueError:
            return val
    return val


def build_db() -> None:
    if not SQL_DUMP.exists():
        print(f"ERROR: SQL dump not found at {SQL_DUMP}")
        print("Download from: https://authority.dila.edu.tw/downloads/authority_time.2012-02.zip")
        sys.exit(1)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SQLITE_SCHEMA)

    sql_text = SQL_DUMP.read_text(encoding="utf-8")

    # Extract INSERT statements
    insert_pattern = re.compile(
        r"INSERT INTO `(\w+)` VALUES\s*(.*?);",
        re.DOTALL,
    )

    row_counts: dict[str, int] = {}

    for match in insert_pattern.finditer(sql_text):
        mysql_table = match.group(1)
        values_str = match.group(2)

        sqlite_table = TABLE_MAP.get(mysql_table)
        if sqlite_table is None:
            continue

        columns = COLUMN_MAP[sqlite_table]
        rows = parse_mysql_values(values_str)

        converted_rows = []
        for row in rows:
            if len(row) != len(columns):
                # Skip rows with mismatched column count
                continue
            converted = tuple(
                convert_value(val, col) for val, col in zip(row, columns)
            )
            converted_rows.append(converted)

        if converted_rows:
            placeholders = ", ".join("?" * len(columns))
            col_names = ", ".join(columns)
            sql = f"INSERT OR IGNORE INTO {sqlite_table} ({col_names}) VALUES ({placeholders})"
            conn.executemany(sql, converted_rows)
            row_counts[sqlite_table] = row_counts.get(sqlite_table, 0) + len(converted_rows)

    conn.commit()

    # Print stats
    print(f"Database built: {DB_PATH}")
    for table, count in sorted(row_counts.items()):
        print(f"  {table}: {count} rows")

    # Verify era_summary view
    cursor = conn.execute("SELECT COUNT(*) FROM era_summary")
    era_count = cursor.fetchone()[0]
    print(f"  era_summary (view): {era_count} eras")

    conn.close()


if __name__ == "__main__":
    build_db()
