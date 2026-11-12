"""
MCP (Model Context Protocol) server for CJK calendar conversion.

Exposes calendar conversion as tools that LLMs can call directly.
Supports both stdio and SSE transports.

Run with:
  stdio: uv run python -m src.calendar_converter.mcp_server
  SSE:   uv run python -m src.calendar_converter.mcp_server --transport sse
"""

import argparse
from typing import Any

from mcp.server.fastmcp import FastMCP

from .tools import handle_tool_call, register_tools


mcp = FastMCP(
    "cjk-calendar-converter",
    host="127.0.0.1",
    port=8000,
)
register_tools(mcp)


def _handle_tool_call(name: str, arguments: dict[str, Any]) -> str:
    """Execute a tool call and return JSON result."""
    return handle_tool_call(name, arguments)


def main() -> None:
    """Run the MCP server."""
    parser = argparse.ArgumentParser(description="CJK Calendar Converter MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for SSE transport (default: 8000)",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        mcp.settings.port = args.port

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
