"""
Core conversion logic using JDN as universal pivot.

JDN (Julian Day Number) is an integer day count from noon GMT, Jan 1, 4713 BCE.
All conversions go through JDN: CJK date → JDN → Gregorian/Julian/other CJK dates.
"""

import sqlite3
from .db import find_eras_by_name, find_month, find_date_by_jdn
from .models import DateConversion, EraInfo, GanzhiInfo, EraMetadata, ParsedDate as ParsedDateModel
from .parser import ParsedDate

# Sexagenary cycle (干支)
HEAVENLY_STEMS = "甲乙丙丁戊己庚辛壬癸"
EARTHLY_BRANCHES = "子丑寅卯辰巳午未申酉戌亥"


def _ganzhi_from_index(idx: int) -> str:
    """Convert a sexagenary cycle index (0-59) to 干支 string."""
    idx = idx % 60
    return HEAVENLY_STEMS[idx % 10] + EARTHLY_BRANCHES[idx % 12]


def ganzhi_index_from_str(gz: str) -> int | None:
    """Convert a 干支 string back to cycle index (0-59)."""
    if len(gz) != 2:
        return None
    stem_idx = HEAVENLY_STEMS.find(gz[0])
    branch_idx = EARTHLY_BRANCHES.find(gz[1])
    if stem_idx < 0 or branch_idx < 0:
        return None
    # Solve: idx % 10 == stem_idx, idx % 12 == branch_idx, 0 <= idx < 60
    for i in range(60):
        if i % 10 == stem_idx and i % 12 == branch_idx:
            return i
    return None


def jdn_to_ganzhi_day(jdn: int) -> str:
    """Compute the sexagenary (干支) day designation for a given JDN.

    Anchor: JDN 2299161 (Oct 15, 1582) = 壬午日 = cycle index 18.
    """
    idx = (jdn - 2299161 + 18) % 60
    return _ganzhi_from_index(idx)


def month_ganzhi(year_ganzhi: str, lunar_month: int) -> str:
    """Compute the sexagenary month from year ganzhi and lunar month number.

    The month ganzhi follows the rule: the stem of month 1 (寅月) is determined
    by the year's Heavenly Stem using the 五虎遁 (Five Tigers) formula:
      Year stem 甲/己 → month 1 stem = 丙 (index 2)
      Year stem 乙/庚 → month 1 stem = 戊 (index 4)
      Year stem 丙/辛 → month 1 stem = 庚 (index 6)
      Year stem 丁/壬 → month 1 stem = 壬 (index 8)
      Year stem 戊/癸 → month 1 stem = 甲 (index 0)

    The Earthly Branch of month 1 is always 寅 (index 2), month 2 = 卯, etc.
    """
    if not year_ganzhi or len(year_ganzhi) < 1:
        return ""
    year_stem_idx = HEAVENLY_STEMS.find(year_ganzhi[0])
    if year_stem_idx < 0:
        return ""

    # Five Tigers formula: base stem for month 1 based on year stem
    base_stems = [2, 4, 6, 8, 0]  # for year stems 甲己, 乙庚, 丙辛, 丁壬, 戊癸
    month1_stem = base_stems[year_stem_idx % 5]

    month_stem = (month1_stem + (lunar_month - 1)) % 10
    month_branch = (lunar_month + 1) % 12  # month 1 = 寅(2), month 2 = 卯(3), ...

    return HEAVENLY_STEMS[month_stem] + EARTHLY_BRANCHES[month_branch]


def jdn_to_gregorian(jdn: int) -> tuple[int, int, int]:
    """Convert JDN to proleptic Gregorian calendar date.

    Returns (year, month, day). Uses astronomical year numbering
    (year 0 = 1 BCE).
    """
    # Algorithm from Meeus, "Astronomical Algorithms" (Richards 2013)
    a = jdn + 32044
    b = (4 * a + 3) // 146097
    c = a - (146097 * b) // 4
    d = (4 * c + 3) // 1461
    e = c - (1461 * d) // 4
    m = (5 * e + 2) // 153

    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = 100 * b + d - 4800 + m // 10

    return (year, month, day)


def gregorian_to_jdn(year: int, month: int, day: int) -> int:
    """Convert Gregorian date to JDN.

    Uses astronomical year numbering (year 0 = 1 BCE).
    """
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    return day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


def jdn_to_julian(jdn: int) -> tuple[int, int, int]:
    """Convert JDN to Julian calendar date.

    Returns (year, month, day).
    """
    b = 0
    c = jdn + 32082
    d = (4 * c + 3) // 1461
    e = c - (1461 * d) // 4
    m = (5 * e + 2) // 153

    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = d - 4800 + m // 10

    return (year, month, day)


def format_date(year: int, month: int, day: int) -> str:
    """Format a date as ISO 8601 string with astronomical year numbering."""
    if year < 0:
        return f"-{abs(year):04d}-{month:02d}-{day:02d}"
    return f"{year:04d}-{month:02d}-{day:02d}"


def convert_cjk_to_jdn(
    conn: sqlite3.Connection,
    parsed: ParsedDate,
) -> list[tuple[int, EraInfo]]:
    """Convert a parsed CJK date to JDN(s).

    Returns list of (jdn, era_info) tuples. Multiple results when era name
    is ambiguous (same name used in different dynasties/countries).
    """
    eras = find_eras_by_name(conn, parsed.era, parsed.country_hint)
    if not eras:
        return []

    results: list[tuple[int, EraInfo]] = []

    for era_row in eras:
        era_id = era_row["era_id"]
        months = find_month(
            conn, era_id, parsed.year,
            parsed.month, parsed.is_leap_month,
        )

        for month_row in months:
            if parsed.day is not None:
                day_offset = parsed.day - month_row["start_from"]
                jdn = month_row["first_jdn"] + day_offset
                # Validate JDN is within month range
                if jdn > month_row["last_jdn"]:
                    continue
            else:
                # No day specified, return first day of month
                jdn = month_row["first_jdn"]

            day_in_month = parsed.day if parsed.day is not None else month_row["start_from"]

            era_info = EraInfo(
                era_name=era_row["era_name"],
                era_id=era_id,
                emperor_name=era_row["emperor_name"],
                dynasty_name=era_row["dynasty_name"],
                country=era_row["country"],
                year_in_era=parsed.year,
                month=month_row["month"],
                month_name=month_row["month_name"],
                is_leap_month=bool(month_row["leap_month"]),
                day=day_in_month,
            )
            results.append((jdn, era_info))

    return results


def convert_jdn(
    conn: sqlite3.Connection,
    jdn: int,
) -> DateConversion:
    """Convert a JDN to all calendar representations."""
    g_year, g_month, g_day = jdn_to_gregorian(jdn)
    gregorian = format_date(g_year, g_month, g_day)

    # Include Julian date for pre-1582 dates
    # Gregorian reform: Oct 15, 1582 = JDN 2299161
    julian_str: str | None = None
    if jdn < 2299161:
        j_year, j_month, j_day = jdn_to_julian(jdn)
        julian_str = format_date(j_year, j_month, j_day)

    ganzhi_day = jdn_to_ganzhi_day(jdn)
    ganzhi_year = ""
    ganzhi_month_str = ""

    # Find all CJK era representations
    month_rows = find_date_by_jdn(conn, jdn)
    cjk_dates: list[EraInfo] = []

    for row in month_rows:
        day_in_month = jdn - row["first_jdn"] + row["start_from"]
        cjk_dates.append(EraInfo(
            era_name=row["era_name"],
            era_id=row["era_id"],
            emperor_name=row["emperor_name"],
            dynasty_name=row["dynasty_name"],
            country=row["country"],
            year_in_era=row["year"],
            month=row["month"],
            month_name=row["month_name"],
            is_leap_month=bool(row["leap_month"]),
            day=day_in_month,
        ))
        # Use the first Chinese result's ganzhi for the year/month ganzhi
        if not ganzhi_year and row["ganzhi"]:
            ganzhi_year = row["ganzhi"]
            if not row["leap_month"]:
                ganzhi_month_str = month_ganzhi(ganzhi_year, row["month"])

    return DateConversion(
        jdn=jdn,
        gregorian=gregorian,
        julian=julian_str,
        ganzhi=GanzhiInfo(year=ganzhi_year, month=ganzhi_month_str, day=ganzhi_day),
        cjk_dates=cjk_dates,
    )


def get_era_metadata(
    conn: sqlite3.Connection,
    era_name: str | None = None,
    dynasty_name: str | None = None,
    country: str | None = None,
) -> list[EraMetadata]:
    """Get metadata for eras matching search criteria."""
    from .db import get_all_eras

    if era_name:
        rows = find_eras_by_name(conn, era_name, country)
    else:
        rows = get_all_eras(conn, country, dynasty_name)

    results = []
    for row in rows:
        start_greg = None
        end_greg = None
        if row["start_jdn"]:
            y, m, d = jdn_to_gregorian(row["start_jdn"])
            start_greg = format_date(y, m, d)
        if row["end_jdn"]:
            y, m, d = jdn_to_gregorian(row["end_jdn"])
            end_greg = format_date(y, m, d)

        results.append(EraMetadata(
            era_id=row["era_id"],
            era_name=row["era_name"],
            emperor_name=row["emperor_name"],
            dynasty_name=row["dynasty_name"],
            country=row["country"],
            start_jdn=row["start_jdn"],
            end_jdn=row["end_jdn"],
            start_gregorian=start_greg,
            end_gregorian=end_greg,
        ))

    return results
