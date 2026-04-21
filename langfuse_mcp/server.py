"""langfuse-mcp server."""
from __future__ import annotations
import os

from dotenv import load_dotenv
load_dotenv()

from fastmcp import FastMCP

from .config import Config
from .client import LangfuseClient
from .tools.data_access import register_data_access_tools
from .tools.analytics import register_analytics_tools
from .tools.annotation_queues import register_annotation_queue_tools

config = Config.from_env()
client = LangfuseClient(config)

_google_client_id = os.getenv("GOOGLE_CLIENT_ID")
_google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
_mcp_base_url = os.getenv("MCP_BASE_URL")

auth = None
if _google_client_id and _google_client_secret and _mcp_base_url:
    from fastmcp.server.auth.providers.google import GoogleProvider

    auth = GoogleProvider(
        client_id=_google_client_id,
        client_secret=_google_client_secret,
        base_url=_mcp_base_url,
        required_scopes=[
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
        ],
        allowed_client_redirect_uris=[
            "https://claude.ai/api/mcp/auth_callback",
            "https://claude.com/api/mcp/auth_callback",
            "http://localhost:*",
            "http://127.0.0.1:*",
        ],
    )

mcp = FastMCP(
    "langfuse-mcp",
    auth=auth,
    instructions="""Langfuse analytics MCP server.

Available capabilities:
- DATA ACCESS: Fetch traces, observations, sessions, scores, prompts, datasets
- ANALYTICS: Aggregate by group, compute accuracy, detect failures, token percentiles,
  context breach scanning, session analysis, cost breakdown, latency analysis
- CONTENT TOOLS: List user queries, find slow traces, search trace content by keyword
- WRITE-BACK: Score and annotate traces

IMPORTANT routing rules:
- "What queries/questions did users ask?" → list_user_queries (NOT fetch_traces)
- "Which traces were slowest?" → find_slow_traces (NOT fetch_traces)
- "Find traces about X / mentioning X" → search_trace_content (NOT fetch_traces)
- For aggregate stats (accuracy, costs, latency percentiles) → use analytics tools
- fetch_traces returns COMPACT metadata only (no input/output). Use fetch_trace(id) for full details.

Default time range is 'today' unless the user specifies otherwise.
Available presets: today, yesterday, last_7_days, last_15_days, last_30_days,
last_90_days, or custom with start_date/end_date.
Configurable via LANGFUSE_DEFAULT_TIME_RANGE env var.

Use group_by='domain' to segment by user email domain.
Set LANGFUSE_INTERNAL_DOMAINS env var to filter internal users.
""",
)

# Selective tool loading: LANGFUSE_TOOLS=traces,analytics or --tools traces,prompts
# Available groups: traces, observations, sessions, errors, scores, prompts, datasets, schema, analytics
_enabled_tools = os.getenv("LANGFUSE_TOOLS", "").strip()
_enabled_groups = {g.strip().lower() for g in _enabled_tools.split(",") if g.strip()} if _enabled_tools else None

# If no filter specified, register everything
if _enabled_groups is None:
    register_data_access_tools(mcp, client)
    register_annotation_queue_tools(mcp, client)
    register_analytics_tools(mcp, client)
else:
    register_data_access_tools(mcp, client, enabled_groups=_enabled_groups)
    register_annotation_queue_tools(mcp, client, enabled_groups=_enabled_groups)
    if "analytics" in _enabled_groups:
        register_analytics_tools(mcp, client)


if auth is not None:
    _allowed_emails = {
        e.strip().lower()
        for e in os.getenv("ALLOWED_EMAILS", "").split(",")
        if e.strip()
    }
    _allowed_domains = {
        d.strip().lower().lstrip("@")
        for d in os.getenv("ALLOWED_EMAIL_DOMAINS", "").split(",")
        if d.strip()
    }

    if _allowed_emails or _allowed_domains:
        from fastmcp.server.middleware import Middleware
        from fastmcp.server.dependencies import get_access_token
        from fastmcp.exceptions import ToolError

        class EmailAllowlistMiddleware(Middleware):
            async def on_call_tool(self, context, call_next):
                token = get_access_token()
                if token is None:
                    raise ToolError("Authentication required")
                claims = token.claims or {}
                if not claims.get("email_verified"):
                    raise ToolError("Email not verified by Google")
                email = (claims.get("email") or "").lower()
                if not email:
                    raise ToolError("No email claim in token")
                if _allowed_emails and email in _allowed_emails:
                    return await call_next(context)
                if _allowed_domains:
                    domain = email.rsplit("@", 1)[-1] if "@" in email else ""
                    if domain in _allowed_domains:
                        return await call_next(context)
                raise ToolError(f"Access denied for {email}")

        mcp.add_middleware(EmailAllowlistMiddleware())


def main():
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    if transport == "stdio":
        mcp.run()
    else:
        host = os.getenv("MCP_HOST", "0.0.0.0")
        port = int(os.getenv("MCP_PORT", "8000"))
        mcp.run(transport=transport, host=host, port=port)


if __name__ == "__main__":
    main()
