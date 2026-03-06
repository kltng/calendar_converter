"""
MCP (Model Context Protocol) server for CJK calendar conversion.

Exposes calendar conversion as tools that LLMs can call directly.
Run with: uv run python -m src.calendar_converter.mcp_server
"""

import json
import sys
from typing import Any

from .converter import (
    convert_cjk_to_jdn,
    convert_jdn,
    get_era_metadata,
    gregorian_to_jdn,
    jdn_to_gregorian,
    format_date,
)
from .db import get_connection
from .parser import parse_cjk_date


TOOLS = [
    {
        "name": "convert_cjk_date",
        "description": (
            "Convert a CJK (Chinese/Japanese/Korean) historical date to Julian Day Number "
            "and equivalent dates in all concurrent calendars. "
            "Input examples: '崇禎三年四月初三', '康熙元年正月初一', '寛永七年四月初三', 'M45.7.30'. "
            "Returns JDN, Gregorian date, Julian date (pre-1582), ganzhi (干支), "
            "and all concurrent CJK era representations."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "CJK date string, e.g. '崇禎三年四月初三' or 'M45.7.30'",
                },
                "country": {
                    "type": "string",
                    "enum": ["chinese", "japanese", "korean"],
                    "description": "Optional country hint to disambiguate era names",
                },
            },
            "required": ["date"],
        },
    },
    {
        "name": "convert_jdn",
        "description": (
            "Convert a Julian Day Number to all calendar representations: "
            "Gregorian, Julian, ganzhi (干支), and all concurrent CJK era dates."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "jdn": {
                    "type": "integer",
                    "description": "Julian Day Number",
                },
            },
            "required": ["jdn"],
        },
    },
    {
        "name": "convert_gregorian_date",
        "description": (
            "Convert a Gregorian date (YYYY-MM-DD) to Julian Day Number "
            "and all concurrent CJK era dates."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Gregorian date in YYYY-MM-DD format",
                },
            },
            "required": ["date"],
        },
    },
    {
        "name": "search_era",
        "description": (
            "Search for era (年號) metadata by name, dynasty, or country. "
            "Returns era name, dynasty, emperor, date range, and JDN range."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Era name, e.g. '崇禎', '康熙', '寛永'",
                },
                "dynasty": {
                    "type": "string",
                    "description": "Dynasty name, e.g. '明', '清', '唐'",
                },
                "country": {
                    "type": "string",
                    "enum": ["chinese", "japanese", "korean"],
                    "description": "Filter by country",
                },
            },
        },
    },
]


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

            results = convert_cjk_to_jdn(conn, parsed)
            if not results:
                # Try to provide helpful disambiguation
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
            conversion = convert_jdn(conn, jdn_val)
            return conversion.model_dump_json()

        elif name == "convert_jdn":
            conversion = convert_jdn(conn, arguments["jdn"])
            return conversion.model_dump_json()

        elif name == "convert_gregorian_date":
            parts = arguments["date"].split("-")
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            jdn = gregorian_to_jdn(y, m, d)
            conversion = convert_jdn(conn, jdn)
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


def _read_message() -> dict[str, Any] | None:
    """Read a JSON-RPC message from stdin."""
    header = ""
    while True:
        line = sys.stdin.readline()
        if not line:
            return None
        header += line
        if line == "\r\n" or line == "\n":
            break

    content_length = 0
    for h in header.strip().split("\n"):
        if h.lower().startswith("content-length:"):
            content_length = int(h.split(":")[1].strip())

    if content_length == 0:
        return None

    body = sys.stdin.read(content_length)
    return json.loads(body)


def _write_message(msg: dict[str, Any]) -> None:
    """Write a JSON-RPC message to stdout."""
    body = json.dumps(msg)
    header = f"Content-Length: {len(body.encode())}\r\n\r\n"
    sys.stdout.write(header + body)
    sys.stdout.flush()


def main() -> None:
    """Run the MCP server using stdio transport."""
    while True:
        msg = _read_message()
        if msg is None:
            break

        method = msg.get("method", "")
        msg_id = msg.get("id")

        if method == "initialize":
            _write_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "cjk-calendar-converter",
                        "version": "0.1.0",
                    },
                },
            })

        elif method == "notifications/initialized":
            pass  # No response needed for notifications

        elif method == "tools/list":
            _write_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOLS},
            })

        elif method == "tools/call":
            params = msg.get("params", {})
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})

            try:
                result_text = _handle_tool_call(tool_name, arguments)
                _write_message({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": result_text}],
                    },
                })
            except Exception as e:
                _write_message({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps({"error": str(e)})}],
                        "isError": True,
                    },
                })

        elif method == "ping":
            _write_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {},
            })

        elif msg_id is not None:
            _write_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            })


if __name__ == "__main__":
    main()
