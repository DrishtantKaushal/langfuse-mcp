"""Data access tools — full Langfuse API coverage."""
from __future__ import annotations
import asyncio
from typing import Any

# Maps group names to the tool functions that belong to them
_GROUP_MAP = {
    "traces": ["fetch_traces", "fetch_trace"],
    "observations": ["fetch_observations", "fetch_observation"],
    "sessions": ["fetch_sessions", "get_session_details", "get_user_sessions"],
    "errors": ["find_exceptions", "get_exception_details", "get_error_count"],
    "scores": ["fetch_scores", "list_scores_v2", "get_score_v2"],
    "prompts": ["list_prompts", "get_prompt", "get_prompt_unresolved", "create_text_prompt", "create_chat_prompt", "update_prompt_labels"],
    "datasets": ["list_datasets", "get_dataset", "list_dataset_items", "get_dataset_item", "create_dataset", "create_dataset_item", "delete_dataset_item"],
    "schema": ["get_data_schema"],
    "projects": ["list_projects"],
    "metrics": ["get_daily_metrics"],
    "users": ["list_users"],
    "comments": ["list_comments", "get_comment", "create_comment"],
    "models": ["list_models", "get_model"],
}

_PROJECT_DOC = "project: Langfuse project to query; uses the default if omitted. Call list_projects to see available names."


def register_data_access_tools(mcp, client, enabled_groups: set[str] | None = None):
    """Register data access tools. If enabled_groups is set, only register matching groups.

    Available groups: traces, observations, sessions, errors, scores, prompts,
    datasets, schema, projects.
    """

    def _enabled(group: str) -> bool:
        return enabled_groups is None or group in enabled_groups

    # -- Projects (discovery) --

    if _enabled("projects"):
        @mcp.tool()
        async def list_projects() -> dict:
            """List all Langfuse projects configured on this server.

            Returns the available project names and the default project (used when
            a tool call omits the `project` argument).
            """
            return {
                "projects": client.project_names(),
                "default": client.default_project,
            }

    # -- Traces --

    if _enabled("traces"):
        @mcp.tool()
        async def fetch_traces(
            limit: int = 20,
            offset: int = 0,
            user_id: str | None = None,
            name: str | None = None,
            tags: str | None = None,
            from_timestamp: str | None = None,
            to_timestamp: str | None = None,
            order_by: str | None = None,
            version: str | None = None,
            project: str | None = None,
        ) -> dict:
            """Fetch traces from Langfuse. Returns compact metadata (no input/output content).

            For analytical questions (accuracy, failures, costs), use the analytics tools instead.
            For user queries, use list_user_queries. For keyword search, use search_trace_content.
            Use fetch_trace(trace_id) to get full details for a specific trace.
            """
            c = client.for_project(project)
            params: dict[str, Any] = {"limit": limit, "offset": offset}
            if user_id:
                params["userId"] = user_id
            if name:
                params["name"] = name
            if tags:
                params["tags"] = tags.strip()
            if from_timestamp:
                params["fromTimestamp"] = from_timestamp
            if to_timestamp:
                params["toTimestamp"] = to_timestamp
            if order_by:
                params["orderBy"] = order_by
            if version:
                params["version"] = version
            result = await c.get_traces(**params)
            # Strip large fields to keep responses compact
            if "data" in result:
                for trace in result["data"]:
                    trace.pop("input", None)
                    trace.pop("output", None)
                    trace.pop("observations", None)
                    if "metadata" in trace and isinstance(trace["metadata"], dict) and len(str(trace["metadata"])) > 500:
                        trace["metadata"] = {"_truncated": True}
            return result

        @mcp.tool()
        async def fetch_trace(trace_id: str, project: str | None = None) -> dict:
            """Get FULL details for a single trace including input, output, and all observations.

            Use this when you have a trace ID and want to inspect the complete trace.
            For listing traces, use fetch_traces (returns compact metadata).
            """
            return await client.for_project(project).get_trace(trace_id)

        @mcp.tool()
        async def diff_traces(
            trace_id_a: str,
            trace_id_b: str,
            project: str | None = None,
        ) -> dict:
            """Compare two traces side-by-side. Fetches both in parallel and returns
            a summary of how their high-level fields differ (name, user, session,
            latency, cost, token usage, tags, model, status).

            Useful for answering 'why did trace X take longer than trace Y?' or
            'what's different between these two runs?'.
            """
            c = client.for_project(project)
            a, b = await asyncio.gather(c.get_trace(trace_id_a), c.get_trace(trace_id_b))

            def _summary(t: dict) -> dict:
                return {
                    "id": t.get("id"),
                    "name": t.get("name"),
                    "userId": t.get("userId"),
                    "sessionId": t.get("sessionId"),
                    "timestamp": t.get("timestamp"),
                    "latency_s": t.get("latency"),
                    "cost_usd": t.get("totalCost"),
                    "tags": t.get("tags"),
                    "release": t.get("release"),
                    "version": t.get("version"),
                }

            sa, sb = _summary(a), _summary(b)
            diff = {k: {"a": sa.get(k), "b": sb.get(k)} for k in sa if sa.get(k) != sb.get(k)}

            return {
                "a": sa,
                "b": sb,
                "differs": diff,
                "identical_fields": [k for k in sa if sa.get(k) == sb.get(k)],
            }

    # -- Observations --

    if _enabled("observations"):
        @mcp.tool()
        async def fetch_observations(
            limit: int = 50,
            page: int = 1,
            trace_id: str | None = None,
            observation_type: str | None = None,
            name: str | None = None,
            from_timestamp: str | None = None,
            to_timestamp: str | None = None,
            project: str | None = None,
        ) -> dict:
            """Fetch observations (spans, generations, events) with filters.

            Use observation_type='GENERATION' to get LLM calls specifically.
            Use trace_id to get all observations within a specific trace.
            """
            c = client.for_project(project)
            params: dict[str, Any] = {"limit": limit, "page": page}
            if trace_id:
                params["traceId"] = trace_id
            if observation_type:
                params["type"] = observation_type
            if name:
                params["name"] = name
            if from_timestamp:
                params["fromTimestamp"] = from_timestamp
            if to_timestamp:
                params["toTimestamp"] = to_timestamp
            return await c.get_observations(**params)

        @mcp.tool()
        async def fetch_observation(observation_id: str, project: str | None = None) -> dict:
            """Get a single observation by ID. Returns full details including
            input/output, token usage, model, latency, and cost."""
            return await client.for_project(project).get_observation(observation_id)

    # -- Sessions --

    if _enabled("sessions"):
        @mcp.tool()
        async def fetch_sessions(
            limit: int = 50,
            page: int = 1,
            from_timestamp: str | None = None,
            to_timestamp: str | None = None,
            project: str | None = None,
        ) -> dict:
            """List sessions with optional time filters."""
            c = client.for_project(project)
            params: dict[str, Any] = {"limit": limit, "page": page}
            if from_timestamp:
                params["fromTimestamp"] = from_timestamp
            if to_timestamp:
                params["toTimestamp"] = to_timestamp
            return await c.get_sessions(**params)

        @mcp.tool()
        async def get_session_details(session_id: str, project: str | None = None) -> dict:
            """Get full details of a session including all its traces."""
            return await client.for_project(project).get_session(session_id)

        @mcp.tool()
        async def get_user_sessions(
            user_id: str,
            limit: int = 50,
            from_timestamp: str | None = None,
            to_timestamp: str | None = None,
            project: str | None = None,
        ) -> dict:
            """Get sessions for a specific user. Fetches user's traces and
            extracts unique sessions to understand their interaction history."""
            c = client.for_project(project)
            params: dict[str, Any] = {}
            if from_timestamp:
                params["fromTimestamp"] = from_timestamp
            if to_timestamp:
                params["toTimestamp"] = to_timestamp
            traces = await c.fetch_all_traces(userId=user_id, max_pages=5, **params)
            session_ids = list({t.get("sessionId") for t in traces if t.get("sessionId")})
            tasks = [c.get_session(sid) for sid in session_ids[:limit]]
            results = await asyncio.gather(*tasks)
            sessions = [s for s in results if "error" not in s]
            return {"user_id": user_id, "session_count": len(sessions), "sessions": sessions}

    # -- Errors --

    if _enabled("errors"):
        @mcp.tool()
        async def find_exceptions(
            limit: int = 50,
            from_timestamp: str | None = None,
            to_timestamp: str | None = None,
            project: str | None = None,
        ) -> dict:
            """Find observations with error status. Use detect_failures for
            LLM output quality issues instead."""
            c = client.for_project(project)
            params: dict[str, Any] = {"limit": limit, "status": "ERROR"}
            if from_timestamp:
                params["fromTimestamp"] = from_timestamp
            if to_timestamp:
                params["toTimestamp"] = to_timestamp
            return await c.get_observations(**params)

        @mcp.tool()
        async def get_exception_details(trace_id: str, project: str | None = None) -> dict:
            """Get full exception/error details for a specific trace.
            Returns the trace with all observations, highlighting errors."""
            c = client.for_project(project)
            trace = await c.get_trace(trace_id)
            observations = await c.get_trace_observations(trace_id)
            errors = [o for o in observations if o.get("statusMessage") or o.get("level") == "ERROR"]
            return {
                "trace": trace,
                "total_observations": len(observations),
                "error_observations": errors,
                "error_count": len(errors),
            }

        @mcp.tool()
        async def get_error_count(
            from_timestamp: str | None = None,
            to_timestamp: str | None = None,
            project: str | None = None,
        ) -> dict:
            """Get total error count within a time period."""
            c = client.for_project(project)
            params: dict[str, Any] = {"status": "ERROR", "limit": 1}
            if from_timestamp:
                params["fromTimestamp"] = from_timestamp
            if to_timestamp:
                params["toTimestamp"] = to_timestamp
            result = await c.get_observations(**params)
            meta = result.get("meta", {})
            return {
                "error_count": meta.get("totalItems", 0),
                "period": {"from": from_timestamp, "to": to_timestamp},
            }

    # -- Scores --

    if _enabled("scores"):
        @mcp.tool()
        async def fetch_scores(
            limit: int = 50,
            page: int = 1,
            trace_id: str | None = None,
            name: str | None = None,
            from_timestamp: str | None = None,
            to_timestamp: str | None = None,
            project: str | None = None,
        ) -> dict:
            """Fetch scores/evaluations with optional filters."""
            c = client.for_project(project)
            params: dict[str, Any] = {"limit": limit, "page": page}
            if trace_id:
                params["traceId"] = trace_id
            if name:
                params["name"] = name
            if from_timestamp:
                params["fromTimestamp"] = from_timestamp
            if to_timestamp:
                params["toTimestamp"] = to_timestamp
            return await c.get_scores(**params)

        @mcp.tool()
        async def list_scores_v2(
            limit: int = 50,
            page: int = 1,
            name: str | None = None,
            user_id: str | None = None,
            trace_id: str | None = None,
            observation_id: str | None = None,
            session_id: str | None = None,
            dataset_run_id: str | None = None,
            queue_id: str | None = None,
            config_id: str | None = None,
            source: str | None = None,
            data_type: str | None = None,
            environment: str | None = None,
            operator: str | None = None,
            value: float | None = None,
            from_timestamp: str | None = None,
            to_timestamp: str | None = None,
            trace_tags: str | None = None,
            score_ids: str | None = None,
            project: str | None = None,
        ) -> dict:
            """List scores using the v2 Scores API. Richer filters than fetch_scores.

            trace_tags / score_ids: comma-separated values.
            operator: comparator used with value (e.g. '>', '>=', '=', '<').
            """
            c = client.for_project(project)
            params: dict[str, Any] = {"limit": limit, "page": page}
            if name:
                params["name"] = name
            if user_id:
                params["userId"] = user_id
            if trace_id:
                params["traceId"] = trace_id
            if observation_id:
                params["observationId"] = observation_id
            if session_id:
                params["sessionId"] = session_id
            if dataset_run_id:
                params["datasetRunId"] = dataset_run_id
            if queue_id:
                params["queueId"] = queue_id
            if config_id:
                params["configId"] = config_id
            if source:
                params["source"] = source
            if data_type:
                params["dataType"] = data_type
            if environment:
                params["environment"] = environment
            if operator:
                params["operator"] = operator
            if value is not None:
                params["value"] = value
            if from_timestamp:
                params["fromTimestamp"] = from_timestamp
            if to_timestamp:
                params["toTimestamp"] = to_timestamp
            if trace_tags:
                params["traceTags"] = trace_tags
            if score_ids:
                params["scoreIds"] = score_ids
            return await c.get_scores_v2(**params)

        @mcp.tool()
        async def get_score_v2(score_id: str, project: str | None = None) -> dict:
            """Get a single score by ID via the v2 Scores API."""
            return await client.for_project(project).get_score_v2(score_id)

    # -- Prompts --

    if _enabled("prompts"):
        @mcp.tool()
        async def list_prompts(
            limit: int = 50, page: int = 1, name: str | None = None,
            project: str | None = None,
        ) -> dict:
            """List all prompts in the project."""
            c = client.for_project(project)
            params: dict[str, Any] = {"limit": limit, "page": page}
            if name:
                params["name"] = name
            return await c.get_prompts(**params)

        @mcp.tool()
        async def get_prompt(
            name: str, version: int | None = None, label: str | None = None,
            project: str | None = None,
        ) -> dict:
            """Fetch a specific prompt by name. Optionally specify version or label."""
            c = client.for_project(project)
            params: dict[str, Any] = {}
            if version is not None:
                params["version"] = version
            if label:
                params["label"] = label
            return await c.get_prompt(name, **params)

        @mcp.tool()
        async def get_prompt_unresolved(
            name: str,
            version: int | None = None,
            label: str | None = None,
            project: str | None = None,
        ) -> dict:
            """Fetch a prompt without resolving placeholders or linked dependencies.

            Use this for debugging prompt composition (seeing the raw template with
            `{{variable}}` placeholders intact). For production runtime fetches, use
            get_prompt which resolves by default.
            """
            c = client.for_project(project)
            params: dict[str, Any] = {"resolve": "false"}
            if version is not None:
                params["version"] = version
            if label:
                params["label"] = label
            return await c.get_prompt_v2(name, **params)

        @mcp.tool()
        async def create_text_prompt(
            name: str, prompt: str, labels: str | None = None, config: str | None = None,
            project: str | None = None,
        ) -> dict:
            """Create a new text prompt version. labels: comma-separated."""
            import json as _json
            c = client.for_project(project)
            data: dict[str, Any] = {"name": name, "prompt": prompt, "type": "text"}
            if labels:
                data["labels"] = [l.strip() for l in labels.split(",")]
            if config:
                data["config"] = _json.loads(config)
            return await c.create_prompt(data)

        @mcp.tool()
        async def create_chat_prompt(
            name: str, messages: str, labels: str | None = None, config: str | None = None,
            project: str | None = None,
        ) -> dict:
            """Create a new chat prompt version. messages: JSON string of [{role, content}]."""
            import json as _json
            c = client.for_project(project)
            data: dict[str, Any] = {"name": name, "prompt": _json.loads(messages), "type": "chat"}
            if labels:
                data["labels"] = [l.strip() for l in labels.split(",")]
            if config:
                data["config"] = _json.loads(config)
            return await c.create_prompt(data)

        @mcp.tool()
        async def update_prompt_labels(
            prompt_name: str, version: int, labels: str, project: str | None = None,
        ) -> dict:
            """Update labels for a specific prompt version. labels: comma-separated."""
            return await client.for_project(project).update_prompt_labels(
                prompt_name, version, [l.strip() for l in labels.split(",")]
            )

    # -- Datasets --

    if _enabled("datasets"):
        @mcp.tool()
        async def list_datasets(limit: int = 50, page: int = 1, project: str | None = None) -> dict:
            """List all datasets in the project."""
            return await client.for_project(project).get_datasets(limit=limit, page=page)

        @mcp.tool()
        async def get_dataset(dataset_name: str, project: str | None = None) -> dict:
            """Get metadata for a specific dataset."""
            return await client.for_project(project).get_dataset(dataset_name)

        @mcp.tool()
        async def list_dataset_items(
            dataset_name: str, limit: int = 50, page: int = 1, project: str | None = None,
        ) -> dict:
            """List items in a dataset."""
            return await client.for_project(project).get_dataset_items(
                dataset_name, limit=limit, page=page
            )

        @mcp.tool()
        async def get_dataset_item(item_id: str, project: str | None = None) -> dict:
            """Get a single dataset item by ID."""
            return await client.for_project(project).get_dataset_item(item_id)

        @mcp.tool()
        async def create_dataset(
            name: str, description: str | None = None, metadata: str | None = None,
            project: str | None = None,
        ) -> dict:
            """Create a new dataset. metadata: JSON string."""
            import json as _json
            c = client.for_project(project)
            data: dict[str, Any] = {"name": name}
            if description:
                data["description"] = description
            if metadata:
                data["metadata"] = _json.loads(metadata)
            return await c.create_dataset(data)

        @mcp.tool()
        async def create_dataset_item(
            dataset_name: str, input: str, expected_output: str | None = None,
            metadata: str | None = None, source_trace_id: str | None = None,
            source_observation_id: str | None = None, item_id: str | None = None,
            project: str | None = None,
        ) -> dict:
            """Create or upsert a dataset item. input/expected_output: JSON strings."""
            import json as _json
            c = client.for_project(project)
            data: dict[str, Any] = {"datasetName": dataset_name, "input": _json.loads(input)}
            if expected_output:
                data["expectedOutput"] = _json.loads(expected_output)
            if metadata:
                data["metadata"] = _json.loads(metadata)
            if source_trace_id:
                data["sourceTraceId"] = source_trace_id
            if source_observation_id:
                data["sourceObservationId"] = source_observation_id
            if item_id:
                data["id"] = item_id
            return await c.create_dataset_item(data)

        @mcp.tool()
        async def delete_dataset_item(item_id: str, project: str | None = None) -> dict:
            """Delete a dataset item by ID."""
            return await client.for_project(project).delete_dataset_item(item_id)

    # -- Metrics --

    if _enabled("metrics"):
        @mcp.tool()
        async def get_daily_metrics(
            from_timestamp: str | None = None,
            to_timestamp: str | None = None,
            user_id: str | None = None,
            tags: str | None = None,
            project: str | None = None,
        ) -> dict:
            """Fetch Langfuse's pre-aggregated daily metrics rollup.

            Returns per-day totals (trace count, cost, token usage) computed by
            Langfuse server-side. Faster than aggregating traces yourself when you
            want high-level trends over a long window.
            """
            c = client.for_project(project)
            params: dict[str, Any] = {}
            if from_timestamp:
                params["fromTimestamp"] = from_timestamp
            if to_timestamp:
                params["toTimestamp"] = to_timestamp
            if user_id:
                params["userId"] = user_id
            if tags:
                params["tags"] = tags
            return await c.get_daily_metrics(**params)

    # -- Users --

    if _enabled("users"):
        @mcp.tool()
        async def list_users(
            from_timestamp: str | None = None,
            to_timestamp: str | None = None,
            top_n: int = 20,
            project: str | None = None,
        ) -> dict:
            """List users in the project with per-user trace counts.

            Langfuse does not expose a dedicated /users endpoint — this queries the
            metrics API (grouping traces by userId) and returns the top users by
            trace count. Use fetch_traces(user_id=...) for a specific user's traces.

            If timestamps are omitted, defaults to the last 30 days.
            """
            from datetime import datetime, timedelta, timezone as _tz
            c = client.for_project(project)
            now = datetime.now(_tz.utc)
            query: dict[str, Any] = {
                "view": "traces",
                "dimensions": [{"field": "userId"}],
                "metrics": [{"measure": "count", "aggregation": "count"}],
                "filters": [],
                "fromTimestamp": from_timestamp or (now - timedelta(days=30)).isoformat(),
                "toTimestamp": to_timestamp or now.isoformat(),
            }
            result = await c.query_metrics(query)
            rows = result.get("data", []) if isinstance(result, dict) else []
            rows = [r for r in rows if r.get("userId")]
            rows.sort(key=lambda r: r.get("count_count", r.get("count", 0)) or 0, reverse=True)
            return {
                "total_users": len(rows),
                "users": rows[:top_n],
            }

    # -- Comments --

    if _enabled("comments"):
        @mcp.tool()
        async def list_comments(
            object_type: str | None = None,
            object_id: str | None = None,
            author_user_id: str | None = None,
            page: int = 1,
            limit: int = 50,
            project: str | None = None,
        ) -> dict:
            """List comments attached to traces, observations, sessions, or prompts.

            object_type: 'trace' | 'observation' | 'session' | 'prompt'.
            object_id requires object_type to also be set.
            """
            c = client.for_project(project)
            params: dict[str, Any] = {"page": page, "limit": limit}
            if object_type:
                params["objectType"] = object_type
            if object_id:
                params["objectId"] = object_id
            if author_user_id:
                params["authorUserId"] = author_user_id
            return await c.get_comments(**params)

        @mcp.tool()
        async def get_comment(comment_id: str, project: str | None = None) -> dict:
            """Get a single comment by ID."""
            return await client.for_project(project).get_comment(comment_id)

        @mcp.tool()
        async def create_comment(
            project_id: str,
            object_type: str,
            object_id: str,
            content: str,
            author_user_id: str | None = None,
            project: str | None = None,
        ) -> dict:
            """Create a comment on a trace, observation, session, or prompt.

            project_id: the Langfuse project ID (different from the MCP `project`
              argument — find it in your Langfuse dashboard URL).
            object_type: 'trace' | 'observation' | 'session' | 'prompt'.
            content: markdown body, up to 5000 characters.
            """
            c = client.for_project(project)
            data: dict[str, Any] = {
                "projectId": project_id,
                "objectType": object_type,
                "objectId": object_id,
                "content": content,
            }
            if author_user_id:
                data["authorUserId"] = author_user_id
            return await c.create_comment(data)

    # -- Models --

    if _enabled("models"):
        @mcp.tool()
        async def list_models(
            page: int = 1, limit: int = 50, project: str | None = None,
        ) -> dict:
            """List model definitions in the Langfuse models registry.

            Returns both Langfuse-managed models and any custom pricing/tokenizer
            configs the project has added.
            """
            return await client.for_project(project).get_models(page=page, limit=limit)

        @mcp.tool()
        async def get_model(model_id: str, project: str | None = None) -> dict:
            """Get a single model definition by ID, including pricing and tokenizer config."""
            return await client.for_project(project).get_model(model_id)

    # -- Schema --

    if _enabled("schema"):
        @mcp.tool()
        async def get_data_schema() -> dict:
            """Get the data schema for the Langfuse project. Useful for understanding
            available fields and data types."""
            return {
                "trace_fields": [
                    "id", "name", "userId", "sessionId", "timestamp",
                    "input", "output", "metadata", "tags", "release",
                    "version", "totalCost", "latency", "observations",
                ],
                "observation_types": ["GENERATION", "SPAN", "EVENT"],
                "observation_fields": [
                    "id", "traceId", "type", "name", "startTime", "endTime",
                    "model", "input", "output", "usage", "metadata",
                    "statusMessage", "level", "completionStartTime",
                ],
                "score_fields": ["id", "traceId", "name", "value", "source", "observationId"],
                "session_fields": ["id", "createdAt", "projectId"],
            }
