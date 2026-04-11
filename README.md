# CJK Calendar Converter

A SQLite-backed historical calendar conversion system for **Chinese, Japanese, Korean, and Vietnamese** dates. Converts between traditional East Asian lunisolar calendars and the Gregorian/Julian calendar using **Julian Day Numbers (JDN)** as the universal pivot.

Designed for both human users (via REST API) and LLMs (via MCP server or API).

> **Disclaimer:** This project has not been thoroughly tested against all historical sources. Calendar conversion for East Asian historical dates is inherently complex — different sources sometimes disagree on intercalary month placement, era boundaries, and calendar reform dates. There may be errors, especially for:
> - Dates during periods of dynastic transition or competing calendars
> - Vietnamese era year counts near era boundaries (±1 year offset possible)
> - Peripheral or short-lived dynasties not fully covered in the DILA dataset
> - Proleptic date ranges (hypothetical extensions before/after an era's actual use)
>
> **Always cross-reference with authoritative sources for scholarly or critical use.**

---

## How It Works

Every calendar date — whether Gregorian, Julian, Chinese lunisolar, Japanese imperial, Korean, or Vietnamese — can be mapped to a unique **Julian Day Number** (an integer counting days from January 1, 4713 BCE). This makes JDN the perfect intermediate representation:

```
崇禎三年四月初三  →  JDN 2316539  →  1630-05-14 (Gregorian)
                                   →  寛永七年四月三日 (Japanese)
                                   →  天聰四年四月三日 (Later Jin/清前身)
                                   →  朝鮮七年四月三日 (Korean)
                                   →  後黎朝德隆元年四月三日 (Vietnamese)
```

The database stores ~131,000 lunar month records with JDN ranges, covering:

| Country | Coverage | Source |
|---------|----------|--------|
| China | ~220 BCE – 1912 CE | DILA Authority Database |
| Japan | 593 – 1872 CE | DILA Authority Database |
| Korea | 56 BCE – 1885 CE | DILA Authority Database |
| Vietnam | ~544 – 1945 CE | Derived from Chinese lunar months + Vietnamese era data |

---

## Quick Start

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Python 3.12+ (uv will install it automatically)

### Setup

```bash
git clone https://github.com/kltng/calendar_converter.git
cd calendar_converter

# Install dependencies
uv sync --extra dev

# Download the DILA source data
mkdir -p data/raw
curl -L -o data/raw/authority_time.zip \
  "https://authority.dila.edu.tw/downloads/authority_time.2012-02.zip"
cd data/raw && unzip authority_time.zip && cd ../..

# Build the SQLite database
uv run python -m data.scripts.build_db
uv run python -m data.scripts.add_vietnamese

# Run tests to verify
uv run pytest
```

### Run the API Server

```bash
uv run uvicorn src.calendar_converter.api:app --reload --port 8000
```

Open http://localhost:8000/docs for the interactive Swagger UI.

### Docker

```bash
docker build -t calendar-converter .
docker compose up
```

The SQLite database is embedded in the container image — no external database needed.

---

## Usage

### 1. REST API

#### Convert a CJK date

```bash
curl "http://localhost:8000/convert?date=崇禎三年四月初三"
```

Response:
```json
{
  "jdn": 2316539,
  "gregorian": "1630-05-14",
  "julian": null,
  "ganzhi": {
    "year": "庚午",
    "month": "辛巳",
    "day": "壬子"
  },
  "cjk_dates": [
    {
      "era_name": "崇禎",
      "dynasty_name": "明",
      "country": "chinese",
      "year_in_era": 3,
      "month": 4,
      "month_name": "四",
      "is_leap_month": false,
      "day": 3
    },
    {
      "era_name": "天聰",
      "dynasty_name": "後金",
      "country": "chinese",
      "year_in_era": 4,
      "month": 4,
      "day": 3
    },
    {
      "era_name": "寛永",
      "dynasty_name": "江戸時代",
      "country": "japanese",
      "year_in_era": 7,
      "month": 4,
      "day": 3
    }
  ]
}
```

#### Convert by Julian Day Number

```bash
curl "http://localhost:8000/convert?jdn=2316539"
```

#### Convert by Gregorian date

```bash
curl "http://localhost:8000/convert?gregorian=1630-05-14"
```

#### Disambiguate with country hint

When an era name is shared across countries, use the `country` parameter:

```bash
curl "http://localhost:8000/convert?date=天保三年閏九月十五日&country=japanese"
```

#### Disambiguate era names

Many era names were reused across dynasties. When the converter finds multiple matching eras, the response includes `ambiguous: true` and an `other_candidates` list showing all alternative interpretations:

```bash
curl "http://localhost:8000/convert?date=乾德二年正月初一"
```

```json
{
  "jdn": 2057111,
  "gregorian": "0920-01-29",
  "ambiguous": true,
  "other_candidates": [
    {
      "jdn": 2073191,
      "gregorian": "0964-02-21",
      "era_name": "乾德",
      "dynasty_name": "吳越",
      "emperor_name": "忠懿王",
      "country": "chinese",
      "year_in_era": 2,
      "month": 1,
      "day": 1
    },
    {
      "jdn": 2073191,
      "gregorian": "0964-02-21",
      "era_name": "乾德",
      "dynasty_name": "北宋",
      "emperor_name": "太祖",
      "country": "chinese",
      "year_in_era": 2,
      "month": 1,
      "day": 1
    }
  ],
  "cjk_dates": [ ... ]
}
```

Use `dynasty` or `emperor` hints to narrow to a specific era:

```bash
# Narrow to Northern Song dynasty
curl "http://localhost:8000/convert?date=乾德二年正月初一&dynasty=北宋"

# Narrow by emperor name
curl "http://localhost:8000/convert?date=上元二年正月初一&emperor=肅宗"

# Combine hints
curl "http://localhost:8000/convert?date=至元三年正月初一&dynasty=元&emperor=順帝"
```

When hints resolve the ambiguity, `ambiguous` will be `false` and `other_candidates` will be empty.

#### Search eras

```bash
# By era name
curl "http://localhost:8000/eras?name=崇禎"

# By dynasty
curl "http://localhost:8000/eras?dynasty=明"

# By country
curl "http://localhost:8000/eras?country=vietnamese"
```

#### Batch convert

```bash
curl -X POST http://localhost:8000/convert/batch \
  -H "Content-Type: application/json" \
  -d '["崇禎三年四月初三", "康熙元年正月初一", "嘉隆元年正月初一"]'
```

#### Download the database

```bash
curl -o calendar.db http://localhost:8000/db/download
```

### 2. Use the SQLite Database Directly

Download `calendar.db` and query it with any SQLite client:

```sql
-- Find all eras named 崇禎
SELECT * FROM era_summary WHERE era_name = '崇禎';

-- Find the lunar month containing a specific JDN
SELECT m.*, es.era_name, es.dynasty_name, es.country
FROM month m
JOIN era_summary es ON es.era_id = m.era_id
WHERE m.first_jdn <= 2316539 AND m.last_jdn >= 2316539;

-- List all Vietnamese eras
SELECT era_name, dynasty_name, start_jdn, end_jdn
FROM era_summary WHERE country = 'vietnamese'
ORDER BY start_jdn;

-- Find concurrent eras for a given year (JDN range)
SELECT es.era_name, es.dynasty_name, es.country
FROM era_summary es
WHERE es.start_jdn <= 2316539 AND es.end_jdn >= 2316539;
```

### 3. MCP Server (LLM Integration)

The MCP server lets LLMs call calendar conversion as a tool via the [Model Context Protocol](https://modelcontextprotocol.io/). Three transports are supported:

#### Option A: Streamable HTTP (Remote)

The deployed API includes an MCP endpoint at `/mcp/`. Use this with any MCP client that supports Streamable HTTP transport — no local installation needed.

```json
{
  "mcpServers": {
    "calendar": {
      "type": "streamable-http",
      "url": "https://calendar-converter.098484.xyz/mcp/"
    }
  }
}
```

#### Option B: SSE (Remote)

For MCP clients that use SSE transport (e.g., LM Studio), connect to the `/sse/` endpoint:

```json
{
  "mcpServers": {
    "calendar": {
      "type": "sse",
      "url": "https://calendar-converter.098484.xyz/sse/"
    }
  }
}
```

#### Option C: stdio (Local)

For local use, run the stdio-based MCP server directly:

```json
{
  "mcpServers": {
    "calendar": {
      "command": "uv",
      "args": ["run", "python", "-m", "src.calendar_converter.mcp_server"],
      "cwd": "/absolute/path/to/calendar_converter"
    }
  }
}
```

The stdio server also supports SSE transport for local use with clients like LM Studio:

```bash
uv run python -m src.calendar_converter.mcp_server --transport sse --port 8001
```

#### Available MCP Tools

| Tool | Description | Required Parameters |
|------|-------------|-------------------|
| `convert_cjk_date` | Convert a CJK date string to JDN + all equivalents | `date` (string) |
| `convert_jdn` | Convert a Julian Day Number to all calendars | `jdn` (integer) |
| `convert_gregorian_date` | Convert YYYY-MM-DD to all calendars | `date` (string) |
| `search_era` | Search era metadata | `name`, `dynasty`, or `country` |

All conversion tools accept optional disambiguation parameters: `country` (`"chinese"`, `"japanese"`, `"korean"`, `"vietnamese"`), `dynasty` (e.g., `"唐"`, `"北宋"`), and `emperor` (e.g., `"肅宗"`). When an era name matches multiple eras, the response includes `ambiguous: true` with `other_candidates` listing all alternatives — the LLM can then re-query with hints.

---

## Supported Input Formats

### CJK Date Strings

| Format | Example | Parsed As |
|--------|---------|-----------|
| Standard Chinese | `崇禎三年四月初三` | 崇禎 era, year 3, month 4, day 3 |
| With 日 suffix | `康熙六十一年十二月二十九日` | 康熙 era, year 61, month 12, day 29 |
| Leap month (閏) | `天保三年閏九月十五日` | 天保 era, year 3, leap month 9, day 15 |
| Yuan year (元年) | `崇禎元年正月初一` | 崇禎 era, year 1, month 1, day 1 |
| Zheng month (正月) | `嘉隆元年正月初一` | 嘉隆 era, year 1, month 1, day 1 |
| 廿/卅 shorthands | `康熙三年臘月廿九` | 康熙 era, year 3, month 12, day 29 |
| Year only | `崇禎三年` | First month of that year |
| Year+month only | `崇禎三年四月` | First day of that month |
| Ganzhi year | `嘉慶甲子年` | 嘉慶 era, year with ganzhi 甲子 |
| Full ganzhi | `崇禎庚午年辛巳月壬子日` | Resolved via sexagenary cycle lookup |
| Mixed ganzhi+numeric | `崇禎庚午年四月初三` | Ganzhi year + numeric month/day |

### Japanese Shorthand

| Format | Example | Parsed As |
|--------|---------|-----------|
| Meiji | `M45.7.30` | 明治45年7月30日 |
| Taisho | `T15.12.25` | 大正15年12月25日 |
| Showa | `S64.1.7` | 昭和64年1月7日 |
| Heisei | `H26.6.8` | 平成26年6月8日 |
| Reiwa | `R1.5.1` | 令和1年5月1日 |

---

## Database Schema

```
dynasty (id, type)                              -- 'chinese'|'japanese'|'korean'|'vietnamese'
  dynasty_name (dynasty_id, name, ranking, language_id)
    └─ emperor (id, dynasty_id)
         emperor_name (emperor_id, name, ranking, language_id)
           └─ era (id, emperor_id)
                era_name (era_id, name, ranking, language_id)
                  └─ month (id, era_id, year, month, month_name, leap_month,
                            first_jdn, last_jdn, ganzhi, start_from, status, eclipse)

era_summary (VIEW)   -- denormalized join for queries: era + emperor + dynasty + JDN range
period               -- historical period spans
day_comment           -- annotations for specific JDNs (historical events, eclipses)
```

The `month` table is the core: each row represents one lunar month with its JDN range. Individual days are derived from `first_jdn + (day - start_from)`.

---

## Key Concepts

**Julian Day Number (JDN):** A continuous integer day count starting from noon GMT, January 1, 4713 BCE (Julian calendar). Every calendar date maps to exactly one JDN. This avoids needing pairwise conversion formulas between calendar systems.

**Lunisolar Calendar:** East Asian calendars track both lunar months (29–30 days) and solar years. When a lunar month contains no "major solar term" (中氣), it becomes an intercalary/leap month (閏月). This is determined astronomically, not by formula — historical data must be looked up.

**Era Names (年號):** Reign-period names that reset year counting. One emperor could use multiple era names. The same name can appear in different dynasties and countries (e.g., 太平 was used 10+ times). Always use dynasty or country for disambiguation.

**Sexagenary Cycle (干支):** A 60-unit cycle from 10 Heavenly Stems (天干) × 12 Earthly Branches (地支). Applied to years, months, days, and hours. Year ganzhi is stored in the database; month ganzhi is computed via the 五虎遁 formula; day ganzhi is computed from JDN.

**Proleptic Dates:** Dates marked `status='P'` extend a calendar system beyond its actual historical use (e.g., using an era name for dates after that era ended, because historical sources reference them that way).

---

## Agent Skill (Claude Code / LLM Tool Use)

The `skill/` directory contains a **standalone agent skill** — a self-contained, zero-dependency Python script with its own SQLite database that any LLM agent (Claude Code, etc.) can use for calendar conversion without needing the full API server.

### What's Included

```
skill/
├── SKILL.md                        # Skill manifest and documentation
├── scripts/
│   ├── calendar_converter.py       # Standalone converter (Python 3.10+, stdlib only)
│   └── .gitignore                  # Ignores downloaded calendar.db
└── references/
    └── database_schema.md          # SQLite schema and query patterns
```

### Setup

```bash
# Download the SQLite database (~14 MB) on first use
python3 skill/scripts/calendar_converter.py setup
```

### CLI Usage

```bash
# CJK date → Gregorian
python3 skill/scripts/calendar_converter.py convert "崇禎三年四月初三"

# Gregorian → all CJK calendars
python3 skill/scripts/calendar_converter.py gregorian 1644 3 19

# Julian Day Number → all calendars
python3 skill/scripts/calendar_converter.py jdn 2299161

# Search eras
python3 skill/scripts/calendar_converter.py eras --name 康熙
python3 skill/scripts/calendar_converter.py eras --dynasty 明 --country chinese
```

### Adding to a Skill Hub

Copy the `skill/` directory (or symlink it) into your skill hub:

```bash
cp -r skill/ /path/to/your-skill-hub/cjk-calendar
```

The skill is fully self-contained: zero external dependencies, downloads its own database, and runs with Python 3.10+ stdlib only.

---

## Development

```bash
# Run all tests (1416 tests)
uv run pytest

# Run a single test file
uv run pytest tests/test_parser.py

# Run a specific test
uv run pytest tests/test_converter.py::TestGanzhi::test_full_ganzhi_in_conversion -v

# Run CBDB verification tests only
uv run pytest tests/test_cbdb_verification.py -v

# Rebuild the database from scratch
uv run python -m data.scripts.build_db
uv run python -m data.scripts.add_vietnamese
```

### Test Suites

| File | Tests | Description |
|------|-------|-------------|
| `test_parser.py` | 23 | CJK date string parsing |
| `test_converter.py` | 39 | JDN conversion, ganzhi, disambiguation |
| `test_api.py` | 19 | FastAPI endpoint integration |
| `test_mcp.py` | 10 | MCP stdio server tools |
| `test_dila_verification.py` | 5 | DILA reference date verification |
| `test_cbdb_verification.py` | 1310 | Era name cross-validation against external dataset |

---

## Data Sources and Acknowledgements

This project builds on the work of several institutions and individuals:

### DILA Authority Database (Primary Source)

The core calendar data (Chinese, Japanese, Korean) comes from the **Dharma Drum Institute of Liberal Arts (DILA)** Time Authority Database, assembled between 2008–2010 by the Library and Information Center of Dharma Drum Buddhist College (法鼓佛教學院).

- **Website:** https://authority.dila.edu.tw/
- **Download:** https://authority.dila.edu.tw/docs/open_content/download.php
- **GitHub:** https://github.com/DILA-edu/Authority-Databases
- **Author:** Simon Wiles, DDBC
- **License:** [Creative Commons Attribution-ShareAlike 3.0 Unported](http://creativecommons.org/licenses/by-sa/3.0/)
- **Japanese data** builds upon data provided by Takashi SUGA

The DILA database uses Julian Day Numbers as the fundamental unit for date designation, with lunar months as the smallest stored entity. This elegant design inspired the architecture of this project.

### CeJS (Colorless echo JavaScript)

The **CeJS** library by kanasimi provided reference data for Vietnamese calendar eras and validation of conversion results.

- **Repository:** https://github.com/kanasimi/CeJS
- **Era Converter Demo:** https://kanasimi.github.io/CeJS/_test%20suite/era.htm
- **Coverage:** 246 BCE – 2100 CE across multiple calendar systems

### CBDB (China Biographical Database)

The **CBDB** project at Harvard University provided nianhao (era name) verification data used for cross-validation testing.

- **Website:** https://projects.iq.harvard.edu/cbdb
- **NIAN_HAO table:** https://input.cbdb.fas.harvard.edu/codes/NIAN_HAO
- **Related NPM package (cn-era):** https://www.npmjs.com/package/cn-era

### Julian Day Number Algorithms

JDN ↔ Gregorian/Julian conversion algorithms are based on:

- Jean Meeus, *Astronomical Algorithms* (Willmann-Bell, 1991)
- E.G. Richards, "Calendars" in *Explanatory Supplement to the Astronomical Almanac* (2013)
- [Julian Day — Wikipedia](https://en.wikipedia.org/wiki/Julian_day)

### Vietnamese Historical Data

Vietnamese dynasty and era information is derived from:

- *Đại Việt sử ký toàn thư* (大越史記全書) — Complete Annals of Đại Việt
- [Vietnamese era name chronology — Wikipedia](https://vi.wikipedia.org/wiki/Ni%C3%AAn_bi%E1%BB%83u_l%E1%BB%8Bch_s%E1%BB%AD_Vi%E1%BB%87t_Nam)
- CeJS Vietnamese era data (see above)

### Sexagenary Cycle (干支) Computation

Month ganzhi uses the traditional 五虎遁 (Five Tigers) formula. Day ganzhi is computed from JDN using a mod-60 cycle calibrated against known historical dates.

---

## License

The DILA Authority Database data is licensed under [CC BY-SA 3.0](http://creativecommons.org/licenses/by-sa/3.0/). The code in this repository is available under the MIT License. If you use the calendar data, please attribute the DILA Authority Database as required by their license.
