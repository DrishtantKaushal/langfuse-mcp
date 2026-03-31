# Langfuse MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

<!-- Agent-readable metadata -->
<!-- llms.txt: ./llms.txt -->
<!-- keywords: langfuse, mcp, model-context-protocol, llm-observability, trace-analysis, ai-agents, claude-code, cursor, codex, langfuse-mcp, llm-analytics, token-usage, accuracy-metrics, failure-detection, cost-tracking, latency-analysis, session-analytics, context-window, prompt-management, dataset-management, mcp-server, llm-monitoring, ai-observability, openai, anthropic, langchain -->

[Model Context Protocol](https://modelcontextprotocol.io) server for [Langfuse](https://langfuse.com) observability. Query traces, analyze accuracy, detect failures, track costs, debug latency, manage prompts and datasets.

**34 tools** across data access and analytics. Works with [Claude Code](https://docs.anthropic.com/en/docs/claude-code), [Codex CLI](https://github.com/openai/codex), [Cursor](https://cursor.com), and any MCP-compatible client.

## Why this MCP server?

Comparison with [official Langfuse MCP](https://langfuse.com/docs/api-and-data-platform/features/mcp-server) (as of March 2026):

| Capability | This server | Official Langfuse MCP |
|---|:---:|:---:|
| Traces & Observations | Yes | No |
| Sessions & Users | Yes | No |
| Exception Tracking | Yes | No |
| Prompt Management | Yes | Yes |
| Dataset Management | Yes | No |
| Score Write-back | Yes | No |
| **Accuracy Metrics** | Yes | No |
| **Failure Detection** | Yes | No |
| **Token Percentiles** | Yes | No |
| **Cost Breakdown** | Yes | No |
| **Latency Analysis** | Yes | No |
| **Session Analytics** | Yes | No |
| **Context Breach Scanning** | Yes | No |
| **User Group Aggregation** | Yes | No |

The official MCP focuses on prompt management. This server provides a **full observability and analytics toolkit** — traces, observations, sessions, scores, exceptions, prompts, datasets, plus 9 built-in analytics tools that compute insights server-side and return LLM-sized summaries.

---

## Quick Start

### 1. Get your API keys

- **Langfuse Cloud:** [cloud.langfuse.com](https://cloud.langfuse.com) &rarr; Settings &rarr; API Keys
- **Self-hosted:** Your Langfuse instance &rarr; Settings &rarr; API Keys. Set `LANGFUSE_HOST` to your instance URL (e.g., `https://langfuse.yourcompany.com`)

### 2. Add the MCP server

#### Claude Code

```bash
claude mcp add \
  -e LANGFUSE_PUBLIC_KEY=pk-lf-... \
  -e LANGFUSE_SECRET_KEY=sk-lf-... \
  -e LANGFUSE_HOST=https://cloud.langfuse.com \
  --scope project \
  langfuse-mcp -- uvx langfuse-mcp
```

#### Codex CLI

```bash
codex mcp add langfuse-mcp \
  --env LANGFUSE_PUBLIC_KEY=pk-lf-... \
  --env LANGFUSE_SECRET_KEY=sk-lf-... \
  --env LANGFUSE_HOST=https://cloud.langfuse.com \
  -- uvx langfuse-mcp
```

#### Cursor

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "langfuse-mcp": {
      "command": "uvx",
      "args": ["langfuse-mcp"],
      "env": {
        "LANGFUSE_PUBLIC_KEY": "pk-lf-...",
        "LANGFUSE_SECRET_KEY": "sk-lf-...",
        "LANGFUSE_HOST": "https://cloud.langfuse.com"
      }
    }
  }
}
```

### 3. Verify

Restart your CLI, then test with `/mcp` (Claude Code) or `codex mcp list` (Codex).

### Manual install (alternative to uvx)

```bash
pip install langfuse-mcp
langfuse-mcp serve
```

---

## Configuration

| Env Variable | Default | Description |
|---|---|---|
| `LANGFUSE_PUBLIC_KEY` | *(required)* | Langfuse public API key |
| `LANGFUSE_SECRET_KEY` | *(required)* | Langfuse secret API key |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse instance URL (cloud or self-hosted) |
| `LANGFUSE_INTERNAL_DOMAINS` | `""` | Comma-separated internal domains to exclude from analytics (e.g., `mycompany.com,test.com`). Applies when using `group_by='domain'`. |
| `LANGFUSE_MCP_READ_ONLY` | `false` | Disable write operations (`score_traces`, `create_dataset`, etc.) |
| `LANGFUSE_PAGE_LIMIT` | `100` | Traces per API page |

---

## Tools

### Analytics (9 tools)

Tools that compute insights server-side and return compact summaries. These go beyond raw data access — they aggregate, detect patterns, and compute statistics so the LLM can reason over results without hitting context window limits.

| Tool | Description | Key Parameters |
|---|---|---|
| `aggregate_by_group` | Aggregate trace metrics by user group. Returns per-group: trace count, unique sessions, unique users, accuracy rate, average latency, total cost. | `group_by` (name/userId/domain/tag), `time_range`, `top_n`, `exclude_internal` |
| `compute_accuracy` | Compute accuracy from feedback scores. Accuracy = correct / (correct + incorrect). Supports grouping and time bucketing for trend analysis. | `group_by`, `bucket_by` (week/day), `score_name`, `time_range` |
| `detect_failures` | Detect LLM output quality failures using pattern matching ("unable to", "I can't", etc.) and negative feedback scores. NOT Python exceptions — use `find_exceptions` for those. | `group_by`, `include_examples`, `max_examples`, `time_range` |
| `compute_token_percentiles` | Compute token usage percentiles (TP50/TP90/TP95/TP99) at trace level. Fetches generation observations for accurate per-trace token counts. | `group_by`, `percentiles`, `time_range` |
| `detect_context_breaches` | Scan for traces where any single generation exceeds a token threshold. Catches context window overflow causing degraded LLM performance or silent truncation. | `threshold` (default 256000), `check_per_generation`, `time_range` |
| `analyze_sessions` | Analyze multi-turn session behavior. Returns session count, depth distribution (single vs multi-turn), engagement metrics, and session-level cost/latency. | `group_by`, `time_range` |
| `estimate_costs` | Compute cost breakdown using Langfuse's built-in `totalCost` field (model-aware, computed by Langfuse). Groups by user, agent, or time bucket. | `group_by`, `bucket_by` (week/day), `time_range` |
| `analyze_latency` | Analyze latency distribution at trace level and optionally per LLM generation. Identifies which model is the bottleneck. | `group_by`, `percentiles`, `include_per_generation`, `time_range` |
| `score_traces` | Write scores back to Langfuse. Use after analysis to annotate traces with findings — tag failures for review, mark high-quality traces for dataset creation. | `trace_ids`, `score_name`, `score_value`, `comment` |

### Data Access (25 tools)

Full Langfuse API coverage for querying and managing your observability data.

#### Traces

| Tool | Description |
|---|---|
| `fetch_traces` | List traces with filters — user ID, name, tags, time range, ordering. Returns paginated results. |
| `fetch_trace` | Get a single trace by ID with full details including all observations (spans, generations, events). |

#### Observations

| Tool | Description |
|---|---|
| `fetch_observations` | List observations with filters — trace ID, type (GENERATION/SPAN/EVENT), name, time range. |
| `fetch_observation` | Get a single observation by ID. Returns input/output, token usage, model, latency, and cost. |

#### Sessions

| Tool | Description |
|---|---|
| `fetch_sessions` | List sessions with optional time filters. |
| `get_session_details` | Get full details of a session including all its traces. |
| `get_user_sessions` | Get sessions for a specific user. Fetches user's traces and extracts unique sessions. |

#### Errors

| Tool | Description |
|---|---|
| `find_exceptions` | Find observations with error status. For LLM output quality issues, use `detect_failures` instead. |
| `get_exception_details` | Get full error details for a trace — returns all observations with error status highlighted. |
| `get_error_count` | Get total error count within a time period. |

#### Scores

| Tool | Description |
|---|---|
| `fetch_scores` | List scores/evaluations with filters — trace ID, score name, time range. |

#### Prompts

| Tool | Description |
|---|---|
| `list_prompts` | List all prompts in the project with optional name filter. |
| `get_prompt` | Fetch a specific prompt by name, version, or label. |
| `create_text_prompt` | Create a new text prompt version with optional labels and model config. |
| `create_chat_prompt` | Create a new chat prompt version with message array and optional config. |
| `update_prompt_labels` | Update labels for a specific prompt version (e.g., promote to "production"). |

#### Datasets

| Tool | Description |
|---|---|
| `list_datasets` | List all datasets in the project. |
| `get_dataset` | Get metadata for a specific dataset. |
| `list_dataset_items` | List items in a dataset with pagination. |
| `get_dataset_item` | Get a single dataset item by ID. |
| `create_dataset` | Create a new dataset with optional description and metadata. |
| `create_dataset_item` | Create or upsert a dataset item. Supports linking to source traces. |
| `delete_dataset_item` | Delete a dataset item by ID. |

#### Schema

| Tool | Description |
|---|---|
| `get_data_schema` | Get the data schema for the Langfuse project — available fields and types for traces, observations, scores, sessions. |

---

## Sample Questions

Once connected, ask your AI assistant questions like these:

### Agent & Pipeline Health
- "Which agents failed the most this week?"
- "What's the failure rate by agent name?"
- "Which agent has the worst accuracy?"
- "Show me the top 5 agents by trace volume"
- "Are any agents consistently slower than others?"
- "Compare all agents by accuracy, latency, and cost"

### Accuracy & Quality
- "What's our overall accuracy this week?"
- "What's the accuracy trend by week for the last 30 days?"
- "Compare accuracy across different agents"
- "What's the daily accuracy breakdown?"
- "Which users are getting the worst accuracy?"
- "What percentage of traces have feedback scores?"

### Failures & Debugging
- "Show me failure examples from today"
- "What are the most common failure patterns?"
- "Which users are seeing the most failures?"
- "What's the failure rate by agent?"
- "Are failures increasing or decreasing this week vs last?"
- "Show me traces where the LLM said 'unable to' or 'I can't'"

### Token Usage
- "What are the P90 and P99 token usage stats?"
- "Which agents consume the most tokens?"
- "Compare token usage across user groups"
- "Are any users hitting unusually high token counts?"

### Context Window Breaches
- "Are any generations exceeding the 128K context window?"
- "Show me traces with token usage above 200K per generation"
- "What's the breach severity distribution?"
- "Which users trigger the most context window breaches?"

### Sessions & Engagement
- "What's our multi-turn rate?"
- "How deep are sessions on average?"
- "Which users have the deepest sessions?"
- "How many single-turn vs multi-turn sessions this week?"
- "What's the average session cost?"

### Cost
- "How much are we spending per day this week?"
- "What's the weekly cost trend for the last 30 days?"
- "Which agent is the most expensive?"
- "Which users are costing the most?"
- "What's the average cost per trace?"

### Latency
- "What's the P95 latency?"
- "Is latency getting worse over time?"
- "Which model is the slowest?"
- "Compare latency across agents"
- "Show me per-generation latency breakdown by model"
- "Which users are experiencing the highest latency?"

### Annotation & Write-back
- "Score all failing traces from today with 'needs-review'"
- "Tag these trace IDs as 'high-quality' for dataset creation"
- "Mark trace abc-123 with a score of 0 and comment 'hallucinated output'"

### Lookups & Exploration
- "Fetch the last 20 traces"
- "Show me trace abc-123 with all its observations"
- "List sessions for user alice@example.com"
- "What errors happened in the last 24 hours?"
- "How many errors occurred this week?"
- "Show me all prompts in the project"
- "List all datasets"
- "What fields are available on traces and observations?"

---

## Grouping Options

The `group_by` parameter controls how traces are segmented in analytics tools:

| Value | What it groups by | When to use |
|---|---|---|
| `name` | Trace/agent name *(default)* | Compare performance across different agents or pipelines |
| `userId` | Per-user breakdown | Identify users with issues or high usage |
| `domain` | Email domain extracted from userId | Multi-tenant apps where users have email-based IDs (e.g., `user@acme.com` &rarr; `acme.com`) |
| `tag` | Trace tags | Compare across tagged environments, versions, or experiments |

---

## Selective Tool Loading

Load only the tool groups you need to reduce token overhead:

```bash
# Only load traces and analytics tools
LANGFUSE_TOOLS=traces,analytics langfuse-mcp serve

# Only load prompts and datasets
LANGFUSE_TOOLS=prompts,datasets langfuse-mcp serve

# In Claude Code
claude mcp add \
  -e LANGFUSE_PUBLIC_KEY=pk-lf-... \
  -e LANGFUSE_SECRET_KEY=sk-lf-... \
  -e LANGFUSE_TOOLS=traces,observations,analytics \
  langfuse-mcp -- uvx langfuse-mcp
```

Available groups:

| Group | Tools | Count |
|---|---|---|
| `traces` | `fetch_traces`, `fetch_trace` | 2 |
| `observations` | `fetch_observations`, `fetch_observation` | 2 |
| `sessions` | `fetch_sessions`, `get_session_details`, `get_user_sessions` | 3 |
| `errors` | `find_exceptions`, `get_exception_details`, `get_error_count` | 3 |
| `scores` | `fetch_scores` | 1 |
| `prompts` | `list_prompts`, `get_prompt`, `create_text_prompt`, `create_chat_prompt`, `update_prompt_labels` | 5 |
| `datasets` | `list_datasets`, `get_dataset`, `list_dataset_items`, `get_dataset_item`, `create_dataset`, `create_dataset_item`, `delete_dataset_item` | 7 |
| `schema` | `get_data_schema` | 1 |
| `analytics` | All 9 analytics tools | 9 |

If `LANGFUSE_TOOLS` is not set, all 34 tools are loaded.

---

## Read-Only Mode

Disable write operations (`score_traces`, `create_dataset`, `create_dataset_item`, `delete_dataset_item`, `create_text_prompt`, `create_chat_prompt`):

```bash
LANGFUSE_MCP_READ_ONLY=true
```

---

## How it Compares

### vs Official Langfuse MCP

| Capability | This server | Official Langfuse MCP |
|---|:---:|:---:|
| Traces & Observations | Yes | No |
| Sessions & Users | Yes | No |
| Exception Tracking | Yes | No |
| Prompt Management | Yes | Yes |
| Dataset Management | Yes | No |
| Score Write-back | Yes | No |
| Selective Tool Loading | Yes | No |
| Accuracy Metrics | Yes | No |
| Failure Detection | Yes | No |
| Token Percentiles | Yes | No |
| Cost Breakdown | Yes | No |
| Latency Analysis | Yes | No |
| Session Analytics | Yes | No |
| Context Breach Scanning | Yes | No |
| User Group Aggregation | Yes | No |

The official Langfuse MCP (5 tools) focuses on prompt management. This server provides full observability coverage plus 9 analytics tools.

### vs Other Langfuse MCP Implementations

| Capability | This server | Others |
|---|:---:|:---:|
| Data access (traces, observations, sessions) | Yes | Yes |
| Prompt & dataset management | Yes | Yes |
| Exception tracking | Yes | Yes |
| Selective tool loading | Yes | Yes |
| **Accuracy metrics** | **Yes** | No |
| **LLM failure detection** | **Yes** | No |
| **Token percentiles (TP50/P90/P95/P99)** | **Yes** | No |
| **Cost breakdown by group/time** | **Yes** | No |
| **Latency analysis with per-model breakdown** | **Yes** | No |
| **Multi-turn session analytics** | **Yes** | No |
| **Context window breach scanning** | **Yes** | No |
| **User/tenant group aggregation** | **Yes** | No |
| **Score write-back** | **Yes** | No |

Other implementations provide data access (fetching raw traces, observations, sessions). This server adds a **compute layer** — analytics tools that aggregate, detect patterns, and compute statistics server-side, returning compact summaries instead of raw API dumps.

### vs Platform-Embedded AI (Braintrust Loop, LangSmith Insights, Arize Alyx)

| Capability | This server | Platform AI assistants |
|---|:---:|:---:|
| Open source | Yes | No |
| Works with any MCP client | Yes | Platform-locked |
| Self-hosted Langfuse support | Yes | N/A |
| Real-time conversational | Yes | Varies (some batch-only) |
| Custom grouping/segmentation | Yes | Limited |
| Write-back to Langfuse | Yes | Platform-specific |
| Free | Yes | Paid tiers |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style guidelines, and areas for contribution.

## Security

See [SECURITY.md](SECURITY.md) for the security policy, vulnerability reporting, and API key handling.

## Code of Conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

MIT — see [LICENSE](LICENSE).
