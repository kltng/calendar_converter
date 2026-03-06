"""SQLite database connection and query layer."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "calendar.db"


def get_connection(
    db_path: Path | None = None,
    check_same_thread: bool = True,
) -> sqlite3.Connection:
    """Get a SQLite connection with row factory."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path), check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def find_eras_by_name(
    conn: sqlite3.Connection,
    era_name: str,
    country: str | None = None,
) -> list[sqlite3.Row]:
    """Find all eras matching a given name, optionally filtered by country."""
    sql = """
        SELECT es.*
        FROM era_summary es
        WHERE es.era_name = ?
    """
    params: list[str] = [era_name]
    if country:
        sql += " AND es.country = ?"
        params.append(country)
    sql += " ORDER BY es.start_jdn"
    return conn.execute(sql, params).fetchall()


def find_month(
    conn: sqlite3.Connection,
    era_id: int,
    year_in_era: int,
    month: int | None = None,
    is_leap_month: bool = False,
) -> list[sqlite3.Row]:
    """Find lunar month records for a given era, year, and optionally month."""
    sql = """
        SELECT * FROM month
        WHERE era_id = ? AND year = ?
    """
    params: list[int | str] = [era_id, year_in_era]
    if month is not None:
        sql += " AND month = ? AND leap_month = ?"
        params.append(month)
        params.append(1 if is_leap_month else 0)
    sql += " ORDER BY first_jdn"
    return conn.execute(sql, params).fetchall()


def find_date_by_jdn(
    conn: sqlite3.Connection,
    jdn: int,
) -> list[sqlite3.Row]:
    """Find all lunar month records containing a given JDN."""
    sql = """
        SELECT
            m.*,
            es.era_name,
            es.emperor_name,
            es.dynasty_name,
            es.country
        FROM month m
        JOIN era_summary es ON es.era_id = m.era_id
        WHERE m.first_jdn <= ? AND m.last_jdn >= ?
        ORDER BY es.country, m.first_jdn
    """
    return conn.execute(sql, (jdn, jdn)).fetchall()


def get_all_eras(
    conn: sqlite3.Connection,
    country: str | None = None,
    dynasty_name: str | None = None,
) -> list[sqlite3.Row]:
    """List eras, optionally filtered by country or dynasty."""
    sql = "SELECT * FROM era_summary WHERE 1=1"
    params: list[str] = []
    if country:
        sql += " AND country = ?"
        params.append(country)
    if dynasty_name:
        sql += " AND dynasty_name = ?"
        params.append(dynasty_name)
    sql += " ORDER BY start_jdn"
    return conn.execute(sql, params).fetchall()
