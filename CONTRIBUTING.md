# Contributing

Contributions are welcome. Here's how to get started.

## Development Setup

```bash
git clone https://github.com/DrishtantKaushal/langfuse-mcp.git
cd langfuse-mcp
uv venv .venv && source .venv/bin/activate
uv pip install -e "."
```

## Running Locally

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-... \
LANGFUSE_SECRET_KEY=sk-lf-... \
LANGFUSE_HOST=https://cloud.langfuse.com \
python -m langfuse_mcp
```

## Testing

Verify all tools register correctly:

```bash
LANGFUSE_PUBLIC_KEY=test LANGFUSE_SECRET_KEY=test python -c "
import asyncio
from langfuse_mcp.server import mcp
async def main():
    tools = await mcp.list_tools()
    print(f'{len(tools)} tools registered')
    for t in sorted(tools, key=lambda x: x.name):
        print(f'  {t.name}')
asyncio.run(main())
"
```

Test selective tool loading:

```bash
LANGFUSE_PUBLIC_KEY=test LANGFUSE_SECRET_KEY=test LANGFUSE_TOOLS=traces,analytics python -c "
import asyncio
from langfuse_mcp.server import mcp
async def main():
    tools = await mcp.list_tools()
    print(f'{len(tools)} tools registered (should be 11)')
asyncio.run(main())
"
```

## Submitting Changes

1. **Fork** the repository
2. **Create a branch** for your feature (`git checkout -b feature/my-feature`)
3. **Make your changes** — follow the code style guidelines below
4. **Test** — verify your changes work with `python -m langfuse_mcp`
5. **Submit a PR** with a clear description of what you changed and why

## Code Style

- **Tools are outcome-oriented** — return computed insights, not raw API dumps
- **Analytics tools** should accept `time_range`, `group_by`, and `tags` parameters consistently
- **Tool descriptions are prompt engineering** — they land directly in the LLM's context. Be precise about *when* to use each tool and how it differs from similar tools.
- **Return compact JSON** summaries sized for LLM context windows, not full API responses
- **Don't add dependencies** unless absolutely necessary
- **Keep functions focused** — one tool, one outcome

## Areas for Contribution

- Additional analytics tools (e.g., model comparison, prompt version tracking, retry detection)
- Trace visualization (Mermaid waterfall, ASCII span tree)
- Performance improvements (caching, connection pooling)
- Documentation and examples
- Bug fixes and edge case handling
- Support for additional MCP clients
