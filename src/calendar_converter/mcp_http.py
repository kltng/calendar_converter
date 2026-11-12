"""
MCP server using FastMCP with HTTP transports.

Mounted into the FastAPI app:
- /mcp  — Streamable HTTP (for modern MCP clients)
- /sse  — SSE transport (for LM Studio and other SSE-based clients)

The tools are the same as the stdio MCP server's: both register them from tools.py.
"""

import os

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from .db import get_connection
from .tools import register_tools

_allowed_hosts = ["localhost", "127.0.0.1"]
if os.environ.get("MCP_ALLOWED_HOST"):
    _allowed_hosts.append(os.environ["MCP_ALLOWED_HOST"])

mcp = FastMCP(
    "cjk-calendar-converter",
    json_response=True,
    streamable_http_path="/",
    sse_path="/",
    message_path="/messages/",
    transport_security=TransportSecuritySettings(
        allowed_hosts=_allowed_hosts,
        allowed_origins=[origin.strip() for origin in os.environ.get("MCP_ALLOWED_ORIGINS", "").split(",") if origin.strip()],
    ),
)


def _get_conn():
    return get_connection(check_same_thread=False)


register_tools(mcp, _get_conn)
