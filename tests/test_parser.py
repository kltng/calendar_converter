"""Tests for CJK date string parser."""

from src.calendar_converter.parser import parse_cjk_date, _parse_chinese_number


class TestParseChineseNumber:
    def test_single_digits(self):
        assert _parse_chinese_number("一") == 1
        assert _parse_chinese_number("九") == 9

    def test_ten(self):
        assert _parse_chinese_number("十") == 10

    def test_teens(self):
        assert _parse_chinese_number("十一") == 11
        assert _parse_chinese_number("十九") == 19

    def test_tens(self):
        assert _parse_chinese_number("二十") == 20
        assert _parse_chinese_number("三十") == 30

    def test_twenties(self):
        assert _parse_chinese_number("二十九") == 29
        assert _parse_chinese_number("二十一") == 21

    def test_shorthand(self):
        assert _parse_chinese_number("廿九") == 29
        assert _parse_chinese_number("卅") == 30

    def test_chu_prefix(self):
        assert _parse_chinese_number("初一") == 1
        assert _parse_chinese_number("初三") == 3
        assert _parse_chinese_number("初十") == 10

    def test_special(self):
        assert _parse_chinese_number("元") == 1
        assert _parse_chinese_number("正") == 1

    def test_larger_numbers(self):
        assert _parse_chinese_number("六十一") == 61


class TestParseCJKDate:
    def test_chongzhen(self):
        d = parse_cjk_date("崇禎三年四月初三")
        assert d is not None
        assert d.era == "崇禎"
        assert d.year == 3
        assert d.month == 4
        assert d.day == 3
        assert d.is_leap_month is False

    def test_leap_month(self):
        d = parse_cjk_date("天保三年閏九月十五日")
        assert d is not None
        assert d.era == "天保"
        assert d.year == 3
        assert d.month == 9
        assert d.day == 15
        assert d.is_leap_month is True

    def test_kangxi(self):
        d = parse_cjk_date("康熙六十一年十二月二十九日")
        assert d is not None
        assert d.era == "康熙"
        assert d.year == 61
        assert d.month == 12
        assert d.day == 29

    def test_yuan_year(self):
        d = parse_cjk_date("崇禎元年正月初一")
        assert d is not None
        assert d.year == 1
        assert d.month == 1
        assert d.day == 1

    def test_year_only(self):
        d = parse_cjk_date("崇禎三年")
        assert d is not None
        assert d.era == "崇禎"
        assert d.year == 3
        assert d.month is None
        assert d.day is None

    def test_year_month_no_day(self):
        d = parse_cjk_date("崇禎三年四月")
        assert d is not None
        assert d.month == 4
        assert d.day is None

    def test_japanese_shorthand(self):
        d = parse_cjk_date("M45.7.30")
        assert d is not None
        assert d.era == "明治"
        assert d.year == 45
        assert d.month == 7
        assert d.day == 30
        assert d.country_hint == "japanese"

    def test_japanese_heisei(self):
        d = parse_cjk_date("H26.6.8")
        assert d is not None
        assert d.era == "平成"
        assert d.year == 26
        assert d.month == 6
        assert d.day == 8

    def test_empty_returns_none(self):
        assert parse_cjk_date("") is None
        assert parse_cjk_date("  ") is None

    def test_invalid_returns_none(self):
        assert parse_cjk_date("hello world") is None
