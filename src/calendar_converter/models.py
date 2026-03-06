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


class DateConversion(BaseModel):
    jdn: int = Field(description="Julian Day Number")
    gregorian: str = Field(description="Proleptic Gregorian date (ISO 8601)")
    julian: str | None = Field(None, description="Julian calendar date (for pre-1582)")
    ganzhi: GanzhiInfo = Field(default_factory=GanzhiInfo)
    cjk_dates: list[EraInfo] = Field(
        default_factory=list,
        description="All concurrent CJK era representations for this date",
    )


class ParsedDate(BaseModel):
    era: str
    year: int
    month: int | None = None
    day: int | None = None
    is_leap_month: bool = False
    country_hint: str | None = None


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
