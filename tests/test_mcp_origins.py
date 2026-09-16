"""Exercise transport origin enforcement without opening the calendar database."""
import asyncio
import runpy

from mcp.server.transport_security import TransportSecurityMiddleware
from starlette.requests import Request


def test_configured_origins_preserve_host_protection(monkeypatch):
    monkeypatch.setenv("MCP_ALLOWED_HOST", "calendar.example")
    monkeypatch.setenv("MCP_ALLOWED_ORIGINS", " chrome-extension://example-id, ,https://client.example ")
    settings = runpy.run_module("src.calendar_converter.mcp_http")["mcp"].settings.transport_security
    middleware = TransportSecurityMiddleware(settings)

    def validate(origin, host="calendar.example"):
        headers = [(b"host", host.encode()), (b"content-type", b"application/json")]
        if origin is not None:
            headers.append((b"origin", origin.encode()))
        request = Request({"type": "http", "method": "POST", "path": "/mcp/", "headers": headers})
        return asyncio.run(middleware.validate_request(request, is_post=True))

    assert validate("chrome-extension://example-id") is None
    assert validate("https://client.example") is None
    assert validate(None) is None
    assert validate("https://untrusted.example").status_code == 403
    assert validate("chrome-extension://example-id", "untrusted.example").status_code == 421


def test_unconfigured_origins_default_to_empty(monkeypatch):
    monkeypatch.delenv("MCP_ALLOWED_ORIGINS", raising=False)
    settings = runpy.run_module("src.calendar_converter.mcp_http")["mcp"].settings.transport_security
    assert settings.allowed_origins == []
    assert settings.enable_dns_rebinding_protection
