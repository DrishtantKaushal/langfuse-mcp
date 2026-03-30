# langfuse-analyst

Langfuse MCP server with built-in analytics. Full data access plus token percentiles, accuracy metrics, failure detection, cost breakdowns, session analytics, latency analysis, and context breach scanning.

## Setup

**1. Get your API keys:**

- **Langfuse Cloud:** [cloud.langfuse.com](https://cloud.langfuse.com) → Settings → API Keys
- **Self-hosted:** Your Langfuse instance → Settings → API Keys. Set `LANGFUSE_HOST` to your instance URL (e.g., `https://langfuse.yourcompany.com`). The default is `https://cloud.langfuse.com`.

**2. Add the MCP server** to your client:

### Claude Code

```bash
claude mcp add \
  -e LANGFUSE_PUBLIC_KEY=pk-lf-... \
  -e LANGFUSE_SECRET_KEY=sk-lf-... \
  -e LANGFUSE_HOST=https://cloud.langfuse.com \
  --scope project \
  langfuse-analyst -- uvx langfuse-analyst
```

### Codex CLI

```bash
codex mcp add langfuse-analyst \
  --env LANGFUSE_PUBLIC_KEY=pk-lf-... \
  --env LANGFUSE_SECRET_KEY=sk-lf-... \
  --env LANGFUSE_HOST=https://cloud.langfuse.com \
  -- uvx langfuse-analyst
```

### Cursor

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "langfuse-analyst": {
      "command": "uvx",
      "args": ["langfuse-analyst"],
      "env": {
        "LANGFUSE_PUBLIC_KEY": "pk-lf-...",
        "LANGFUSE_SECRET_KEY": "sk-lf-...",
        "LANGFUSE_HOST": "https://cloud.langfuse.com"
      }
    }
  }
}
```

**3. Verify** — restart your CLI, then test with `/mcp` (Claude Code) or `codex mcp list` (Codex).

### Manual install (alternative to uvx)

```bash
pip install langfuse-analyst
langfuse-analyst serve
```

## Configuration

| Env Variable | Default | Description |
|---|---|---|
| `LANGFUSE_PUBLIC_KEY` | (required) | Langfuse public API key |
| `LANGFUSE_SECRET_KEY` | (required) | Langfuse secret API key |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse instance URL |
| `LANGFUSE_INTERNAL_DOMAINS` | `""` | Comma-separated internal domains to exclude from analytics (e.g., `mycompany.com,test.com`). Only applies when using `group_by='domain'`. |
| `LANGFUSE_MCP_READ_ONLY` | `false` | Disable write operations (score_traces, create_dataset, etc.) |
| `LANGFUSE_PAGE_LIMIT` | `100` | Traces per API page |

---

## All 34 Tools

### Analytics Tools (9)

| Tool | What it computes |
|---|---|
| `aggregate_by_group` | Per-group metrics: trace count, sessions, users, accuracy, latency, cost |
| `compute_accuracy` | Feedback-based accuracy with grouping and time bucketing |
| `detect_failures` | Pattern-based LLM output failure detection + feedback cross-reference |
| `compute_token_percentiles` | TP50/TP90/TP95/TP99 token usage at trace level |
| `detect_context_breaches` | Per-generation context window threshold scanning |
| `analyze_sessions` | Multi-turn depth, engagement, session-level cost/latency |
| `estimate_costs` | Cost breakdown by group or time bucket |
| `analyze_latency` | Latency percentiles at trace and per-generation/model level |
| `score_traces` | Write scores back to Langfuse (annotate traces after analysis) |

### Data Access Tools (25)

| Category | Tools |
|---|---|
| **Traces** | `fetch_traces`, `fetch_trace` |
| **Observations** | `fetch_observations`, `fetch_observation` |
| **Sessions** | `fetch_sessions`, `get_session_details`, `get_user_sessions` |
| **Errors** | `find_exceptions`, `get_exception_details`, `get_error_count` |
| **Scores** | `fetch_scores` |
| **Prompts** | `list_prompts`, `get_prompt`, `create_text_prompt`, `create_chat_prompt`, `update_prompt_labels` |
| **Datasets** | `list_datasets`, `get_dataset`, `list_dataset_items`, `get_dataset_item`, `create_dataset`, `create_dataset_item`, `delete_dataset_item` |
| **Schema** | `get_data_schema` |

---

## Sample Questions

### Agent & Pipeline Health

```
"Which agents failed the most this week?"
"What's the failure rate by agent name?"
"Which agent has the worst accuracy?"
"Show me the top 5 agents by trace volume"
"Are any agents consistently slower than others?"
```

### Accuracy & Quality

```
"What's our overall accuracy this week?"
"What's the accuracy trend by week for the last 30 days?"
"Compare accuracy across different agents"
"What's the daily accuracy breakdown?"
"Which users are getting the worst accuracy?"
"What percentage of traces have feedback scores?"
```

### Failures & Debugging

```
"Show me failure examples from today"
"What are the most common failure patterns?"
"Which users are seeing the most failures?"
"What's the failure rate by agent?"
"Are failures increasing or decreasing this week vs last?"
"Show me traces where the LLM said 'unable to' or 'I can't'"
```

### Token Usage

```
"What are the P90 and P99 token usage stats?"
"Which agents consume the most tokens?"
"Compare token usage across user groups"
"Are any users hitting unusually high token counts?"
```

### Context Window Breaches

```
"Are any generations exceeding the 128K context window?"
"Show me traces with token usage above 200K per generation"
"What's the breach severity distribution?"
"Which users trigger the most context window breaches?"
```

### Sessions & Engagement

```
"What's our multi-turn rate?"
"How deep are sessions on average?"
"Which users have the deepest sessions?"
"How many single-turn vs multi-turn sessions this week?"
"What's the average session cost?"
```

### Cost

```
"How much are we spending per day this week?"
"What's the weekly cost trend for the last 30 days?"
"Which agent is the most expensive?"
"Which users are costing the most?"
"What's the average cost per trace?"
```

### Latency

```
"What's the P95 latency?"
"Is latency getting worse over time?"
"Which model is the slowest?"
"Compare latency across agents"
"Show me per-generation latency breakdown by model"
"Which users are experiencing the highest latency?"
```

### Annotation & Write-back

```
"Score all failing traces from today with 'needs-review'"
"Tag these trace IDs as 'high-quality' for dataset creation"
"Mark trace abc-123 with a score of 0 and comment 'hallucinated output'"
```

### Lookups & Exploration

```
"Fetch the last 20 traces"
"Show me trace abc-123 with all its observations"
"List sessions for user alice@example.com"
"What errors happened in the last 24 hours?"
"How many errors occurred this week?"
"Show me all prompts in the project"
"List all datasets"
"What fields are available on traces and observations?"
```

---

### Grouping Options

The `group_by` parameter controls how traces are segmented in analytics tools:

| Value | What it groups by | When to use |
|---|---|---|
| `name` | Trace/agent name (default) | Compare performance across different agents or pipelines |
| `userId` | Per-user breakdown | Identify users with issues or high usage |
| `domain` | Email domain extracted from userId | Multi-tenant apps where users have email-based IDs (e.g., `user@acme.com` → `acme.com`) |
| `tag` | Trace tags | Compare across tagged environments, versions, or experiments |

---

## License

MIT
