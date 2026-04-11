"""
MCP (Model Context Protocol) server for CJK calendar conversion.

Exposes calendar conversion as tools that LLMs can call directly.
Supports both stdio and SSE transports.

Run with:
  stdio: uv run python -m src.calendar_converter.mcp_server
  SSE:   uv run python -m src.calendar_converter.mcp_server --transport sse
"""

import argparse
import json
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from .converter import (
    build_ambiguous_candidates,
    convert_cjk_to_jdn,
    convert_jdn as _convert_jdn,
    get_era_metadata,
    gregorian_to_jdn,
    format_date,
)
from .db import get_connection
from .parser import parse_cjk_date


mcp = FastMCP(
    "cjk-calendar-converter",
    host="127.0.0.1",
    port=8000,
)


def _handle_tool_call(name: str, arguments: dict[str, Any]) -> str:
    """Execute a tool call and return JSON result."""
    conn = get_connection()
    try:
        if name == "convert_cjk_date":
            parsed = parse_cjk_date(arguments["date"])
            if parsed is None:
                return json.dumps({"error": f"Cannot parse date: {arguments['date']}"})

            if "country" in arguments:
                parsed.country_hint = arguments["country"]
            if "dynasty" in arguments:
                parsed.dynasty_hint = arguments["dynasty"]
            if "emperor" in arguments:
                parsed.emperor_hint = arguments["emperor"]

            results = convert_cjk_to_jdn(conn, parsed)
            if not results:
                from .db import find_eras_by_name
                candidates = find_eras_by_name(conn, parsed.era)
                if candidates:
                    era_list = [
                        {"era": r["era_name"], "dynasty": r["dynasty_name"],
                         "country": r["country"]}
                        for r in candidates
                    ]
                    return json.dumps({
                        "error": f"Era '{parsed.era}' found but no match for year {parsed.year}",
                        "candidates": era_list,
                    })
                return json.dumps({"error": f"Era '{parsed.era}' not found"})

            jdn_val, _ = results[0]
            conversion = _convert_jdn(conn, jdn_val)

            distinct_era_ids = {info.era_id for _, info in results}
            if len(distinct_era_ids) > 1:
                conversion.ambiguous = True
                conversion.other_candidates = build_ambiguous_candidates(results)

            return conversion.model_dump_json()

        elif name == "convert_jdn":
            conversion = _convert_jdn(conn, arguments["jdn"])
            return conversion.model_dump_json()

        elif name == "convert_gregorian_date":
            parts = arguments["date"].split("-")
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            jdn = gregorian_to_jdn(y, m, d)
            conversion = _convert_jdn(conn, jdn)
            return conversion.model_dump_json()

        elif name == "search_era":
            eras = get_era_metadata(
                conn,
                era_name=arguments.get("name"),
                dynasty_name=arguments.get("dynasty"),
                country=arguments.get("country"),
            )
            return json.dumps([e.model_dump() for e in eras])

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})
    finally:
        conn.close()


@mcp.tool()
def convert_cjk_date(
    date: str,
    country: str | None = None,
    dynasty: str | None = None,
    emperor: str | None = None,
) -> str:
    """Convert a CJK (Chinese/Japanese/Korean/Vietnamese) historical date to Julian Day Number and equivalent dates in all concurrent calendars.

    Input examples: '崇禎三年四月初三', '康熙元年正月初一', '寛永七年四月初三', 'M45.7.30'.
    Returns JDN, Gregorian date, Julian date (pre-1582), ganzhi (干支),
    and all concurrent CJK era representations.

    Args:
        date: CJK date string, e.g. '崇禎三年四月初三' or 'M45.7.30'
        country: Optional country hint to disambiguate era names (chinese, japanese, korean, vietnamese)
        dynasty: Optional dynasty hint to disambiguate era names, e.g. '唐', '元', '北宋'
        emperor: Optional emperor hint to disambiguate era names, e.g. '肅宗', '順帝'
    """
    args: dict[str, Any] = {"date": date}
    if country is not None:
        args["country"] = country
    if dynasty is not None:
        args["dynasty"] = dynasty
    if emperor is not None:
        args["emperor"] = emperor
    return _handle_tool_call("convert_cjk_date", args)


@mcp.tool()
def convert_jdn(jdn: int) -> str:
    """Convert a Julian Day Number to all calendar representations.

    Returns Gregorian, Julian, ganzhi (干支), and all concurrent CJK era dates.

    Args:
        jdn: Julian Day Number
    """
    return _handle_tool_call("convert_jdn", {"jdn": jdn})


@mcp.tool()
def convert_gregorian_date(date: str) -> str:
    """Convert a Gregorian date (YYYY-MM-DD) to Julian Day Number and all concurrent CJK era dates.

    Args:
        date: Gregorian date in YYYY-MM-DD format
    """
    return _handle_tool_call("convert_gregorian_date", {"date": date})


@mcp.tool()
def search_era(
    name: str | None = None,
    dynasty: str | None = None,
    country: str | None = None,
) -> str:
    """Search for era (年號) metadata by name, dynasty, or country.

    Returns era name, dynasty, emperor, date range, and JDN range.

    Args:
        name: Era name, e.g. '崇禎', '康熙', '寛永'
        dynasty: Dynasty name, e.g. '明', '清', '唐'
        country: Filter by country (chinese, japanese, korean, vietnamese)
    """
    args: dict[str, Any] = {}
    if name is not None:
        args["name"] = name
    if dynasty is not None:
        args["dynasty"] = dynasty
    if country is not None:
        args["country"] = country
    return _handle_tool_call("search_era", args)


def main() -> None:
    """Run the MCP server."""
    parser = argparse.ArgumentParser(description="CJK Calendar Converter MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for SSE transport (default: 8000)",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        mcp.settings.port = args.port

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
