"""
MCP server using FastMCP with HTTP transports.

Mounted into the FastAPI app:
- /mcp  — Streamable HTTP (for modern MCP clients)
- /sse  — SSE transport (for LM Studio and other SSE-based clients)

Tools mirror the stdio MCP server but use the FastMCP decorator API.
"""

import json
import os

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from .converter import (
    build_ambiguous_candidates,
    convert_cjk_to_jdn,
    convert_jdn as _convert_jdn,
    get_era_metadata,
    gregorian_to_jdn,
)
from .db import get_connection
from .parser import parse_cjk_date

_allowed_hosts = ["localhost", "127.0.0.1"]
if os.environ.get("MCP_ALLOWED_HOST"):
    _allowed_hosts.append(os.environ["MCP_ALLOWED_HOST"])

mcp = FastMCP(
    "cjk-calendar-converter",
    json_response=True,
    streamable_http_path="/",
    sse_path="/",
    message_path="/messages/",
    transport_security=TransportSecuritySettings(
        allowed_hosts=_allowed_hosts,
    ),
)


def _get_conn():
    return get_connection(check_same_thread=False)


@mcp.tool()
def convert_cjk_date(
    date: str,
    country: str | None = None,
    dynasty: str | None = None,
    emperor: str | None = None,
) -> str:
    """Convert a CJK (Chinese/Japanese/Korean/Vietnamese) historical date to Julian Day Number
    and equivalent dates in all concurrent calendars.
    Input examples: '崇禎三年四月初三', '康熙元年正月初一', '寛永七年四月初三', 'M45.7.30'.
    Returns JDN, Gregorian date, Julian date (pre-1582), ganzhi (干支),
    and all concurrent CJK era representations.
    Use dynasty/emperor hints to disambiguate repeated era names (e.g. 上元 in Tang)."""
    conn = _get_conn()
    try:
        parsed = parse_cjk_date(date)
        if parsed is None:
            return json.dumps({"error": f"Cannot parse date: {date}"})

        if country:
            parsed.country_hint = country
        if dynasty:
            parsed.dynasty_hint = dynasty
        if emperor:
            parsed.emperor_hint = emperor

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
    finally:
        conn.close()


@mcp.tool()
def convert_jdn(jdn: int) -> str:
    """Convert a Julian Day Number to all calendar representations:
    Gregorian, Julian, ganzhi (干支), and all concurrent CJK era dates."""
    conn = _get_conn()
    try:
        conversion = _convert_jdn(conn, jdn)
        return conversion.model_dump_json()
    finally:
        conn.close()


@mcp.tool()
def convert_gregorian_date(date: str) -> str:
    """Convert a Gregorian date (YYYY-MM-DD) to Julian Day Number
    and all concurrent CJK era dates."""
    conn = _get_conn()
    try:
        parts = date.split("-")
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        jdn = gregorian_to_jdn(y, m, d)
        conversion = _convert_jdn(conn, jdn)
        return conversion.model_dump_json()
    finally:
        conn.close()


@mcp.tool()
def search_era(name: str | None = None, dynasty: str | None = None, country: str | None = None) -> str:
    """Search for era (年號) metadata by name, dynasty, or country.
    Returns era name, dynasty, emperor, date range, and JDN range."""
    conn = _get_conn()
    try:
        eras = get_era_metadata(
            conn,
            era_name=name,
            dynasty_name=dynasty,
            country=country,
        )
        return json.dumps([e.model_dump() for e in eras])
    finally:
        conn.close()
