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
        assert result.ganzhi.day == "壬子"  # verified against DILA


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

    def test_ganzhi_full_date(self, db):
        """崇禎庚午年辛巳月壬子日 = 崇禎三年四月初三 = 1630-05-14"""
        parsed = ParsedDate(
            era="崇禎", ganzhi_year="庚午",
            ganzhi_month="辛巳", ganzhi_day="壬子",
        )
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        jdn, info = results[0]
        assert info.year_in_era == 3
        assert info.month == 4
        assert info.day == 3
        y, m, d = jdn_to_gregorian(jdn)
        assert (y, m, d) == (1630, 5, 14)

    def test_ganzhi_year_with_numeric_month_day(self, db):
        """崇禎庚午年四月初三 = same as above"""
        parsed = ParsedDate(
            era="崇禎", ganzhi_year="庚午", month=4, day=3,
        )
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        jdn, info = results[0]
        assert info.year_in_era == 3
        y, m, d = jdn_to_gregorian(jdn)
        assert (y, m, d) == (1630, 5, 14)


class TestDisambiguation:
    """Test dynasty/emperor hints for intra-dynasty era name disambiguation."""

    def test_shangyuan_no_hint(self, db):
        """上元二年 without hint returns both Tang uses (高宗 675 and 肅宗 761)."""
        parsed = ParsedDate(era="上元", year=2, month=1, day=1)
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) == 2
        emperors = {info.emperor_name for _, info in results}
        assert "高宗" in emperors
        assert "肅宗" in emperors

    def test_shangyuan_emperor_hint(self, db):
        """上元二年 with emperor=肅宗 returns only 肅宗's era (761 CE)."""
        parsed = ParsedDate(era="上元", year=2, month=1, day=1, emperor_hint="肅宗")
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) == 1
        jdn, info = results[0]
        assert info.emperor_name == "肅宗"
        y, m, d = jdn_to_gregorian(jdn)
        assert y == 761

    def test_shangyuan_dynasty_emperor_hint(self, db):
        """上元二年 with dynasty=唐, emperor=高宗 returns 675 CE."""
        parsed = ParsedDate(era="上元", year=2, month=1, day=1,
                            dynasty_hint="唐", emperor_hint="高宗")
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) == 1
        jdn, info = results[0]
        assert info.emperor_name == "高宗"
        y, m, d = jdn_to_gregorian(jdn)
        assert y == 675

    def test_zhiyuan_yuan_dynasty_hint(self, db):
        """至元 in Yuan: dynasty hint narrows to Yuan only (not 西夏 etc.)."""
        parsed = ParsedDate(era="至元", year=20, month=1, day=1, dynasty_hint="元")
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) == 1
        _, info = results[0]
        assert info.dynasty_name == "元"
        assert info.emperor_name == "世祖"

    def test_zhiyuan_shundi(self, db):
        """至元三年 with emperor=順帝 returns 1337, not 世祖's era."""
        parsed = ParsedDate(era="至元", year=3, month=1, day=1,
                            dynasty_hint="元", emperor_hint="順帝")
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) == 1
        jdn, info = results[0]
        assert info.emperor_name == "順帝"
        y, m, d = jdn_to_gregorian(jdn)
        assert y == 1337

    def test_country_hint_still_works(self, db):
        """country_hint should still filter as before."""
        parsed = ParsedDate(era="貞觀", year=3, month=1, day=1, country_hint="chinese")
        results = convert_cjk_to_jdn(db, parsed)
        for _, info in results:
            assert info.country == "chinese"

    def test_dynasty_hint_song(self, db):
        """開寶三年 with dynasty=北宋 excludes 吳越."""
        parsed = ParsedDate(era="開寶", year=3, month=1, day=1, dynasty_hint="北宋")
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) == 1
        _, info = results[0]
        assert info.dynasty_name == "北宋"


class TestCnEraConversions:
    """Test cases derived from the cn-era NPM package (CBDB-based).

    cn-era operates at year level (Gregorian year -> era name). These tests
    verify our month-level data is consistent with CBDB's era year boundaries.
    """

    def test_tang_wude(self, db):
        """Tang 武德二年正月 = 619 CE (year 1 starts mid-year in month 5)."""
        parsed = ParsedDate(era="武德", year=2, month=1, day=1, dynasty_hint="唐")
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        y, _, _ = jdn_to_gregorian(results[0][0])
        assert y == 619

    def test_tang_zhenguan_year1(self, db):
        """Tang 貞觀元年 = 627 CE."""
        parsed = ParsedDate(era="貞觀", year=1, month=1, day=1, dynasty_hint="唐")
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        y, _, _ = jdn_to_gregorian(results[0][0])
        assert y == 627

    def test_tang_kaiyuan(self, db):
        """Tang 開元二年正月 = 714 CE (year 1 starts in month 12)."""
        parsed = ParsedDate(era="開元", year=2, month=1, day=1)
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        y, _, _ = jdn_to_gregorian(results[0][0])
        assert y == 714

    def test_tang_tianbao(self, db):
        """Tang 天寶元年 = 742 CE."""
        parsed = ParsedDate(era="天寶", year=1, month=1, day=1, dynasty_hint="唐")
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        y, _, _ = jdn_to_gregorian(results[0][0])
        assert y == 742

    def test_song_jianlong_year1(self, db):
        """Song 建隆元年 = 960 CE."""
        parsed = ParsedDate(era="建隆", year=1, month=1, day=1)
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        y, _, _ = jdn_to_gregorian(results[0][0])
        assert y == 960

    def test_yuan_zhongtong(self, db):
        """Yuan 中統二年正月 = 1261 CE (year 1 starts in month 5)."""
        parsed = ParsedDate(era="中統", year=2, month=1, day=1)
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        y, _, _ = jdn_to_gregorian(results[0][0])
        assert y == 1261

    def test_yuan_zhiyuan_shizu(self, db):
        """Yuan 至元(世祖) year 17 = 1280 CE."""
        parsed = ParsedDate(era="至元", year=17, month=1, day=1,
                            dynasty_hint="元", emperor_hint="世祖")
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) == 1
        y, _, _ = jdn_to_gregorian(results[0][0])
        assert y == 1280

    def test_yuan_zhiyuan_shundi(self, db):
        """Yuan 至元(順帝) year 1 = 1335 CE."""
        parsed = ParsedDate(era="至元", year=1, month=1, day=1,
                            dynasty_hint="元", emperor_hint="順帝")
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) == 1
        y, _, _ = jdn_to_gregorian(results[0][0])
        assert y == 1335

    def test_ming_hongwu(self, db):
        """Ming 洪武元年 = 1368 CE."""
        parsed = ParsedDate(era="洪武", year=1, month=1, day=1, dynasty_hint="明")
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        y, _, _ = jdn_to_gregorian(results[0][0])
        assert y == 1368

    def test_ming_yongle(self, db):
        """Ming 永樂元年 = 1403 CE."""
        parsed = ParsedDate(era="永樂", year=1, month=1, day=1, dynasty_hint="明")
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        y, _, _ = jdn_to_gregorian(results[0][0])
        assert y == 1403

    def test_ming_wanli(self, db):
        """Ming 萬曆元年 = 1573 CE."""
        parsed = ParsedDate(era="萬曆", year=1, month=1, day=1, dynasty_hint="明")
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        y, _, _ = jdn_to_gregorian(results[0][0])
        assert y == 1573

    def test_ming_chongzhen(self, db):
        """Ming 崇禎元年 = 1628 CE."""
        parsed = ParsedDate(era="崇禎", year=1, month=1, day=1)
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        y, _, _ = jdn_to_gregorian(results[0][0])
        assert y == 1628

    def test_qing_shunzhi(self, db):
        """Qing 順治元年 = 1644 CE."""
        parsed = ParsedDate(era="順治", year=1, month=1, day=1, dynasty_hint="清")
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        y, _, _ = jdn_to_gregorian(results[0][0])
        assert y == 1644

    def test_qing_kangxi(self, db):
        """Qing 康熙元年 = 1662 CE."""
        parsed = ParsedDate(era="康熙", year=1, month=1, day=1, dynasty_hint="清")
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        y, _, _ = jdn_to_gregorian(results[0][0])
        assert y == 1662

    def test_qing_qianlong(self, db):
        """Qing 乾隆元年 = 1736 CE."""
        parsed = ParsedDate(era="乾隆", year=1, month=1, day=1)
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        y, _, _ = jdn_to_gregorian(results[0][0])
        assert y == 1736

    def test_qing_guangxu(self, db):
        """Qing 光緒元年 = 1875 CE."""
        parsed = ParsedDate(era="光緒", year=1, month=1, day=1, dynasty_hint="清")
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        y, _, _ = jdn_to_gregorian(results[0][0])
        assert y == 1875

    def test_three_kingdoms_wei(self, db):
        """Wei 黃初二年正月 = 221 CE (year 1 starts in month 10)."""
        parsed = ParsedDate(era="黃初", year=2, month=1, day=1, dynasty_hint="曹魏")
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        y, _, _ = jdn_to_gregorian(results[0][0])
        assert y == 221

    def test_western_jin_taishi(self, db):
        """Western Jin 泰始二年正月 = 266 CE (year 1 starts in month 12)."""
        parsed = ParsedDate(era="泰始", year=2, month=1, day=1, dynasty_hint="西晉")
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        y, _, _ = jdn_to_gregorian(results[0][0])
        assert y == 266

    def test_concurrent_eras_jingkang(self, db):
        """靖康 (1126-1127): should exist in our data."""
        parsed = ParsedDate(era="靖康", year=1, month=1, day=1)
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        y, _, _ = jdn_to_gregorian(results[0][0])
        assert y == 1126

    def test_liao_era(self, db):
        """Liao 天顯二年正月 should exist (year 1 starts in month 2)."""
        parsed = ParsedDate(era="天顯", year=2, month=1, day=1, dynasty_hint="遼")
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        _, info = results[0]
        assert info.dynasty_name == "遼"

    def test_xixia_era(self, db):
        """Xi Xia 大慶二年正月 should exist (year 1 starts in month 12)."""
        parsed = ParsedDate(era="大慶", year=2, month=1, day=1, dynasty_hint="西夏")
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        _, info = results[0]
        assert info.dynasty_name == "西夏"

    def test_jin_dynasty_tianhui(self, db):
        """Jin 天會二年正月 should map to Jin dynasty (year 1 starts in month 9)."""
        parsed = ParsedDate(era="天會", year=2, month=1, day=1, dynasty_hint="金")
        results = convert_cjk_to_jdn(db, parsed)
        assert len(results) >= 1
        _, info = results[0]
        assert info.dynasty_name == "金"
