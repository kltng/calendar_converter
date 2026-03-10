"""Pydantic models for API request/response."""

from pydantic import BaseModel, Field


class EraInfo(BaseModel):
    era_name: str
    era_id: int
    emperor_name: str | None = None
    dynasty_name: str | None = None
    country: str  # 'chinese', 'japanese', 'korean'
    year_in_era: int
    month: int
    month_name: str
    is_leap_month: bool
    day: int


class GanzhiInfo(BaseModel):
    year: str = ""
    month: str = ""
    day: str = ""


class AmbiguousCandidate(BaseModel):
    """One possible interpretation when an era name is ambiguous."""
    jdn: int = Field(description="Julian Day Number for this interpretation")
    gregorian: str = Field(description="Gregorian date (ISO 8601)")
    era_name: str
    dynasty_name: str | None = None
    emperor_name: str | None = None
    country: str
    year_in_era: int
    month: int
    day: int


class DateConversion(BaseModel):
    jdn: int = Field(description="Julian Day Number")
    gregorian: str = Field(description="Proleptic Gregorian date (ISO 8601)")
    julian: str | None = Field(None, description="Julian calendar date (for pre-1582)")
    ganzhi: GanzhiInfo = Field(default_factory=GanzhiInfo)
    cjk_dates: list[EraInfo] = Field(
        default_factory=list,
        description="All concurrent CJK era representations for this date",
    )
    ambiguous: bool = Field(
        False,
        description="True when the input era name matched multiple distinct eras. "
        "The returned date is the first match; check other_candidates for alternatives.",
    )
    other_candidates: list[AmbiguousCandidate] = Field(
        default_factory=list,
        description="Other possible interpretations when era name is ambiguous. "
        "Use dynasty/emperor hints to disambiguate.",
    )


class ParsedDate(BaseModel):
    era: str
    year: int | None = None
    month: int | None = None
    day: int | None = None
    is_leap_month: bool = False
    country_hint: str | None = None
    dynasty_hint: str | None = None
    emperor_hint: str | None = None
    ganzhi_year: str | None = None
    ganzhi_month: str | None = None
    ganzhi_day: str | None = None


class EraMetadata(BaseModel):
    era_id: int
    era_name: str
    emperor_name: str | None = None
    dynasty_name: str | None = None
    country: str
    start_jdn: int | None = None
    end_jdn: int | None = None
    start_gregorian: str | None = None
    end_gregorian: str | None = None


class ErrorResponse(BaseModel):
    error: str
    candidates: list[EraMetadata] = Field(
        default_factory=list,
        description="Possible era matches when input is ambiguous",
    )
