"""Tests for MCP server tool handlers."""

import json
from src.calendar_converter.mcp_server import _handle_tool_call


class TestMCPTools:
    def test_convert_cjk_date(self):
        result = json.loads(_handle_tool_call("convert_cjk_date", {"date": "崇禎三年四月初三"}))
        assert result["jdn"] == 2316539
        assert result["gregorian"] == "1630-05-14"
        assert result["ganzhi"]["year"] == "庚午"
        assert result["ganzhi"]["day"] == "壬子"  # verified against DILA
        assert len(result["cjk_dates"]) >= 1

    def test_convert_jdn(self):
        result = json.loads(_handle_tool_call("convert_jdn", {"jdn": 2316539}))
        assert result["gregorian"] == "1630-05-14"

    def test_convert_gregorian(self):
        result = json.loads(_handle_tool_call("convert_gregorian_date", {"date": "1630-05-14"}))
        assert result["jdn"] == 2316539

    def test_search_era(self):
        result = json.loads(_handle_tool_call("search_era", {"name": "崇禎"}))
        assert len(result) >= 1
        assert result[0]["era_name"] == "崇禎"
        assert result[0]["dynasty_name"] == "明"

    def test_search_era_by_dynasty(self):
        result = json.loads(_handle_tool_call("search_era", {"dynasty": "清"}))
        assert len(result) > 0

    def test_convert_unknown_era(self):
        result = json.loads(_handle_tool_call("convert_cjk_date", {"date": "不存在元年正月初一"}))
        assert "error" in result

    def test_convert_with_country(self):
        result = json.loads(_handle_tool_call(
            "convert_cjk_date",
            {"date": "寛永七年四月初三", "country": "japanese"},
        ))
        assert "jdn" in result

    def test_ambiguous_era_returns_candidates(self):
        """乾德二年 should flag ambiguity with other_candidates."""
        result = json.loads(_handle_tool_call("convert_cjk_date", {"date": "乾德二年正月初一"}))
        assert result["ambiguous"] is True
        assert len(result["other_candidates"]) >= 1
        dynasties = {c["dynasty_name"] for c in result["other_candidates"]}
        assert dynasties & {"北宋", "吳越"}

    def test_ambiguous_era_with_hint(self):
        """乾德二年 with dynasty=北宋 should not be ambiguous."""
        result = json.loads(_handle_tool_call(
            "convert_cjk_date",
            {"date": "乾德二年正月初一", "dynasty": "北宋"},
        ))
        assert result.get("ambiguous", False) is False
        assert result["gregorian"].startswith("0964")

    def test_unknown_tool(self):
        result = json.loads(_handle_tool_call("nonexistent", {}))
        assert "error" in result
