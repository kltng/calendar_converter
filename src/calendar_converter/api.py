"""FastAPI routes for calendar conversion."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator
import sqlite3

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from .converter import (
    convert_cjk_to_jdn,
    convert_jdn,
    get_era_metadata,
    gregorian_to_jdn,
)
from .db import get_connection, DB_PATH
from .models import DateConversion, EraMetadata, ErrorResponse
from .parser import parse_cjk_date

_conn: sqlite3.Connection | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _conn
    _conn = get_connection()
    yield
    if _conn:
        _conn.close()


app = FastAPI(
    title="CJK Calendar Converter",
    description=(
        "Convert dates between Chinese, Japanese, Korean historical calendars "
        "using Julian Day Numbers as universal pivot. "
        "Input CJK dates like 崇禎三年四月初三 and get equivalent dates across all calendars."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


def conn() -> sqlite3.Connection:
    assert _conn is not None, "Database not initialized"
    return _conn


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/convert",
    response_model=DateConversion | ErrorResponse,
    summary="Convert a date between calendars",
)
async def convert(
    date: str | None = Query(None, description="CJK date string, e.g. 崇禎三年四月初三"),
    jdn: int | None = Query(None, description="Julian Day Number"),
    gregorian: str | None = Query(None, description="Gregorian date (YYYY-MM-DD)"),
    country: str | None = Query(None, description="Country hint: chinese, japanese, korean"),
) -> DateConversion | ErrorResponse:
    """Convert a date. Provide exactly one of: date, jdn, or gregorian."""
    db = conn()

    if jdn is not None:
        return convert_jdn(db, jdn)

    if gregorian is not None:
        parts = gregorian.split("-")
        if len(parts) != 3:
            raise HTTPException(400, "gregorian must be YYYY-MM-DD format")
        try:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            raise HTTPException(400, "Invalid gregorian date")
        target_jdn = gregorian_to_jdn(y, m, d)
        return convert_jdn(db, target_jdn)

    if date is not None:
        parsed = parse_cjk_date(date)
        if parsed is None:
            raise HTTPException(400, f"Cannot parse date: {date}")

        if country:
            parsed.country_hint = country

        results = convert_cjk_to_jdn(db, parsed)
        if not results:
            # Return ambiguity info
            from .db import find_eras_by_name
            candidates_rows = find_eras_by_name(db, parsed.era)
            candidates = [
                EraMetadata(
                    era_id=r["era_id"],
                    era_name=r["era_name"],
                    emperor_name=r["emperor_name"],
                    dynasty_name=r["dynasty_name"],
                    country=r["country"],
                    start_jdn=r["start_jdn"],
                    end_jdn=r["end_jdn"],
                )
                for r in candidates_rows
            ]
            if candidates:
                return ErrorResponse(
                    error=f"Era '{parsed.era}' found but no matching date for year {parsed.year}. "
                          f"Found {len(candidates)} era(s) with this name.",
                    candidates=candidates,
                )
            return ErrorResponse(error=f"Era '{parsed.era}' not found in database")

        if len(results) == 1:
            jdn_val, _ = results[0]
            return convert_jdn(db, jdn_val)

        # Multiple matches — return first and include all as CJK dates
        jdn_val, _ = results[0]
        conversion = convert_jdn(db, jdn_val)
        return conversion

    raise HTTPException(400, "Provide one of: date, jdn, or gregorian")


@app.get(
    "/db/download",
    summary="Download the SQLite database file",
    response_class=FileResponse,
)
async def download_db() -> FileResponse:
    """Download the calendar.db SQLite file for local use."""
    if not DB_PATH.exists():
        raise HTTPException(404, "Database file not found")
    return FileResponse(
        path=str(DB_PATH),
        filename="calendar.db",
        media_type="application/x-sqlite3",
    )


@app.get(
    "/eras",
    response_model=list[EraMetadata],
    summary="Search era metadata",
)
async def eras(
    name: str | None = Query(None, description="Era name, e.g. 崇禎"),
    dynasty: str | None = Query(None, description="Dynasty name, e.g. 明"),
    country: str | None = Query(None, description="Country: chinese, japanese, korean"),
) -> list[EraMetadata]:
    """Search for eras by name, dynasty, or country."""
    db = conn()
    return get_era_metadata(db, era_name=name, dynasty_name=dynasty, country=country)


@app.post(
    "/convert/batch",
    response_model=list[DateConversion | ErrorResponse],
    summary="Convert multiple dates",
)
async def convert_batch(
    dates: list[str],
) -> list[DateConversion | ErrorResponse]:
    """Convert a batch of CJK date strings."""
    db = conn()
    results: list[DateConversion | ErrorResponse] = []

    for date_str in dates:
        parsed = parse_cjk_date(date_str)
        if parsed is None:
            results.append(ErrorResponse(error=f"Cannot parse: {date_str}"))
            continue

        conversions = convert_cjk_to_jdn(db, parsed)
        if not conversions:
            results.append(ErrorResponse(error=f"No match for: {date_str}"))
            continue

        jdn_val, _ = conversions[0]
        results.append(convert_jdn(db, jdn_val))

    return results
