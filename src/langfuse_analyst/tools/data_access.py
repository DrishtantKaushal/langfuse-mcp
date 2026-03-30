"""Data access tools — full Langfuse API coverage."""
from __future__ import annotations
from typing import Any


def register_data_access_tools(mcp, client):
    """Register all data access tools on the FastMCP server."""

    # -- Traces --

    @mcp.tool()
    def fetch_traces(
        limit: int = 50,
        offset: int = 0,
        user_id: str | None = None,
        name: str | None = None,
        tags: str | None = None,
        from_timestamp: str | None = None,
        to_timestamp: str | None = None,
        order_by: str | None = None,
        version: str | None = None,
    ) -> dict:
        """Fetch traces from Langfuse with optional filters.

        Use this to list recent traces, filter by user or tags, or search within a time range.
        tags: comma-separated if multiple. Timestamps in ISO 8601 format.
        """
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
        return client.get_traces(**params)

    @mcp.tool()
    def fetch_trace(trace_id: str) -> dict:
        """Get detailed information about a specific trace including all observations.

        Use this when you have a trace ID and need the full trace with its spans,
        generations, and events.
        """
        return client.get_trace(trace_id)

    # -- Observations --

    @mcp.tool()
    def fetch_observations(
        limit: int = 50,
        page: int = 1,
        trace_id: str | None = None,
        observation_type: str | None = None,
        name: str | None = None,
        from_timestamp: str | None = None,
        to_timestamp: str | None = None,
    ) -> dict:
        """Fetch observations (spans, generations, events) with filters.

        Use observation_type='GENERATION' to get LLM calls specifically.
        Use trace_id to get all observations within a specific trace.
        """
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
        return client.get_observations(**params)

    @mcp.tool()
    def fetch_observation(observation_id: str) -> dict:
        """Get a single observation by ID. Returns full details including
        input/output, token usage, model, latency, and cost."""
        return client.get_observation(observation_id)

    # -- Sessions --

    @mcp.tool()
    def fetch_sessions(
        limit: int = 50,
        page: int = 1,
        from_timestamp: str | None = None,
        to_timestamp: str | None = None,
    ) -> dict:
        """List sessions with optional time filters."""
        params: dict[str, Any] = {"limit": limit, "page": page}
        if from_timestamp:
            params["fromTimestamp"] = from_timestamp
        if to_timestamp:
            params["toTimestamp"] = to_timestamp
        return client.get_sessions(**params)

    @mcp.tool()
    def get_session_details(session_id: str) -> dict:
        """Get full details of a session including all its traces."""
        return client.get_session(session_id)

    @mcp.tool()
    def get_user_sessions(
        user_id: str,
        limit: int = 50,
        from_timestamp: str | None = None,
        to_timestamp: str | None = None,
    ) -> dict:
        """Get sessions for a specific user. Fetches user's traces and
        extracts unique sessions to understand their interaction history."""
        params: dict[str, Any] = {}
        if from_timestamp:
            params["fromTimestamp"] = from_timestamp
        if to_timestamp:
            params["toTimestamp"] = to_timestamp
        traces = client.fetch_all_traces(userId=user_id, max_pages=5, **params)
        session_ids = list({t.get("sessionId") for t in traces if t.get("sessionId")})
        sessions = []
        for sid in session_ids[:limit]:
            s = client.get_session(sid)
            if "error" not in s:
                sessions.append(s)
        return {"user_id": user_id, "session_count": len(sessions), "sessions": sessions}

    # -- Errors --

    @mcp.tool()
    def find_exceptions(
        limit: int = 50,
        from_timestamp: str | None = None,
        to_timestamp: str | None = None,
    ) -> dict:
        """Find observations with error status. Use detect_failures for
        LLM output quality issues instead."""
        params: dict[str, Any] = {"limit": limit, "status": "ERROR"}
        if from_timestamp:
            params["fromTimestamp"] = from_timestamp
        if to_timestamp:
            params["toTimestamp"] = to_timestamp
        return client.get_observations(**params)

    @mcp.tool()
    def get_exception_details(trace_id: str) -> dict:
        """Get full exception/error details for a specific trace.
        Returns the trace with all observations, highlighting errors."""
        trace = client.get_trace(trace_id)
        observations = client.get_trace_observations(trace_id)
        errors = [o for o in observations if o.get("statusMessage") or o.get("level") == "ERROR"]
        return {
            "trace": trace,
            "total_observations": len(observations),
            "error_observations": errors,
            "error_count": len(errors),
        }

    @mcp.tool()
    def get_error_count(
        from_timestamp: str | None = None,
        to_timestamp: str | None = None,
    ) -> dict:
        """Get total error count within a time period."""
        params: dict[str, Any] = {"status": "ERROR", "limit": 1}
        if from_timestamp:
            params["fromTimestamp"] = from_timestamp
        if to_timestamp:
            params["toTimestamp"] = to_timestamp
        result = client.get_observations(**params)
        meta = result.get("meta", {})
        return {
            "error_count": meta.get("totalItems", 0),
            "period": {"from": from_timestamp, "to": to_timestamp},
        }

    # -- Scores --

    @mcp.tool()
    def fetch_scores(
        limit: int = 50,
        page: int = 1,
        trace_id: str | None = None,
        name: str | None = None,
        from_timestamp: str | None = None,
        to_timestamp: str | None = None,
    ) -> dict:
        """Fetch scores/evaluations with optional filters."""
        params: dict[str, Any] = {"limit": limit, "page": page}
        if trace_id:
            params["traceId"] = trace_id
        if name:
            params["name"] = name
        if from_timestamp:
            params["fromTimestamp"] = from_timestamp
        if to_timestamp:
            params["toTimestamp"] = to_timestamp
        return client.get_scores(**params)

    # -- Prompts --

    @mcp.tool()
    def list_prompts(limit: int = 50, page: int = 1, name: str | None = None) -> dict:
        """List all prompts in the project."""
        params: dict[str, Any] = {"limit": limit, "page": page}
        if name:
            params["name"] = name
        return client.get_prompts(**params)

    @mcp.tool()
    def get_prompt(name: str, version: int | None = None, label: str | None = None) -> dict:
        """Fetch a specific prompt by name. Optionally specify version or label."""
        params: dict[str, Any] = {}
        if version is not None:
            params["version"] = version
        if label:
            params["label"] = label
        return client.get_prompt(name, **params)

    @mcp.tool()
    def create_text_prompt(
        name: str, prompt: str, labels: str | None = None, config: str | None = None,
    ) -> dict:
        """Create a new text prompt version. labels: comma-separated."""
        import json as _json
        data: dict[str, Any] = {"name": name, "prompt": prompt, "type": "text"}
        if labels:
            data["labels"] = [l.strip() for l in labels.split(",")]
        if config:
            data["config"] = _json.loads(config)
        return client.create_prompt(data)

    @mcp.tool()
    def create_chat_prompt(
        name: str, messages: str, labels: str | None = None, config: str | None = None,
    ) -> dict:
        """Create a new chat prompt version. messages: JSON string of [{role, content}]."""
        import json as _json
        data: dict[str, Any] = {"name": name, "prompt": _json.loads(messages), "type": "chat"}
        if labels:
            data["labels"] = [l.strip() for l in labels.split(",")]
        if config:
            data["config"] = _json.loads(config)
        return client.create_prompt(data)

    @mcp.tool()
    def update_prompt_labels(prompt_name: str, version: int, labels: str) -> dict:
        """Update labels for a specific prompt version. labels: comma-separated."""
        return client.update_prompt_labels(prompt_name, version, [l.strip() for l in labels.split(",")])

    # -- Datasets --

    @mcp.tool()
    def list_datasets(limit: int = 50, page: int = 1) -> dict:
        """List all datasets in the project."""
        return client.get_datasets(limit=limit, page=page)

    @mcp.tool()
    def get_dataset(dataset_name: str) -> dict:
        """Get metadata for a specific dataset."""
        return client.get_dataset(dataset_name)

    @mcp.tool()
    def list_dataset_items(dataset_name: str, limit: int = 50, page: int = 1) -> dict:
        """List items in a dataset."""
        return client.get_dataset_items(dataset_name, limit=limit, page=page)

    @mcp.tool()
    def get_dataset_item(item_id: str) -> dict:
        """Get a single dataset item by ID."""
        return client.get_dataset_item(item_id)

    @mcp.tool()
    def create_dataset(name: str, description: str | None = None, metadata: str | None = None) -> dict:
        """Create a new dataset. metadata: JSON string."""
        import json as _json
        data: dict[str, Any] = {"name": name}
        if description:
            data["description"] = description
        if metadata:
            data["metadata"] = _json.loads(metadata)
        return client.create_dataset(data)

    @mcp.tool()
    def create_dataset_item(
        dataset_name: str, input: str, expected_output: str | None = None,
        metadata: str | None = None, source_trace_id: str | None = None,
        source_observation_id: str | None = None, item_id: str | None = None,
    ) -> dict:
        """Create or upsert a dataset item. input/expected_output: JSON strings."""
        import json as _json
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
        return client.create_dataset_item(data)

    @mcp.tool()
    def delete_dataset_item(item_id: str) -> dict:
        """Delete a dataset item by ID."""
        return client.delete_dataset_item(item_id)

    # -- Schema --

    @mcp.tool()
    def get_data_schema() -> dict:
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
