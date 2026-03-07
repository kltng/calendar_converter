"""
Fetch 200 verified date records from DILA's date query service.

Spreads JDN samples across the full coverage range (~220 BCE to 1912 CE)
with polite pacing (2-3 second delays) to avoid overloading the service.

Usage:
    uv run python -m data.scripts.fetch_dila_test_data
"""

import json
import random
import subprocess
import time
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / "dila_test_data.json"

# DILA date query API
API_URL = "https://authority.dila.edu.tw/webwidget/getAuthorityData.php"

# Coverage range in JDN
# ~220 BCE (start of Chinese coverage) to ~1912 CE (end of Chinese imperial era)
JDN_START = 1683000   # ~220 BCE
JDN_END = 2419000     # ~1912 CE

NUM_SAMPLES = 200
DELAY_MIN = 2.0  # seconds between requests
DELAY_MAX = 3.0


def fetch_date(jdn: int) -> dict | None:
    """Query DILA for a single JDN, return parsed JSON or None on error."""
    url = f"{API_URL}?type=time&when={jdn}&format=j&jsoncallback=cb"
    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", "15", url],
            capture_output=True, text=True, timeout=20,
        )
        raw = result.stdout.strip()
        if not raw:
            print(f"  Empty response for JDN {jdn}")
            return None
        # Strip JSONP wrapper: cb({...})
        if raw.startswith("cb(") and raw.endswith(")"):
            raw = raw[3:-1]
        data = json.loads(raw)
        return data.get("W")
    except Exception as e:
        print(f"  Error fetching JDN {jdn}: {e}")
        return None


def generate_jdn_samples(n: int) -> list[int]:
    """Generate n JDN values spread across the coverage range with some randomness."""
    random.seed(42)  # reproducible
    step = (JDN_END - JDN_START) / n
    samples = []
    for i in range(n):
        base = int(JDN_START + i * step)
        jitter = random.randint(-500, 500)
        samples.append(base + jitter)
    return samples


def normalize_record(jdn: int, entry: dict) -> dict:
    """Extract a flat record from a DILA data entry."""
    return {
        "jdn": int(entry.get("JD", jdn)),
        "ce_date": entry.get("ceDate", ""),
        "dynasty": entry.get("dynasty", ""),
        "emperor": entry.get("emperor", ""),
        "era": entry.get("era", ""),
        "year_number": int(entry.get("yearNumber", 0)),
        "year_ganzhi": entry.get("yearGanzhi", ""),
        "lunar_month": entry.get("lunar_month", ""),
        "leap_month": entry.get("leap_month", "0"),
        "day_number": int(entry.get("dayNumber", 0)),
        "day_ganzhi": entry.get("dayGanzhi", ""),
        "year_number_ch": entry.get("yearNumberCh", ""),
        "day_number_ch": entry.get("dayNumberCh", ""),
    }


def main():
    jdns = generate_jdn_samples(NUM_SAMPLES)
    records: list[dict] = []

    print(f"Fetching {NUM_SAMPLES} records from DILA (JDN {jdns[0]}..{jdns[-1]})...")
    print(f"Estimated time: {NUM_SAMPLES * (DELAY_MIN + DELAY_MAX) / 2 / 60:.0f} minutes")

    for i, jdn in enumerate(jdns):
        print(f"  [{i+1}/{NUM_SAMPLES}] JDN {jdn}...", end=" ", flush=True)

        result = fetch_date(jdn)
        if result is None:
            print("SKIP (no data)")
            continue

        # Take the first entry (Chinese calendar) as primary record
        # Also store all entries for cross-calendar verification
        all_entries = []
        for key in sorted(result.keys()):
            if key.startswith("data"):
                entry = result[key]
                all_entries.append(normalize_record(jdn, entry))

        if all_entries:
            record = {
                "query_jdn": jdn,
                "primary": all_entries[0],
                "all_calendars": all_entries,
            }
            records.append(record)
            p = record["primary"]
            print(f"{p['dynasty']} {p['era']}{p['year_number_ch']} "
                  f"{p['lunar_month']}月{p['day_number_ch']} = {p['ce_date']}")
        else:
            print("SKIP (empty)")

        if i < NUM_SAMPLES - 1:
            delay = random.uniform(DELAY_MIN, DELAY_MAX)
            time.sleep(delay)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"\nDone! Saved {len(records)} records to {OUTPUT}")


if __name__ == "__main__":
    main()
