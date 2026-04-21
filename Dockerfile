FROM python:3.12-slim

RUN useradd --create-home --uid 1000 mcp

WORKDIR /app

COPY pyproject.toml README.md ./
COPY langfuse_mcp ./langfuse_mcp

RUN pip install --no-cache-dir .

USER mcp

EXPOSE 8000

ENV MCP_TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

CMD ["langfuse-mcp"]
