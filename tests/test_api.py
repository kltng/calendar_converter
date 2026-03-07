"""Tests for FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient
from src.calendar_converter.api import app
from src.calendar_converter.db import get_connection


@pytest.fixture(scope="module")
def client():
    # Manually set up the connection for testing
    import src.calendar_converter.api as api_module
    api_module._conn = get_connection(check_same_thread=False)
    with TestClient(app) as c:
        yield c
    api_module._conn = None


class TestHealth:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


class TestConvert:
    def test_convert_cjk_date(self, client):
        r = client.get("/convert", params={"date": "崇禎三年四月初三"})
        assert r.status_code == 200
        data = r.json()
        assert data["jdn"] == 2316539
        assert data["gregorian"] == "1630-05-14"
        assert len(data["cjk_dates"]) >= 1

    def test_convert_by_jdn(self, client):
        r = client.get("/convert", params={"jdn": 2316539})
        assert r.status_code == 200
        data = r.json()
        assert data["gregorian"] == "1630-05-14"

    def test_convert_by_gregorian(self, client):
        r = client.get("/convert", params={"gregorian": "1630-05-14"})
        assert r.status_code == 200
        data = r.json()
        assert data["jdn"] == 2316539

    def test_convert_no_params(self, client):
        r = client.get("/convert")
        assert r.status_code == 400

    def test_convert_invalid_date(self, client):
        r = client.get("/convert", params={"date": "garbage"})
        assert r.status_code == 400

    def test_convert_unknown_era(self, client):
        r = client.get("/convert", params={"date": "不存在元年正月初一"})
        assert r.status_code == 200
        data = r.json()
        assert "error" in data

    def test_convert_with_country_hint(self, client):
        r = client.get("/convert", params={"date": "寛永七年四月初三", "country": "japanese"})
        assert r.status_code == 200

    def test_convert_with_dynasty_hint(self, client):
        r = client.get("/convert", params={"date": "至元三年正月初一", "dynasty": "元"})
        assert r.status_code == 200
        data = r.json()
        assert "error" not in data
        assert data["jdn"] > 0

    def test_convert_with_emperor_hint(self, client):
        """上元二年 with emperor=肅宗 should return 761 CE."""
        r = client.get("/convert", params={"date": "上元二年正月初一", "emperor": "肅宗"})
        assert r.status_code == 200
        data = r.json()
        assert "error" not in data
        assert data["gregorian"].startswith("0761")

    def test_convert_with_dynasty_and_emperor_hint(self, client):
        """至元 with dynasty=元, emperor=順帝 -> 1337."""
        r = client.get("/convert", params={
            "date": "至元三年正月初一", "dynasty": "元", "emperor": "順帝",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["gregorian"].startswith("1337")


class TestEras:
    def test_search_by_name(self, client):
        r = client.get("/eras", params={"name": "崇禎"})
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1
        assert data[0]["era_name"] == "崇禎"

    def test_search_by_dynasty(self, client):
        r = client.get("/eras", params={"dynasty": "明"})
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0

    def test_search_by_country(self, client):
        r = client.get("/eras", params={"country": "japanese"})
        assert r.status_code == 200
        data = r.json()
        assert all(e["country"] == "japanese" for e in data)


class TestDBDownload:
    def test_download_db(self, client):
        r = client.get("/db/download")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/x-sqlite3"
        # Verify it starts with SQLite magic bytes
        assert r.content[:16].startswith(b"SQLite format 3")


class TestBatch:
    def test_batch_convert(self, client):
        r = client.post("/convert/batch", json=[
            "崇禎三年四月初三",
            "康熙元年正月初一",
        ])
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        assert data[0]["gregorian"] == "1630-05-14"
