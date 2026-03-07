"""
Verify converter output against DILA's authoritative date query service.

Uses data/dila_test_data.json (200 records fetched from DILA).
Tests JDN → CJK date conversion and ganzhi calculations.
"""

import json
import re
from pathlib import Path

import pytest

from src.calendar_converter.converter import (
    convert_jdn,
    jdn_to_gregorian,
    jdn_to_ganzhi_day,
    format_date,
)
from src.calendar_converter.db import get_connection

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "dila_test_data.json"

# Known discrepancies between DILA API and our SQL dump data.
# These are era name variants or year numbering differences in the source data,
# not converter bugs. Keyed by (JDN, DILA era name).
KNOWN_DISCREPANCIES = {
    (1866844, "燕平"),     # 南燕: DILA=燕平, our DB=燕王 (name variant)
    (1881319, "承和"),     # 北涼: DILA=承和, our DB=永和 (name variant)
    (2050863, "正開"),     # 後百濟: DILA=正開, our DB=（王年） (era not in dump)
    (2054394, "正開"),     # 後百濟: same
    (2058546, "正開"),     # 後百濟: same
    (2061813, "正開"),     # 後百濟: same
    (2209475, "建武"),     # 持明院統: DILA=建武4年, our DB=建武2年 (year offset)
}

# Chinese month name → month number
MONTH_MAP = {
    "正": 1, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
    "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "冬": 11,
    "十二": 12, "臘": 12,
}


def parse_ce_date(ce_date: str) -> str:
    """Convert DILA ceDate format (+YYYY-MM-DD) to our format (YYYY-MM-DD)."""
    if ce_date.startswith("+"):
        ce_date = ce_date[1:]
    return ce_date


def parse_lunar_month(s: str) -> int | None:
    """Convert Chinese month name to number."""
    return MONTH_MAP.get(s)


def load_dila_data() -> list[dict]:
    if not DATA_PATH.exists():
        pytest.skip("DILA test data not found. Run: uv run python -m data.scripts.fetch_dila_test_data")
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def db():
    conn = get_connection()
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def dila_data():
    return load_dila_data()


class TestGregorianConversion:
    """Verify JDN → Gregorian date matches DILA."""

    def test_gregorian_dates(self, dila_data):
        mismatches = []
        for record in dila_data:
            jdn = record["primary"]["jdn"]
            expected = parse_ce_date(record["primary"]["ce_date"])
            y, m, d = jdn_to_gregorian(jdn)
            actual = format_date(y, m, d)
            if actual != expected:
                mismatches.append(f"JDN {jdn}: expected {expected}, got {actual}")

        assert not mismatches, (
            f"{len(mismatches)} Gregorian mismatches:\n" + "\n".join(mismatches[:20])
        )


class TestCJKConversion:
    """Verify JDN → CJK calendar data matches DILA."""

    def test_era_and_year(self, db, dila_data):
        """Check that our converter finds the correct era and year for each JDN."""
        mismatches = []
        missing = []

        for record in dila_data:
            for dila_entry in record["all_calendars"]:
                jdn = dila_entry["jdn"]
                dila_era = dila_entry["era"]
                dila_year = dila_entry["year_number"]
                dila_dynasty = dila_entry["dynasty"]

                # Skip entries with parenthetical era names (Korean regnal years,
                # Japanese pre-era emperor names like (推古)9年)
                if "（" in dila_era or "）" in dila_era:
                    continue
                if "(" in dila_era or ")" in dila_era:
                    continue

                result = convert_jdn(db, jdn)
                found = False
                for cjk in result.cjk_dates:
                    if cjk.era_name == dila_era and cjk.year_in_era == dila_year:
                        found = True
                        break

                if not found:
                    if (jdn, dila_era) in KNOWN_DISCREPANCIES:
                        continue
                    our_eras = [(c.era_name, c.year_in_era, c.dynasty_name)
                                for c in result.cjk_dates]
                    mismatches.append(
                        f"JDN {jdn}: DILA={dila_dynasty} {dila_era}{dila_year}年, "
                        f"ours={our_eras}"
                    )

        assert not mismatches, (
            f"{len(mismatches)} era/year mismatches:\n" + "\n".join(mismatches[:20])
        )

    def test_lunar_month_and_day(self, db, dila_data):
        """Check lunar month and day match DILA."""
        mismatches = []

        for record in dila_data:
            for dila_entry in record["all_calendars"]:
                jdn = dila_entry["jdn"]
                dila_era = dila_entry["era"]
                dila_month_str = dila_entry["lunar_month"]
                dila_day = dila_entry["day_number"]
                dila_leap = dila_entry["leap_month"] == "1"

                if "（" in dila_era or "）" in dila_era:
                    continue

                dila_month = parse_lunar_month(dila_month_str)
                if dila_month is None:
                    continue

                result = convert_jdn(db, jdn)
                for cjk in result.cjk_dates:
                    if cjk.era_name == dila_era:
                        if cjk.month != dila_month:
                            mismatches.append(
                                f"JDN {jdn} {dila_era}: month DILA={dila_month_str}({dila_month}), "
                                f"ours={cjk.month}"
                            )
                        if cjk.day != dila_day:
                            mismatches.append(
                                f"JDN {jdn} {dila_era}: day DILA={dila_day}, ours={cjk.day}"
                            )
                        if cjk.is_leap_month != dila_leap:
                            mismatches.append(
                                f"JDN {jdn} {dila_era}: leap DILA={dila_leap}, "
                                f"ours={cjk.is_leap_month}"
                            )
                        break

        assert not mismatches, (
            f"{len(mismatches)} month/day mismatches:\n" + "\n".join(mismatches[:20])
        )


class TestGanzhiVerification:
    """Verify ganzhi calculations against DILA."""

    def test_year_ganzhi(self, db, dila_data):
        """Check year ganzhi matches DILA."""
        mismatches = []

        for record in dila_data:
            dila_entry = record["primary"]
            jdn = dila_entry["jdn"]
            dila_year_gz = dila_entry["year_ganzhi"]

            result = convert_jdn(db, jdn)
            if result.ganzhi.year and result.ganzhi.year != dila_year_gz:
                mismatches.append(
                    f"JDN {jdn}: year ganzhi DILA={dila_year_gz}, ours={result.ganzhi.year}"
                )

        assert not mismatches, (
            f"{len(mismatches)} year ganzhi mismatches:\n" + "\n".join(mismatches[:20])
        )

    def test_day_ganzhi(self, dila_data):
        """Check day ganzhi matches DILA."""
        mismatches = []

        for record in dila_data:
            dila_entry = record["primary"]
            jdn = dila_entry["jdn"]
            dila_day_gz = dila_entry["day_ganzhi"]

            actual = jdn_to_ganzhi_day(jdn)
            if actual != dila_day_gz:
                mismatches.append(
                    f"JDN {jdn}: day ganzhi DILA={dila_day_gz}, ours={actual}"
                )

        assert not mismatches, (
            f"{len(mismatches)} day ganzhi mismatches:\n" + "\n".join(mismatches[:20])
        )
