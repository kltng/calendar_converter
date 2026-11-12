"""
The four calendar tools, shared by the stdio MCP server and the HTTP MCP server.

The descriptions here are what a language model reads before it calls a tool, so
they say plainly which argument is needed and which values are allowed. Small
models copy examples and fill every optional field they are shown; the wording
tells them to pass only `date` unless a first answer was ambiguous.
"""

import json
import sqlite3
from collections.abc import Callable
from typing import Annotated, Any

from pydantic import Field

from .converter import (
    conversion_from_resolution,
    convert_jdn,
    get_era_metadata,
    gregorian_to_jdn,
    jdn_to_gregorian,
    resolve_cjk_date,
)
from .db import COUNTRIES, find_eras_by_name, get_connection

_COUNTRY_LIST = ", ".join(COUNTRIES)

CONVERT_CJK_DATE_DOC = (
    "Convert a CJK (Chinese/Japanese/Korean/Vietnamese) historical date to the Gregorian date, "
    "Julian Day Number (JDN), ganzhi (干支) and all concurrent era dates. "
    'Usually pass only `date`, copied exactly from the user, for example {"date": "崇禎三年四月初三"}. '
    "Add country, dynasty or emperor only when a first call answers `ambiguous: true`, "
    "which means the same era name was used more than once (e.g. 上元 in Tang)."
)
CONVERT_JDN_DOC = (
    "Convert a Julian Day Number to all calendar representations: "
    "Gregorian, Julian, ganzhi (干支), and all concurrent CJK era dates."
)
CONVERT_GREGORIAN_DATE_DOC = (
    "Convert a Gregorian date (YYYY-MM-DD) to Julian Day Number and all concurrent CJK era dates."
)
SEARCH_ERA_DOC = (
    "Search for era (年號) metadata by name, dynasty, or country. "
    "Returns era name, dynasty, emperor, date range, and JDN range. "
    'Usually pass only `name`, for example {"name": "崇禎"}.'
)

DateArg = Annotated[str, Field(
    description="The historical date exactly as written, e.g. '崇禎三年四月初三', "
    "'康熙元年正月初一', '寛永七年四月初三', 'M5.7.30'.",
)]
CountryArg = Annotated[str | None, Field(
    description=f"Optional. One of: {_COUNTRY_LIST}. Leave out unless the era name is ambiguous.",
)]
DynastyArg = Annotated[str | None, Field(
    description="Optional. Dynasty name in Chinese characters, e.g. '唐', '北宋'. "
    "Leave out unless the era name is ambiguous.",
)]
EmperorArg = Annotated[str | None, Field(
    description="Optional. Emperor's temple name, e.g. '肅宗'. Leave out unless the era name is ambiguous.",
)]
JdnArg = Annotated[int, Field(description="Julian Day Number, e.g. 2316539.")]
GregorianArg = Annotated[str, Field(description="Gregorian date as YYYY-MM-DD, e.g. '1630-05-14'.")]
EraNameArg = Annotated[str | None, Field(description="Era name in Chinese characters, e.g. '崇禎', '康熙', '寛永'.")]
EraDynastyArg = Annotated[str | None, Field(description="Optional. Dynasty name, e.g. '明', '清', '唐'.")]
EraCountryArg = Annotated[str | None, Field(description=f"Optional. One of: {_COUNTRY_LIST}.")]


def _dumps(value: Any) -> str:
    # Chinese stays readable: a small model cannot read \\uXXXX escapes back.
    return json.dumps(value, ensure_ascii=False)


def _year_of(jdn: int | None) -> int | None:
    return jdn_to_gregorian(jdn)[0] if jdn else None


def cjk_date_error(conn: sqlite3.Connection, text: str, era: str | None, year: int | None) -> dict[str, Any]:
    """Explain why a date was not found, in words a caller can act on."""
    if era is None:
        return {
            "error": f"Cannot parse date: {text}",
            "hint": "Write era name, year, month and day in Chinese characters, e.g. 崇禎三年四月初三.",
        }
    candidates = find_eras_by_name(conn, era)
    if not candidates:
        return {
            "error": f"Era '{era}' not found",
            "hint": "Check the era name. Use search_era to look for it by dynasty or country.",
        }
    return {
        "error": f"Era '{era}' found but no match for year {year}",
        "hint": "The era exists, but this year, month or day is not in it. Check the date against the years below.",
        "candidates": [
            {
                "era": row["era_name"],
                "dynasty": row["dynasty_name"],
                "emperor": row["emperor_name"],
                "country": row["country"],
                "first_year": _year_of(row["start_jdn"]),
                "last_year": _year_of(row["end_jdn"]),
            }
            for row in candidates
        ],
    }


def handle_tool_call(
    name: str,
    arguments: dict[str, Any],
    connect: Callable[[], sqlite3.Connection] = get_connection,
) -> str:
    """Run one tool and return its JSON answer."""
    conn = connect()
    try:
        if name == "convert_cjk_date":
            resolution = resolve_cjk_date(
                conn,
                arguments["date"],
                country=arguments.get("country"),
                dynasty=arguments.get("dynasty"),
                emperor=arguments.get("emperor"),
            )
            if not resolution.results:
                parsed = resolution.parsed
                return _dumps(cjk_date_error(
                    conn, arguments["date"], parsed.era if parsed else None, parsed.year if parsed else None,
                ))
            return conversion_from_resolution(conn, resolution).model_dump_json()

        if name == "convert_jdn":
            return convert_jdn(conn, arguments["jdn"]).model_dump_json()

        if name == "convert_gregorian_date":
            try:
                year, month, day = (int(part) for part in str(arguments["date"]).strip().split("-"))
            except ValueError:
                return _dumps({
                    "error": f"Cannot read Gregorian date: {arguments['date']}",
                    "hint": "Use YYYY-MM-DD, e.g. 1630-05-14.",
                })
            return convert_jdn(conn, gregorian_to_jdn(year, month, day)).model_dump_json()

        if name == "search_era":
            eras = get_era_metadata(
                conn,
                era_name=arguments.get("name") or None,
                dynasty_name=arguments.get("dynasty") or None,
                country=arguments.get("country") or None,
            )
            return _dumps([era.model_dump() for era in eras])

        return _dumps({"error": f"Unknown tool: {name}"})
    finally:
        conn.close()


def register_tools(mcp: Any, connect: Callable[[], sqlite3.Connection] = get_connection) -> None:
    """Add the four tools to a FastMCP server."""

    @mcp.tool(description=CONVERT_CJK_DATE_DOC)
    def convert_cjk_date(
        date: DateArg,
        country: CountryArg = None,
        dynasty: DynastyArg = None,
        emperor: EmperorArg = None,
    ) -> str:
        args = {"date": date, "country": country, "dynasty": dynasty, "emperor": emperor}
        return handle_tool_call("convert_cjk_date", args, connect)

    @mcp.tool(description=CONVERT_JDN_DOC)
    def convert_jdn(jdn: JdnArg) -> str:
        return handle_tool_call("convert_jdn", {"jdn": jdn}, connect)

    @mcp.tool(description=CONVERT_GREGORIAN_DATE_DOC)
    def convert_gregorian_date(date: GregorianArg) -> str:
        return handle_tool_call("convert_gregorian_date", {"date": date}, connect)

    @mcp.tool(description=SEARCH_ERA_DOC)
    def search_era(
        name: EraNameArg = None,
        dynasty: EraDynastyArg = None,
        country: EraCountryArg = None,
    ) -> str:
        args = {"name": name, "dynasty": dynasty, "country": country}
        return handle_tool_call("search_era", args, connect)
