"""SQLite database connection and query layer."""

import sqlite3
from functools import lru_cache
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


# Names the database gives to years that have no era name of their own
REIGN_ERA_NAMES = ("（無年號）", "（王年）")
# 文帝後三年, 景帝中五年: the 後元 / 中元 years of a Han emperor
REIGN_SUFFIXES = {"後": "（後元）", "中": "（中元）"}
# The same suffixes as they may be typed in simplified characters
_SIMPLIFIED_REIGN_SUFFIXES = {"后": "後", "後": "後", "中": "中"}


COUNTRIES = ("chinese", "japanese", "korean", "vietnamese")

# What people and language models write for the country, mapped to the value in dynasty.type
_COUNTRY_ALIASES = {
    "chinese": ("chinese", "china", "cn", "zh", "prc", "中国", "中國", "中华", "中華", "中", "漢", "汉"),
    "japanese": ("japanese", "japan", "jp", "ja", "jpn", "日本", "日"),
    "korean": ("korean", "korea", "kr", "ko", "kor", "韓國", "韩国", "韓", "韩", "朝鮮", "朝鲜", "高麗", "高丽"),
    "vietnamese": ("vietnamese", "vietnam", "viet nam", "vn", "vi", "越南", "越"),
}
_COUNTRY_LOOKUP = {alias: country for country, aliases in _COUNTRY_ALIASES.items() for alias in aliases}


def canonical_country(value: str | None) -> str | None:
    """Map 'China', '中国', 'Chinese', 'JP' ... to chinese / japanese / korean / vietnamese.

    Returns None when the value names none of the four.
    """
    if not value:
        return None
    return _COUNTRY_LOOKUP.get(value.strip().lower())


@lru_cache(maxsize=1)
def _simplifier():  # type: ignore[no-untyped-def]
    from opencc import OpenCC  # type: ignore[import-untyped]

    return OpenCC("t2s")


def simplified(text: str) -> str:
    """Simplified-character form of a name. Used only to compare names, never stored."""
    return str(_simplifier().convert(text))


_NAME_COLUMNS = ("era_name", "dynasty_name", "emperor_name")
# {database file: {column: {simplified name: [names as stored]}}}
_name_index_cache: dict[str, dict[str, dict[str, list[str]]]] = {}


def _name_index(conn: sqlite3.Connection, column: str) -> dict[str, list[str]]:
    key = str(conn.execute("PRAGMA database_list").fetchone()[2])
    index = _name_index_cache.get(key)
    if index is None:
        index = {}
        for col in _NAME_COLUMNS:
            by_simplified: dict[str, list[str]] = {}
            for (name,) in conn.execute(f"SELECT DISTINCT {col} FROM era_summary WHERE {col} IS NOT NULL"):
                by_simplified.setdefault(simplified(name), []).append(name)
            index[col] = by_simplified
        _name_index_cache[key] = index
    return index[column]


def name_variants(conn: sqlite3.Connection, column: str, value: str) -> list[str]:
    """The stored names that `value` can mean: 崇祯 finds 崇禎, 明朝 finds 明.

    The database keeps names in traditional characters. A name written in simplified
    characters is matched by comparing simplified forms. Empty when nothing matches.
    """
    if column not in _NAME_COLUMNS:
        raise ValueError(f"Unknown name column: {column}")
    value = value.strip()
    index = _name_index(conn, column)
    found = index.get(simplified(value), [])
    if not found and column == "dynasty_name" and len(value) > 1 and value[-1] in "朝代":
        found = index.get(simplified(value[:-1]), [])
    # The exact spelling first, so a name that exists as written wins.
    return sorted(found, key=lambda name: name != value)


def find_eras_by_name(
    conn: sqlite3.Connection,
    era_name: str,
    country: str | None = None,
    dynasty: str | None = None,
    emperor: str | None = None,
) -> list[sqlite3.Row]:
    """Find all eras matching a given name, optionally filtered by country/dynasty/emperor.

    Besides the exact name, this finds:
    - eras stored in brackets: 後元 finds （後元）, 中元 finds （中元）;
    - years counted by the ruler's name, when no era has that name:
      文帝七年 and 仁祖二十二年 find the eras stored as （無年號） or （王年）,
      and 文帝後三年 / 景帝中五年 find that emperor's （後元） / （中元）.
    """
    country = canonical_country(country) or country
    # A hint that matches no stored name keeps its spelling, and so matches nothing.
    dynasties = (name_variants(conn, "dynasty_name", dynasty) or [dynasty]) if dynasty else []
    emperors = (name_variants(conn, "emperor_name", emperor) or [emperor]) if emperor else []

    def run(where: str, values: list[str]) -> list[sqlite3.Row]:
        sql = f"SELECT es.* FROM era_summary es WHERE {where}"
        params = list(values)
        if country:
            sql += " AND es.country = ?"
            params.append(country)
        if dynasties:
            sql += f" AND es.dynasty_name IN ({', '.join('?' * len(dynasties))})"
            params.extend(dynasties)
        if emperors:
            sql += f" AND es.emperor_name IN ({', '.join('?' * len(emperors))})"
            params.extend(emperors)
        sql += " ORDER BY es.start_jdn"
        return conn.execute(sql, params).fetchall()

    def lookup(name: str) -> list[sqlite3.Row]:
        rows = run("es.era_name IN (?, ?)", [name, f"（{name}）"])
        if rows:
            return rows

        # Reign names: the era name given is really the ruler's name.
        rows = run(
            f"es.emperor_name = ? AND es.era_name IN ({', '.join('?' * len(REIGN_ERA_NAMES))})",
            [name, *REIGN_ERA_NAMES],
        )
        if len(name) > 1 and name[-1] in REIGN_SUFFIXES:
            rows += run("es.emperor_name = ? AND es.era_name = ?",
                        [name[:-1], REIGN_SUFFIXES[name[-1]]])
        return rows

    rows = lookup(era_name)
    if rows:
        return rows

    # Not found as written: try the stored spellings of a simplified-character name.
    spellings = name_variants(conn, "era_name", era_name) + name_variants(conn, "emperor_name", era_name)
    if len(era_name) > 1 and era_name[-1] in _SIMPLIFIED_REIGN_SUFFIXES:
        suffix = _SIMPLIFIED_REIGN_SUFFIXES[era_name[-1]]
        spellings += [name + suffix for name in name_variants(conn, "emperor_name", era_name[:-1])]
    seen = {era_name}
    for spelling in spellings:
        if spelling in seen:
            continue
        seen.add(spelling)
        rows += lookup(spelling)
    return rows


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


def find_years_by_ganzhi(
    conn: sqlite3.Connection,
    era_id: int,
    ganzhi: str,
) -> list[sqlite3.Row]:
    """Find all year numbers within an era that match a given year ganzhi."""
    sql = """
        SELECT DISTINCT year, ganzhi FROM month
        WHERE era_id = ? AND ganzhi = ?
        ORDER BY year
    """
    return conn.execute(sql, (era_id, ganzhi)).fetchall()


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
    country = canonical_country(country) or country
    if country:
        sql += " AND country = ?"
        params.append(country)
    if dynasty_name:
        dynasties = name_variants(conn, "dynasty_name", dynasty_name) or [dynasty_name]
        sql += f" AND dynasty_name IN ({', '.join('?' * len(dynasties))})"
        params.extend(dynasties)
    sql += " ORDER BY start_jdn"
    return conn.execute(sql, params).fetchall()
