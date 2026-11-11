"""Tests for the data corrections (data/scripts/apply_corrections.py) and for the
date forms that depend on them: bracketed era names, reign names, and a numbered
year with a 干支 day."""

import shutil
import sqlite3

import pytest

from data.scripts.apply_corrections import DB_PATH, apply_corrections
from src.calendar_converter.converter import (
    convert_cjk_to_jdn,
    convert_jdn,
    gregorian_to_jdn,
    jdn_to_ganzhi_day,
    jdn_to_gregorian,
)
from src.calendar_converter.db import find_eras_by_name, get_connection
from src.calendar_converter.parser import parse_cjk_date


@pytest.fixture(scope="module")
def conn():
    c = get_connection()
    yield c
    c.close()


def convert(conn, text, country=None):
    parsed = parse_cjk_date(text)
    assert parsed is not None, text
    if country:
        parsed.country_hint = country
    return convert_cjk_to_jdn(conn, parsed)


def korean(conn, y, m, d):
    dates = convert_jdn(conn, gregorian_to_jdn(y, m, d)).cjk_dates
    return [(e.emperor_name, e.year_in_era, e.month, e.day) for e in dates if e.country == "korean"]


class TestEraNames:
    def test_jianshi(self, conn):
        western_han = [e for e in find_eras_by_name(conn, "建始") if e["dynasty_name"] == "西漢"]
        assert [e["emperor_name"] for e in western_han] == ["成帝"]
        assert find_eras_by_name(conn, "始建") == []
        results = [(j, e) for j, e in convert(conn, "建始三年正月", "chinese") if e.dynasty_name == "西漢"]
        assert [j for j, _ in results] == [1710510]

    def test_bracketed_names(self, conn):
        emperors = {e["emperor_name"] for e in find_eras_by_name(conn, "後元", "chinese")}
        assert {"武帝", "文帝", "景帝"} <= emperors
        assert [e["emperor_name"] for e in find_eras_by_name(conn, "中元", "chinese")] == ["景帝"]

    def test_exact_name_wins_over_reign_name(self, conn):
        # 崇禎 is an era name; the reign-name lookup must not add anything
        assert {e["era_name"] for e in find_eras_by_name(conn, "崇禎")} == {"崇禎"}


class TestReignNames:
    def test_han_years_without_an_era_name(self, conn):
        (jdn, era), = convert(conn, "文帝七年十月", "chinese")
        assert (era.era_name, era.dynasty_name, era.year_in_era) == ("（無年號）", "西漢", 7)

    def test_middle_and_later_years(self, conn):
        assert [e.era_name for _, e in convert(conn, "景帝中五年十月")] == ["（中元）"]
        assert [e.era_name for _, e in convert(conn, "文帝後三年十月")] == ["（後元）"]

    def test_korean_king(self, conn):
        (jdn, era), = convert(conn, "仁祖二十二年三月十九日", "korean")
        assert jdn_to_gregorian(jdn) == (1644, 4, 25)


class TestGanzhiDayWithNumberedYear:
    def test_parse(self):
        parsed = parse_cjk_date("建元六年六月丁酉")
        assert (parsed.era, parsed.year, parsed.month, parsed.day, parsed.ganzhi_day) == ("建元", 6, 6, None, "丁酉")
        assert parse_cjk_date("建元六年六月初七日").day == 7
        assert parse_cjk_date("建元六年六月").ganzhi_day is None

    def test_same_day_as_ganzhi_year_form(self, conn):
        a = [j for j, e in convert(conn, "建元六年六月丁酉") if e.dynasty_name == "西漢"]
        b = [j for j, e in convert(conn, "建元丙午年六月丁酉") if e.dynasty_name == "西漢"]
        assert a == b and len(a) == 1
        assert jdn_to_ganzhi_day(a[0]) == "丁酉"


class TestKoreanAccessionYears:
    """中宗 and 仁祖 count from the accession year, as in the Joseon Sillok."""

    def test_injo(self, conn):
        # 仁祖實錄 卷45: 仁祖 22년 3월 19일 丁未 = 1644-04-25
        assert korean(conn, 1644, 4, 25) == [("仁祖", 22, 3, 19)]
        assert jdn_to_ganzhi_day(gregorian_to_jdn(1644, 4, 25)) == "丁未"
        assert korean(conn, 1623, 4, 11) == [("光海君", 15, 3, 12)]
        assert korean(conn, 1623, 4, 12) == [("仁祖", 1, 3, 13)]
        assert korean(conn, 1650, 1, 31)[0][:2] == ("仁祖", 27)

    def test_jungjong(self, conn):
        assert korean(conn, 1506, 9, 27) == [("燕山君", 12, 9, 1)]
        assert korean(conn, 1506, 9, 28) == [("中宗", 1, 9, 2)]
        assert korean(conn, 1507, 1, 23)[0][:2] == ("中宗", 2)

    def test_other_kings_unchanged(self, conn):
        assert korean(conn, 1832, 6, 1)[0][:2] == ("純祖", 32)
        assert korean(conn, 1455, 7, 24)[0][:2] == ("世祖", 1)

    def test_no_gap_or_overlap(self, conn):
        for old, new in (("燕山君", "中宗"), ("光海君", "仁祖")):
            ids = [find_eras_by_name(conn, k, "korean")[0]["era_id"] for k in (old, new)]
            rows = conn.execute(
                "SELECT first_jdn, last_jdn FROM month WHERE era_id IN (?, ?) ORDER BY first_jdn", ids
            ).fetchall()
            for a, b in zip(rows, rows[1:]):
                assert b["first_jdn"] == a["last_jdn"] + 1


def test_apply_corrections_is_idempotent(tmp_path):
    copy = tmp_path / "calendar.db"
    shutil.copy(DB_PATH, copy)
    assert apply_corrections(copy) == []
    c = sqlite3.connect(copy)
    keys = {r[0] for r in c.execute("SELECT key FROM data_correction")}
    c.close()
    assert keys == {"era-jianshi", "korea-jungjong", "korea-injo"}
