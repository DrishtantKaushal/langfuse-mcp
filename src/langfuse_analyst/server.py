"""langfuse-analyst MCP server."""
from __future__ import annotations
import os

from dotenv import load_dotenv
load_dotenv()

from fastmcp import FastMCP

from .config import Config
from .client import LangfuseClient
from .tools.data_access import register_data_access_tools
from .tools.analytics import register_analytics_tools

config = Config.from_env()
client = LangfuseClient(config)

mcp = FastMCP(
    "langfuse-analyst",
    instructions="""Langfuse analytics MCP server.

Available capabilities:
- DATA ACCESS: Fetch traces, observations, sessions, scores, prompts, datasets
- ANALYTICS: Aggregate by group, compute accuracy, detect failures, token percentiles,
  context breach scanning, session analysis, cost breakdown, latency analysis
- WRITE-BACK: Score and annotate traces

For lookups, use data access tools (fetch_traces, fetch_trace, etc.).
For analytical questions, use analytics tools.

Time range presets: today, yesterday, last_7_days, last_15_days, last_30_days,
last_90_days, or custom with start_date/end_date.

Use group_by='domain' to segment by user email domain.
Set LANGFUSE_INTERNAL_DOMAINS env var to filter internal users.
""",
)

register_data_access_tools(mcp, client)
register_analytics_tools(mcp, client)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
