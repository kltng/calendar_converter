"""
Apply known corrections to data/calendar.db.

The database is built from the DILA authority dump (build_db.py) and extended
with Vietnamese data (add_vietnamese.py). This script fixes errors found in
that data afterwards. Run it after the other two:

    python -m data.scripts.build_db
    python -m data.scripts.add_vietnamese
    python -m data.scripts.apply_corrections

It is safe to run more than once: each correction first checks whether the
error is still there. Every correction that was applied is recorded in the
table `data_correction`.

Corrections
-----------
1. era-jianshi: the era of 西漢 成帝 that starts in 32 BCE is 建始 (漢書 卷10),
   not 始建.
2. korea-jungjong, korea-injo: 中宗 and 仁祖 of Joseon took the throne after
   the king before them was deposed (燕山君 in 1506, 光海君 in 1623). The
   Joseon Sillok counts the accession year as year 1 (中宗 1년 = 1506,
   仁祖 1년 = 1623). The DILA data starts the count in the next year and keeps
   the deposed king, marked as continued use (status 'P'), to the end of the
   accession year. Here the new king starts on the accession day with year 1,
   and all his later years move up by one.
   Sources: 中宗實錄 1년 9월 2일; 仁祖實錄 1년 3월 13일
   (https://sillok.history.go.kr/id/kpa_10103013_001).
"""

import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "calendar.db"

# (key, emperor, wrong era name, right era name, description)
ERA_NAME_FIXES = [
    ("era-jianshi", "成帝", "始建", "建始",
     "西漢 成帝: era name 始建 corrected to 建始 (漢書 卷10)"),
]

# (key, deposed king, new king, deposed king's last year, month, accession day, description)
KOREAN_ACCESSION_FIXES = [
    ("korea-jungjong", "燕山君", "中宗", 12, 9, 2,
     "中宗 counts from the accession year 1506 (中宗實錄 1년 9월 2일); "
     "燕山君 ends on 12年 9月 1日"),
    ("korea-injo", "光海君", "仁祖", 15, 3, 13,
     "仁祖 counts from the accession year 1623 (仁祖實錄 1년 3월 13일); "
     "光海君 ends on 15年 3月 12日"),
]
KOREAN_DYNASTY = "大朝鮮國"
KOREAN_REIGN_ERA = "（王年）"

MONTH_COLS = ("year", "month", "month_name", "leap_month", "era_id", "first_jdn",
              "last_jdn", "ganzhi", "start_from", "status", "eclipse")


def era_ids(conn: sqlite3.Connection, emperor: str, era_name: str,
            dynasty: str | None = None) -> list[int]:
    """Era ids by emperor name and era name (primary names only)."""
    sql = (
        "SELECT e.id FROM era e "
        "JOIN era_name en ON en.era_id = e.id AND en.ranking = 0 "
        "JOIN emperor emp ON emp.id = e.emperor_id "
        "JOIN emperor_name empn ON empn.emperor_id = emp.id AND empn.ranking = 0 "
        "LEFT JOIN dynasty_name dn ON dn.dynasty_id = emp.dynasty_id AND dn.ranking = 0 "
        "WHERE empn.name = ? AND en.name = ?"
    )
    params = [emperor, era_name]
    if dynasty:
        sql += " AND dn.name = ?"
        params.append(dynasty)
    return [r[0] for r in conn.execute(sql, params)]


def fix_era_name(conn: sqlite3.Connection, emperor: str, wrong: str, right: str) -> bool:
    ids = era_ids(conn, emperor, wrong)
    for era_id in ids:
        conn.execute("UPDATE era_name SET name = ? WHERE era_id = ? AND ranking = 0",
                     (right, era_id))
    return bool(ids)


def fix_korean_accession(conn: sqlite3.Connection, old_king: str, new_king: str,
                         last_year: int, month: int, day: int) -> bool:
    """Start the new king on his accession day, with that year as year 1."""
    old = era_ids(conn, old_king, KOREAN_REIGN_ERA, KOREAN_DYNASTY)
    new = era_ids(conn, new_king, KOREAN_REIGN_ERA, KOREAN_DYNASTY)
    if len(old) != 1 or len(new) != 1:
        return False
    old_id, new_id = old[0], new[0]
    conn.row_factory = sqlite3.Row
    pieces = conn.execute(
        "SELECT * FROM month WHERE era_id = ? AND year = ? AND month = ? AND leap_month = 0 "
        "ORDER BY first_jdn", (old_id, last_year, month)).fetchall()
    if not pieces:
        return False
    month_first = min(r["first_jdn"] for r in pieces)
    month_last = max(r["last_jdn"] for r in pieces)
    first_day = min(r["start_from"] for r in pieces)
    accession = month_first + (day - first_day)
    if not month_first <= accession <= month_last:
        return False
    new_start = conn.execute("SELECT MIN(first_jdn) FROM month WHERE era_id = ?", (new_id,)).fetchone()[0]
    old_end = conn.execute("SELECT MAX(last_jdn) FROM month WHERE era_id = ?", (old_id,)).fetchone()[0]
    if new_start is None or new_start <= accession or old_end <= accession:
        return False  # already corrected

    # 1. the new king's existing years move up by one
    conn.execute("UPDATE month SET year = year + 1 WHERE era_id = ?", (new_id,))
    # 2. the months after the accession month become year 1 of the new king
    conn.execute("UPDATE month SET era_id = ?, year = 1, status = 'S' "
                 "WHERE era_id = ? AND first_jdn > ?", (new_id, old_id, month_last))
    # 3. the accession month is split on the accession day
    base = dict(pieces[0])
    conn.execute("DELETE FROM month WHERE id IN (%s)" % ", ".join("?" * len(pieces)),
                 [r["id"] for r in pieces])
    cols = ", ".join(MONTH_COLS)
    marks = ", ".join("?" * len(MONTH_COLS))
    if accession > month_first:
        row = {**base, "first_jdn": month_first, "last_jdn": accession - 1,
               "start_from": first_day, "status": "S"}
        conn.execute(f"INSERT INTO month (id, {cols}) VALUES (?, {marks})",
                     [base["id"], *[row[c] for c in MONTH_COLS]])
    row = {**base, "era_id": new_id, "year": 1, "first_jdn": accession,
           "last_jdn": month_last, "start_from": day, "status": "S"}
    conn.execute(f"INSERT INTO month ({cols}) VALUES ({marks})", [row[c] for c in MONTH_COLS])
    return True


def apply_corrections(db_path: Path = DB_PATH) -> list[str]:
    """Apply every correction that is still needed. Returns the keys applied."""
    conn = sqlite3.connect(str(db_path))
    applied: list[str] = []
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS data_correction ("
            "key TEXT PRIMARY KEY, description TEXT NOT NULL, "
            "applied_at TEXT NOT NULL DEFAULT (date('now')))")
        for key, emperor, wrong, right, description in ERA_NAME_FIXES:
            if fix_era_name(conn, emperor, wrong, right):
                applied.append(key)
                conn.execute("INSERT OR REPLACE INTO data_correction (key, description) VALUES (?, ?)",
                             (key, description))
        for key, old_king, new_king, last_year, month, day, description in KOREAN_ACCESSION_FIXES:
            if fix_korean_accession(conn, old_king, new_king, last_year, month, day):
                applied.append(key)
                conn.execute("INSERT OR REPLACE INTO data_correction (key, description) VALUES (?, ?)",
                             (key, description))
        conn.commit()
    finally:
        conn.close()
    return applied


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DB_PATH
    if not path.exists():
        print(f"ERROR: database not found at {path}")
        sys.exit(1)
    done = apply_corrections(path)
    print(f"Applied: {', '.join(done)}" if done else "Nothing to do: the data is already corrected.")
