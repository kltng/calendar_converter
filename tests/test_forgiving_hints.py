"""Hints and spellings that a person or a small language model gets slightly wrong.

These come from real tool calls made by a 0.6B model in class: it added
country "中国" or "China" to almost every call, guessed dynasties, and students
typed era names in simplified characters. Each of these used to return an error.
"""

import asyncio
import json

import pytest

from src.calendar_converter.db import canonical_country, find_eras_by_name, get_connection, name_variants
from src.calendar_converter.converter import normalize_date_text
from src.calendar_converter.mcp_http import mcp as http_mcp
from src.calendar_converter.mcp_server import _handle_tool_call, mcp as stdio_mcp


def convert(**arguments):
    return json.loads(_handle_tool_call("convert_cjk_date", arguments))


class TestCountryAliases:
    @pytest.mark.parametrize("value", ["chinese", "Chinese", "CHINA", "China", "中国", "中國", " cn "])
    def test_chinese(self, value):
        assert canonical_country(value) == "chinese"

    @pytest.mark.parametrize("value,expected", [
        ("Japan", "japanese"), ("日本", "japanese"), ("Korea", "korean"), ("韩国", "korean"),
        ("朝鮮", "korean"), ("Vietnam", "vietnamese"), ("越南", "vietnamese"),
    ])
    def test_others(self, value, expected):
        assert canonical_country(value) == expected

    @pytest.mark.parametrize("value", [None, "", "Western", "Jpn."])
    def test_unknown(self, value):
        assert canonical_country(value) is None

    @pytest.mark.parametrize("country", ["中国", "China", "Chinese", "chinese", None])
    def test_convert_accepts_any_spelling(self, country):
        result = convert(date="崇禎三年四月初三", country=country)
        assert result["gregorian"] == "1630-05-14"
        assert result["notes"] == []

    def test_search_era_accepts_alias(self):
        result = json.loads(_handle_tool_call("search_era", {"name": "天保", "country": "日本"}))
        assert result and {era["country"] for era in result} == {"japanese"}


class TestWrongHintsAreDropped:
    def test_unknown_country_is_ignored_and_reported(self):
        result = convert(date="崇禎三年四月初三", country="Western")
        assert result["gregorian"] == "1630-05-14"
        assert any("country 'Western'" in note for note in result["notes"])

    def test_wrong_country_is_ignored_and_reported(self):
        result = convert(date="崇禎三年四月初三", country="japanese")
        assert result["gregorian"] == "1630-05-14"
        assert any("country 'japanese'" in note for note in result["notes"])

    def test_era_given_as_dynasty(self):
        result = convert(date="崇禎三年四月初三", country="中国", dynasty="崇禎")
        assert result["gregorian"] == "1630-05-14"
        assert result["notes"] == ["dynasty '崇禎' does not fit this date, so it was ignored"]

    def test_nonsense_dynasty_and_emperor(self):
        result = convert(date="光緒二十四年三月廿七日", country="中国", dynasty="LION King", emperor="光緒")
        assert result["gregorian"] == "1898-04-17"
        assert len(result["notes"]) == 2

    def test_empty_strings_count_as_no_hint(self):
        result = convert(date="崇禎三年四月初三", country="", dynasty=" ", emperor="")
        assert result["gregorian"] == "1630-05-14"
        assert result["notes"] == []

    def test_a_good_hint_still_disambiguates(self):
        result = convert(date="乾德二年正月初一", dynasty="北宋")
        assert result["ambiguous"] is False
        assert result["gregorian"].startswith("0964")
        assert result["notes"] == []

    def test_a_dropped_hint_never_hides_ambiguity(self):
        result = convert(date="乾德二年正月初一", dynasty="LION King")
        assert result["ambiguous"] is True
        assert result["other_candidates"]
        assert result["notes"]

    def test_dynasty_with_suffix(self):
        result = convert(date="乾德二年正月初一", dynasty="北宋朝")
        assert result["ambiguous"] is False
        assert result["gregorian"].startswith("0964")

    def test_shorthand_keeps_its_own_country(self):
        result = convert(date="M5.7.30", country="中国")
        assert result["gregorian"] == "1872-09-02"
        assert any("country '中国'" in note for note in result["notes"])


class TestSimplifiedCharacters:
    @pytest.mark.parametrize("simplified_date,traditional_date", [
        ("崇祯三年四月初三", "崇禎三年四月初三"),
        ("光绪二十四年三月廿七日", "光緒二十四年三月廿七日"),
        ("万历十五年六月初一", "萬曆十五年六月初一"),
        ("文帝后三年正月", "文帝後三年正月"),
    ])
    def test_same_answer_as_traditional(self, simplified_date, traditional_date):
        assert convert(date=simplified_date)["jdn"] == convert(date=traditional_date)["jdn"]

    def test_leap_month_marker(self):
        assert normalize_date_text(" 万历 二十年 闰三月 初一 ") == "万历二十年閏三月初一"

    def test_simplified_dynasty_hint(self):
        conn = get_connection()
        try:
            assert name_variants(conn, "dynasty_name", "东汉") == ["東漢"]
            assert name_variants(conn, "dynasty_name", "明朝") == ["明"]
            assert name_variants(conn, "era_name", "不存在") == []
            assert {row["era_name"] for row in find_eras_by_name(conn, "崇祯")} == {"崇禎"}
        finally:
            conn.close()

    def test_search_era_in_simplified(self):
        result = json.loads(_handle_tool_call("search_era", {"name": "崇祯"}))
        assert result[0]["era_name"] == "崇禎"

    def test_exact_spelling_wins_over_variants(self):
        # 大宝 and 大寶 are different eras that share one simplified form.
        conn = get_connection()
        try:
            assert {row["era_name"] for row in find_eras_by_name(conn, "大宝")} == {"大宝"}
            assert {row["era_name"] for row in find_eras_by_name(conn, "大寶")} == {"大寶"}
        finally:
            conn.close()


class TestErrors:
    def test_chinese_is_readable_not_escaped(self):
        raw = _handle_tool_call("convert_cjk_date", {"date": "不存在元年正月初一"})
        assert "不存在" in raw and "\\u" not in raw
        assert json.loads(raw)["hint"]

    def test_wrong_year_lists_the_era_years(self):
        # There is no thirteenth month.
        result = convert(date="崇禎三年十三月初一")
        assert "found but no match for year 3" in result["error"]
        candidate = result["candidates"][0]
        assert candidate["dynasty"] == "明" and candidate["country"] == "chinese"
        assert candidate["first_year"] == 1628

    def test_unparseable(self):
        result = convert(date="next Tuesday")
        assert result["error"].startswith("Cannot parse date") and result["hint"]

    def test_bad_gregorian(self):
        result = json.loads(_handle_tool_call("convert_gregorian_date", {"date": "May 14, 1630"}))
        assert "YYYY-MM-DD" in result["hint"]


class TestToolDescriptions:
    """What a model reads before calling. Both servers must publish the same text."""

    @pytest.mark.parametrize("server", [stdio_mcp, http_mcp])
    def test_convert_cjk_date_says_what_to_pass(self, server):
        tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
        assert set(tools) == {"convert_cjk_date", "convert_jdn", "convert_gregorian_date", "search_era"}
        tool = tools["convert_cjk_date"]
        assert "Usually pass only `date`" in tool.description
        schema = tool.inputSchema
        assert schema["required"] == ["date"]
        country = schema["properties"]["country"]["description"]
        for value in ("chinese", "japanese", "korean", "vietnamese"):
            assert value in country
        for name in ("date", "dynasty", "emperor"):
            assert schema["properties"][name]["description"]

    def test_both_servers_publish_the_same_tools(self):
        def published(server):
            return [(t.name, t.description, t.inputSchema) for t in asyncio.run(server.list_tools())]
        assert published(stdio_mcp) == published(http_mcp)
