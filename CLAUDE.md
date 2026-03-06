# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**CJK Calendar Converter** — a SQLite-backed calendar conversion system for Chinese, Japanese, Korean, and Vietnamese historical dates. Designed for both human users and LLM tool-use (as an MCP skill or API endpoint).

**Core idea:** A user or LLM inputs a CJK date like `崇禎三年四月初三` and gets back:
- The Julian Day Number (JDN)
- Equivalent dates in other CJK calendars active at that time
- Gregorian/Julian calendar equivalent
- Sexagenary cycle (干支) designation

## Architecture

### Data Layer: SQLite Database

The database uses **Julian Day Number (JDN)** as the universal pivot for all conversions, following the DILA (Dharma Drum Institute of Liberal Arts) approach. JDN is an integer day count from January 1, 4713 BCE (Julian) — every calendar date maps to exactly one JDN, enabling O(1) cross-calendar lookups.

**Schema (normalized from DILA's MySQL dump into SQLite):**

```
dynasty (id, type)                          -- type: 'chinese'|'japanese'|'korean'|'vietnamese'
  dynasty_name (dynasty_id, name, ranking, language_id)
    └─ emperor (id, dynasty_id)
         emperor_name (emperor_id, name, ranking, language_id)
           └─ era (id, emperor_id)
                era_name (era_id, name, ranking, language_id)
                  └─ month (id, era_id, year, month, month_name, leap_month,
                            first_jdn, last_jdn, ganzhi, start_from, status, eclipse)

era_summary (VIEW) -- joins era→emperor→dynasty with MIN/MAX JDN, used by all queries
period (id, dynasty_id, first_jdn, last_jdn, description)
day_comment (id, jdn, comment)
```

- `month` is the core table (~131K rows): each row = one lunar month with JDN range
- Names are in separate tables supporting multiple languages (Chinese, English, Korean hangul, etc.)
- JDN ↔ Gregorian/Julian conversion is computed, not looked up (algorithms in converter.py)
- `dynasty.type` disambiguates same era names across China/Japan/Korea/Vietnam
- `status='P'` marks proleptic (hypothetical) date ranges; `start_from` handles split months

**Data sources:**
- DILA Authority Database (CC BY-SA 2.5 TW): `authority_time.sql` dumps from https://authority.dila.edu.tw/docs/open_content/download.php and https://github.com/DILA-edu/Authority-Databases
- CeJS era data for gap-filling and validation: https://github.com/kanasimi/CeJS
- Coverage: China ~220 BCE–1912, Japan 593–1872, Korea 56 BCE–1885, Vietnam ~968–1945

### Parser: CJK Date String → Structured Query

Parses natural CJK date inputs into structured form for DB lookup:

```
Input:  "崇禎三年四月初三"
Parsed: { era: "崇禎", year: 3, month: 4, day: 3, is_leap: false }

Input:  "天保三年閏九月十五日"
Parsed: { era: "天保", year: 3, month: 9, day: 15, is_leap: true }
```

Key parsing challenges:
- Chinese numerals (初三=3, 十五=15, 二十九=29) including 廿 and 卅 shorthands
- Intercalary month markers (閏)
- Japanese shorthand eras (M/T/S/H/R + year)
- Ambiguous era names (太平 used 10+ times) — resolved by optional dynasty/country hint

### API Layer: FastAPI (Python)

```
GET  /convert?date=崇禎三年四月初三           → JDN + all equivalents
GET  /convert?jdn=2317814                      → all calendar representations
GET  /convert?gregorian=1630-05-14             → JDN + all CJK equivalents
GET  /eras?name=崇禎                           → era metadata + date range
GET  /eras?dynasty=明                          → all eras in dynasty
POST /convert/batch                            → array of dates
GET  /db/download                              → download calendar.db SQLite file
GET  /health                                   → service status
```

Response includes: JDN, Gregorian date, Julian date (pre-1582), full ganzhi (year/month/day), and all concurrent CJK+Vietnamese era representations.

### MCP Server (LLM Tool Use)

`src/calendar_converter/mcp_server.py` — stdio-based MCP server exposing 4 tools:
- `convert_cjk_date` — parse and convert a CJK date string
- `convert_jdn` — convert Julian Day Number to all calendars
- `convert_gregorian_date` — convert YYYY-MM-DD to all calendars
- `search_era` — search era metadata by name/dynasty/country

Add to Claude Code config:
```json
{
  "mcpServers": {
    "calendar": {
      "command": "uv",
      "args": ["run", "python", "-m", "src.calendar_converter.mcp_server"],
      "cwd": "/path/to/calendar_converter"
    }
  }
}
```

### Containerization

```
Dockerfile          → Python 3.12-slim, FastAPI + uvicorn, embeds SQLite DB
docker-compose.yml  → single service, port 8000, healthcheck
```

The SQLite DB file ships inside the container image — no external DB dependency.

## Directory Structure

```
calendar_converter/
├── CLAUDE.md
├── pyproject.toml              # Python project config (hatch/uv)
├── Dockerfile
├── docker-compose.yml
├── data/
│   ├── raw/                    # Original DILA SQL dumps and CeJS data
│   ├── scripts/                # ETL scripts to build SQLite from raw data
│   └── calendar.db             # Built SQLite database (gitignored, built via script)
├── src/
│   └── calendar_converter/
│       ├── __init__.py
│       ├── db.py               # SQLite connection and query layer
│       ├── parser.py           # CJK date string parser
│       ├── converter.py        # Core conversion logic (JDN pivot)
│       ├── models.py           # Pydantic response models
│       ├── api.py              # FastAPI routes
│       └── mcp_server.py       # MCP server for LLM tool-use (stdio transport)
└── tests/
    ├── test_parser.py
    ├── test_converter.py
    ├── test_api.py
    └── test_mcp.py
```

## Development Commands

```bash
# Setup (using uv)
uv sync

# Install dev dependencies
uv sync --extra dev

# Download DILA data (if data/raw/ is empty)
curl -L -o data/raw/authority_time.zip "https://authority.dila.edu.tw/downloads/authority_time.2012-02.zip"
cd data/raw && unzip authority_time.zip && cd ../..

# Build the SQLite database from raw data (two steps)
uv run python -m data.scripts.build_db
uv run python -m data.scripts.add_vietnamese

# Run the API server locally
uv run uvicorn src.calendar_converter.api:app --reload --port 8000

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_parser.py

# Run a specific test
uv run pytest tests/test_parser.py::TestParseCJKDate::test_chongzhen -v

# Type checking
uv run mypy src/

# Docker build and run
docker build -t calendar-converter .
docker compose up
```

## Key Domain Concepts

**Julian Day Number (JDN):** Integer day count from noon GMT, Jan 1 4713 BCE. The universal pivot — convert any calendar date to JDN, then from JDN to any other calendar. Avoids needing N*(N-1)/2 pairwise conversion functions.

**Lunisolar calendar:** CJK calendars combine lunar months (29-30 days tracking moon phases) with solar year alignment via intercalary months. A month lacking a "major solar term" (中氣/zhongqi) becomes the leap month (閏月). This is astronomically determined, not formulaic — historical data must be looked up, not computed.

**Era names (年號):** Reign-period names that reset year counting. One emperor could have multiple eras. Same name reused across dynasties/countries (e.g., 太平 appears 10+ times). Always disambiguate with dynasty + country.

**Sexagenary cycle (干支):** 60-unit cycle from 10 Heavenly Stems × 12 Earthly Branches. Applied to years, months, days, and hours. Repeats every 60 units. Stored per lunar_month and derivable for any JDN.

**Proleptic calendar:** Extending a calendar system backwards before its actual adoption (e.g., Gregorian dates before 1582). DILA marks these with status='P'. We preserve this distinction.

## Important Constraints

- The Chinese calendar is **not algorithmically computable** for historical dates — it depends on which astronomical bureau was in power and what methods they used. Always use lookup tables from authoritative sources.
- Intercalary month placement varies by dynasty/method. Never assume a formula; always query the DB.
- When era names are ambiguous, the API must return all matches with disambiguation metadata (dynasty, country, date range) rather than guessing.
- All Gregorian dates before Oct 15, 1582 are proleptic. Julian calendar dates should be provided alongside for pre-1582 dates.
- The DILA data is CC BY-SA 2.5 TW licensed — attribution required.
- SQLite DB must be reproducibly buildable from raw data via `data/scripts/build_db` + `data/scripts/add_vietnamese`.
- Vietnamese calendar data is derived by mapping Vietnamese eras onto Chinese lunar month data (same lunisolar calendar). Vietnamese era year counts may have ±1 year offset near era boundaries due to lunar/Gregorian alignment.
