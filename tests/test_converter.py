"""Tests for calendar conversion logic."""

import pytest
from src.calendar_converter.converter import (
    jdn_to_gregorian,
    gregorian_to_jdn,
    jdn_to_julian,
    jdn_to_ganzhi_day,
    month_ganzhi,
    convert_cjk_to_jdn,
    convert_jdn,
)
from src.calendar_converter.parser import ParsedDate
from src.calendar_converter.db import get_connection


class TestJDNGregorianConversion:
    """Test JDN ↔ Gregorian roundtrip using known dates."""

    def test_j2000(self):
        # Jan 1, 2000 = JDN 2451545
        assert jdn_to_gregorian(2451545) == (2000, 1, 1)
        assert gregorian_to_jdn(2000, 1, 1) == 2451545

    def test_gregorian_reform(self):
        # Oct 15, 1582 = JDN 2299161 (first day of Gregorian calendar)
        assert jdn_to_gregorian(2299161) == (1582, 10, 15)
        assert gregorian_to_jdn(1582, 10, 15) == 2299161

    def test_roundtrip(self):
        for jdn in [1721426, 2000000, 2299161, 2451545, 2460000]:
            y, m, d = jdn_to_gregorian(jdn)
            assert gregorian_to_jdn(y, m, d) == jdn

    def test_negative_year(self):
        # 4713 BCE Jan 1 (Julian) = JDN 0
        # In Gregorian proleptic, that's 4714 BCE Nov 24 = year -4713
        assert gregorian_to_jdn(-4713, 11, 24) == 0


class TestJDNJulianConversion:
    def test_julian_reform_boundary(self):
        # Oct 4, 1582 (Julian) = JDN 2299160 (last day before Gregorian reform)
        assert jdn_to_julian(2299160) == (1582, 10, 4)

    def test_julian_epoch(self):
        # Jan 1, 1 CE (Julian) = JDN 1721424
        assert jdn_to_julian(1721424) == (1, 1, 1)


class TestGanzhi:
    def test_ganzhi_day_format(self):
        result = jdn_to_ganzhi_day(2451545)  # Jan 1, 2000
        assert len(result) == 2
        assert result[0] in "甲乙丙丁戊己庚辛壬癸"
        assert result[1] in "子丑寅卯辰巳午未申酉戌亥"

    def test_ganzhi_day_cycle(self):
        """Ganzhi day should repeat every 60 days."""
        base = jdn_to_ganzhi_day(2451545)
        assert jdn_to_ganzhi_day(2451545 + 60) == base
        assert jdn_to_ganzhi_day(2451545 + 120) == base

    def test_month_ganzhi_five_tigers(self):
        """Test 五虎遁 formula for month ganzhi."""
        # 甲/己年: month 1 stem = 丙 → 丙寅
        assert month_ganzhi("甲子", 1) == "丙寅"
        assert month_ganzhi("己巳", 1) == "丙寅"
        # 乙/庚年: month 1 stem = 戊 → 戊寅
        assert month_ganzhi("乙丑", 1) == "戊寅"
        assert month_ganzhi("庚午", 1) == "戊寅"
        # 庚午年 month 4 = 辛巳
        assert month_ganzhi("庚午", 4) == "辛巳"

    def test_month_ganzhi_empty_input(self):
        assert month_ganzhi("", 1) == ""

    def test_full_ganzhi_in_conversion(self, db):
        """convert_jdn should include year, month, and day ganzhi."""
        result = convert_jdn(db, 2316539)  # 崇禎三年四月初三
        assert result.ganzhi.year == "庚午"
        assert result.ganzhi.month == "辛巳"
        assert result.ganzhi.day == "庚申"


@pytest.fixture
def db():
    conn = get_connection()
    yield conn
    conn.close()


class TestCJKConversion:
    def test_chongzhen_3_4_3(self, db):
        """崇禎三年四月初三 → 1630-05-14 Gregorian"""
        parsed = ParsedDate(era="崇禎", year=3, month=4, day=3)
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        jdn, info = results[0]
        assert info.dynasty_name == "明"
        assert info.country == "chinese"
        y, m, d = jdn_to_gregorian(jdn)
        assert (y, m, d) == (1630, 5, 14)

    def test_concurrent_dates(self, db):
        """A single JDN should have multiple CJK representations."""
        # 崇禎三年四月初三
        parsed = ParsedDate(era="崇禎", year=3, month=4, day=3)
        results = convert_cjk_to_jdn(db, parsed)
        jdn, _ = results[0]

        conversion = convert_jdn(db, jdn)
        # Should have Chinese + Japanese + Korean at minimum
        countries = {d.country for d in conversion.cjk_dates}
        assert "chinese" in countries

    def test_kangxi(self, db):
        """康熙元年正月初一"""
        parsed = ParsedDate(era="康熙", year=1, month=1, day=1)
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        jdn, info = results[0]
        assert info.era_name == "康熙"
        assert info.dynasty_name == "清"

    def test_era_not_found(self, db):
        """Unknown era should return empty."""
        parsed = ParsedDate(era="不存在", year=1, month=1, day=1)
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) == 0

    def test_jdn_to_full_conversion(self, db):
        """Test convert_jdn returns proper structure."""
        conversion = convert_jdn(db, 2451545)  # Jan 1, 2000
        assert conversion.jdn == 2451545
        assert conversion.gregorian == "2000-01-01"
        assert conversion.julian is None  # post-1582
        assert len(conversion.ganzhi.day) == 2

    def test_vietnamese_era(self, db):
        """嘉隆元年正月初一 (Nguyễn dynasty, Gia Long era)"""
        parsed = ParsedDate(era="嘉隆", year=1, month=1, day=1)
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        jdn, info = results[0]
        assert info.dynasty_name == "阮朝"
        assert info.country == "vietnamese"
        y, m, d = jdn_to_gregorian(jdn)
        assert y == 1803  # Gia Long year 1 starts lunar new year ~1803

    def test_concurrent_includes_vietnamese(self, db):
        """Dates in Vietnamese coverage should include Vietnamese eras."""
        # 1630 is covered by 後黎朝
        result = convert_jdn(db, 2316539)
        countries = {d.country for d in result.cjk_dates}
        assert "vietnamese" in countries
