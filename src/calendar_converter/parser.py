"""
Parse CJK date strings into structured form.

Handles formats like:
  崇禎三年四月初三
  天保三年閏九月十五日
  康熙六十一年十二月二十九日
  M45.7.30 (Japanese shorthand: Meiji 45, July 30)
  H26.6.8  (Heisei 26, June 8)
"""

import re
from dataclasses import dataclass


@dataclass
class ParsedDate:
    era: str
    year: int
    month: int | None = None
    day: int | None = None
    is_leap_month: bool = False
    country_hint: str | None = None


# Chinese numeral mapping
_DIGITS = {
    "〇": 0, "零": 0,
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9,
    "十": 10, "廿": 20, "卅": 30,
    "元": 1,  # 元年 = year 1
    "正": 1,  # 正月 = month 1
}

# Japanese era shorthand
_JP_ERA_SHORT = {
    "M": "明治",
    "T": "大正",
    "S": "昭和",
    "H": "平成",
    "R": "令和",
}


def _parse_chinese_number(s: str) -> int | None:
    """Parse a Chinese numeral string to int.

    Handles: 一 through 三十, plus 初X, 廿X, 卅X patterns.
    """
    if not s:
        return None

    # Single digit or special
    if len(s) == 1 and s in _DIGITS:
        return _DIGITS[s]

    # 初X = day X (1-10), e.g. 初三 = 3
    if s.startswith("初"):
        rest = s[1:]
        if rest and rest in _DIGITS:
            return _DIGITS[rest]
        return None

    # 十X patterns
    if s == "十":
        return 10
    if len(s) == 2 and s[0] == "十":
        ones = _DIGITS.get(s[1])
        if ones is not None:
            return 10 + ones
    if len(s) == 2 and s[1] == "十":
        tens = _DIGITS.get(s[0])
        if tens is not None:
            return tens * 10

    # XX十Y: e.g. 二十九 = 29
    if len(s) == 3 and s[1] == "十":
        tens = _DIGITS.get(s[0])
        ones = _DIGITS.get(s[2])
        if tens is not None and ones is not None:
            return tens * 10 + ones

    # 廿X / 卅X
    if len(s) == 2 and s[0] in ("廿", "卅"):
        base = _DIGITS[s[0]]
        ones = _DIGITS.get(s[1], 0)
        return base + ones

    # Try pure digit composition for longer numbers (e.g. 六十一)
    if "十" in s:
        parts = s.split("十")
        if len(parts) == 2:
            tens = _DIGITS.get(parts[0], 0) if parts[0] else 1
            ones = _DIGITS.get(parts[1], 0) if parts[1] else 0
            return tens * 10 + ones

    return None


# Main parsing regex for CJK dates
# Matches: [era_name][year]年[閏?][month]月[day]日?
_CJK_PATTERN = re.compile(
    r"^"
    r"(?P<era>[^\d\s年]{1,10}?)"       # era name (non-greedy, 1-10 chars)
    r"(?P<year>[元一二三四五六七八九十百廿卅\d]+)年"  # year + 年
    r"(?:"                              # optional month+day group
    r"(?P<leap>閏)?"                    # optional leap month marker
    r"(?P<month>[正一二三四五六七八九十廿]+)月"  # month + 月
    r"(?:"                              # optional day group
    r"(?P<day>[初一二三四五六七八九十廿卅]+)"    # day
    r"日?"                              # optional 日
    r")?"
    r")?"
    r"$"
)

# Japanese shorthand: M45.7.30
_JP_SHORT_PATTERN = re.compile(
    r"^(?P<era>[MTSHRLW])(?P<year>\d{1,4})"
    r"(?:\.(?P<month>\d{1,2})"
    r"(?:\.(?P<day>\d{1,2}))?"
    r")?$"
)


def parse_cjk_date(text: str) -> ParsedDate | None:
    """Parse a CJK date string into structured components.

    Returns None if the string cannot be parsed.
    """
    text = text.strip()
    if not text:
        return None

    # Try Japanese shorthand first (M45.7.30)
    m = _JP_SHORT_PATTERN.match(text)
    if m:
        era_char = m.group("era")
        era = _JP_ERA_SHORT.get(era_char)
        if era is None:
            return None
        year = int(m.group("year"))
        month = int(m.group("month")) if m.group("month") else None
        day = int(m.group("day")) if m.group("day") else None
        return ParsedDate(
            era=era, year=year, month=month, day=day,
            country_hint="japanese",
        )

    # Try CJK pattern
    m = _CJK_PATTERN.match(text)
    if m:
        era = m.group("era")
        year_str = m.group("year")
        is_leap = m.group("leap") is not None
        month_str = m.group("month")
        day_str = m.group("day")

        # Parse year
        if year_str == "元":
            year = 1
        elif year_str.isascii() and year_str.isdigit():
            year = int(year_str)
        else:
            year = _parse_chinese_number(year_str)
            if year is None:
                return None

        # Parse month
        month: int | None = None
        if month_str:
            month = _parse_chinese_number(month_str)

        # Parse day
        day: int | None = None
        if day_str:
            day = _parse_chinese_number(day_str)

        return ParsedDate(
            era=era, year=year, month=month, day=day,
            is_leap_month=is_leap,
        )

    return None
