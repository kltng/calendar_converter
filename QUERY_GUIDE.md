# SQLite Query Guide

Direct SQL queries against `data/calendar.db` for calendar conversion and historical date research.

## Schema Overview

```
dynasty (id, type)                          -- 135 rows, type: chinese|japanese|korean|vietnamese
  dynasty_name (dynasty_id, name, ranking, language_id)  -- 161 rows
    emperor (id, dynasty_id)                -- 772 rows
      emperor_name (emperor_id, name, ranking, language_id)  -- 1,120 rows
        era (id, emperor_id)                -- 1,637 rows
          era_name (era_id, name, ranking, language_id)  -- 2,100 rows
            month (id, era_id, year, month, month_name, leap_month,
                   first_jdn, last_jdn, ganzhi, start_from, status, eclipse)  -- 131,808 rows

era_summary (VIEW)  -- 1,621 rows: joins era→emperor→dynasty with MIN/MAX JDN
day_comment (id, jdn, comment)  -- 57 rows
period (id, dynasty_id, first_jdn, last_jdn, description, note)
```

**Key concept:** `month` is the core table. Each row is one lunar month with a JDN range. A specific day is found by: `jdn = first_jdn + (day_number - start_from)`.

---

## 1. Look Up a CJK Date → JDN

Given era name, year, month, and day:

```sql
-- 崇禎三年四月初三 → JDN
SELECT m.first_jdn + (3 - m.start_from) AS jdn
FROM month m
JOIN era_summary es ON es.era_id = m.era_id
WHERE es.era_name = '崇禎'
  AND m.year = 3
  AND m.month = 4
  AND m.leap_month = 0;
```

For a leap month, set `leap_month = 1`:

```sql
-- 天保三年閏九月十五日
SELECT m.first_jdn + (15 - m.start_from) AS jdn
FROM month m
JOIN era_summary es ON es.era_id = m.era_id
WHERE es.era_name = '天保'
  AND m.year = 3
  AND m.month = 9
  AND m.leap_month = 1;
```

## 2. Look Up a JDN → All CJK Dates

Find all calendar representations for a given day:

```sql
-- JDN 2316539 → all concurrent eras
SELECT
    es.dynasty_name,
    es.era_name,
    es.emperor_name,
    es.country,
    m.year,
    m.month,
    m.month_name,
    m.leap_month,
    (? - m.first_jdn + m.start_from) AS day,
    m.ganzhi AS year_ganzhi
FROM month m
JOIN era_summary es ON es.era_id = m.era_id
WHERE m.first_jdn <= 2316539 AND m.last_jdn >= 2316539
ORDER BY es.country, m.first_jdn;
```

## 3. Disambiguate Era Names

Many era names are reused across dynasties/countries. Find all matches:

```sql
-- How many eras are named 太平?
SELECT es.era_name, es.dynasty_name, es.country,
       es.emperor_name, es.start_jdn, es.end_jdn
FROM era_summary es
WHERE es.era_name = '太平'
ORDER BY es.start_jdn;
```

Filter by country:

```sql
SELECT * FROM era_summary
WHERE era_name = '建武' AND country = 'chinese'
ORDER BY start_jdn;
```

Filter by dynasty:

```sql
SELECT * FROM era_summary
WHERE era_name = '建武' AND dynasty_name = '東漢';
```

## 4. List All Eras in a Dynasty

```sql
SELECT es.era_name, es.emperor_name, es.start_jdn, es.end_jdn
FROM era_summary es
WHERE es.dynasty_name = '明'
ORDER BY es.start_jdn;
```

## 5. List All Eras for a Country

```sql
-- All Chinese eras
SELECT * FROM era_summary WHERE country = 'chinese' ORDER BY start_jdn;

-- All Japanese eras
SELECT * FROM era_summary WHERE country = 'japanese' ORDER BY start_jdn;

-- All Korean eras
SELECT * FROM era_summary WHERE country = 'korean' ORDER BY start_jdn;

-- All Vietnamese eras
SELECT * FROM era_summary WHERE country = 'vietnamese' ORDER BY start_jdn;
```

## 6. Find Year by Ganzhi (干支) Within an Era

When a historical source gives a ganzhi year instead of a number:

```sql
-- 嘉慶甲子年 = which year number?
SELECT DISTINCT m.year, m.ganzhi
FROM month m
JOIN era_summary es ON es.era_id = m.era_id
WHERE es.era_name = '嘉慶' AND es.country = 'chinese'
  AND m.ganzhi = '甲子';
-- Result: year 9
```

List all ganzhi years in an era:

```sql
SELECT DISTINCT m.year, m.ganzhi
FROM month m
JOIN era_summary es ON es.era_id = m.era_id
WHERE es.era_name = '康熙' AND es.country = 'chinese'
ORDER BY m.year;
```

## 7. Find Leap Months

All leap months in a specific era and year:

```sql
SELECT m.year, m.month, m.month_name, m.first_jdn, m.last_jdn
FROM month m
JOIN era_summary es ON es.era_id = m.era_id
WHERE es.era_name = '康熙' AND m.leap_month = 1
ORDER BY m.first_jdn;
```

Check if a specific year has a leap month:

```sql
SELECT m.month, m.month_name
FROM month m
JOIN era_summary es ON es.era_id = m.era_id
WHERE es.era_name = '崇禎' AND es.country = 'chinese'
  AND m.year = 3 AND m.leap_month = 1;
```

## 8. Count Days in a Lunar Month

```sql
-- How many days in 崇禎三年四月?
SELECT m.last_jdn - m.first_jdn + 1 AS days_in_month
FROM month m
JOIN era_summary es ON es.era_id = m.era_id
WHERE es.era_name = '崇禎' AND m.year = 3
  AND m.month = 4 AND m.leap_month = 0;
```

## 9. List All Months in a Year

```sql
SELECT m.month, m.month_name, m.leap_month,
       m.first_jdn, m.last_jdn,
       m.last_jdn - m.first_jdn + 1 AS days,
       m.ganzhi AS year_ganzhi
FROM month m
JOIN era_summary es ON es.era_id = m.era_id
WHERE es.era_name = '崇禎' AND es.country = 'chinese'
  AND m.year = 3
ORDER BY m.first_jdn;
```

## 10. Date Range Queries

Find all eras active during a JDN range:

```sql
-- Which eras were active around 1630 CE (JDN ~2316500)?
SELECT es.era_name, es.dynasty_name, es.country,
       es.start_jdn, es.end_jdn
FROM era_summary es
WHERE es.start_jdn <= 2316600 AND es.end_jdn >= 2316400
ORDER BY es.country, es.start_jdn;
```

Find the era for a specific JDN:

```sql
SELECT es.era_name, es.dynasty_name, es.country
FROM era_summary es
WHERE es.start_jdn <= 2316539 AND es.end_jdn >= 2316539
ORDER BY es.country;
```

## 11. Era Name Search (Multilingual)

The `era_name` table stores names in multiple languages (ranking 0 = primary Chinese):

```sql
-- Find all name variants for an era
SELECT en.name, en.ranking, en.language_id
FROM era_name en
JOIN era_summary es ON es.era_id = en.era_id
WHERE es.era_name = '崇禎'
ORDER BY en.era_id, en.ranking;
```

Search by alternate name:

```sql
-- Find era by any name variant
SELECT es.*
FROM era_summary es
JOIN era_name en ON en.era_id = es.era_id
WHERE en.name = 'Chongzhen';
```

## 12. Emperor and Dynasty Lookups

All emperors in a dynasty:

```sql
SELECT empn.name AS emperor_name, dn.name AS dynasty_name
FROM emperor emp
JOIN emperor_name empn ON empn.emperor_id = emp.id AND empn.ranking = 0
JOIN dynasty_name dn ON dn.dynasty_id = emp.dynasty_id AND dn.ranking = 0
WHERE dn.name = '清'
ORDER BY emp.id;
```

All eras for a specific emperor:

```sql
SELECT es.era_name, es.start_jdn, es.end_jdn
FROM era_summary es
WHERE es.emperor_name = '高宗'
ORDER BY es.start_jdn;
```

## 13. Day Comments

Historical notes attached to specific days:

```sql
SELECT dc.jdn, dc.comment
FROM day_comment dc
WHERE dc.jdn = 2316539;
```

Find all comments in a date range:

```sql
SELECT dc.jdn, dc.comment
FROM day_comment dc
WHERE dc.jdn BETWEEN 2316000 AND 2317000
ORDER BY dc.jdn;
```

## 14. Proleptic vs Standard Dates

The `status` column marks proleptic (hypothetical) extensions:

```sql
-- Only standard (historically attested) months
SELECT * FROM month
WHERE era_id = 650 AND status = 'S'
ORDER BY first_jdn;

-- Only proleptic months
SELECT * FROM month
WHERE era_id = 650 AND status = 'P'
ORDER BY first_jdn;
```

## 15. Cross-Calendar Date Comparison

Find what date a CJK date corresponds to in other calendars:

```sql
-- Step 1: Get JDN for 崇禎三年四月初三
-- Step 2: Find all concurrent representations
WITH target AS (
    SELECT m.first_jdn + (3 - m.start_from) AS jdn
    FROM month m
    JOIN era_summary es ON es.era_id = m.era_id
    WHERE es.era_name = '崇禎' AND es.country = 'chinese'
      AND m.year = 3 AND m.month = 4 AND m.leap_month = 0
    LIMIT 1
)
SELECT
    es.country,
    es.dynasty_name,
    es.era_name,
    m.year,
    m.month_name || CASE WHEN m.leap_month THEN '(閏)' ELSE '' END AS month,
    (target.jdn - m.first_jdn + m.start_from) AS day,
    m.ganzhi AS year_ganzhi
FROM target, month m
JOIN era_summary es ON es.era_id = m.era_id
WHERE m.first_jdn <= target.jdn AND m.last_jdn >= target.jdn
ORDER BY es.country;
```

## 16. Statistics and Coverage

```sql
-- Date range coverage per country
SELECT es.country,
       COUNT(DISTINCT es.era_id) AS num_eras,
       MIN(es.start_jdn) AS earliest_jdn,
       MAX(es.end_jdn) AS latest_jdn
FROM era_summary es
WHERE es.country != ''
GROUP BY es.country;

-- Dynasties per country
SELECT d.type AS country, COUNT(*) AS num_dynasties
FROM dynasty d
WHERE d.type != ''
GROUP BY d.type;

-- Total lunar months
SELECT COUNT(*) FROM month;
```

## Notes

- **JDN** (Julian Day Number) is the universal pivot. All conversions go through JDN.
- **Ganzhi day** is computed, not stored: `ganzhi_index = (JDN + 49) % 60`.
- **Ganzhi month** is computed from year ganzhi + month number via the 五虎遁 formula.
- **Ganzhi year** is stored in the `month.ganzhi` column.
- Pre-1582 Gregorian dates are proleptic. Use Julian calendar formulas for historical accuracy.
- `start_from` is usually 1, but can differ for months that were split across eras.
