"""Analytics tools — token percentiles, accuracy, failures, latency, costs, sessions, breaches."""
from __future__ import annotations
import asyncio
import re
from collections import defaultdict
from datetime import datetime, timezone

FAILURE_PATTERNS = [
    r"(?i)i can'?t",
    r"(?i)unable to",
    r"(?i)no data (found|available)",
    r"(?i)error occurred",
    r"(?i)don'?t have access",
    r"(?i)couldn'?t (find|retrieve|fetch|get)",
    r"(?i)unfortunately",
    r"(?i)i'?m (sorry|afraid)",
    r"(?i)not (able|possible) to",
    r"(?i)failed to",
]


def _extract_output_text(trace: dict) -> str:
    output = trace.get("output")
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        for key in ("content", "response", "answer", "text", "message"):
            if key in output:
                return str(output[key])
        return str(output)
    if isinstance(output, list) and output:
        return str(output[0])
    return ""


def _extract_input_text(trace: dict) -> str:
    inp = trace.get("input")
    if isinstance(inp, str):
        return inp
    if isinstance(inp, dict):
        for key in ("user_query", "query", "question", "message", "content"):
            if key in inp:
                return str(inp[key])
        msgs = inp.get("messages", [])
        if msgs:
            for m in reversed(msgs):
                if isinstance(m, dict) and m.get("role") == "user":
                    return str(m.get("content", ""))
        return str(inp)
    if isinstance(inp, list) and inp:
        for m in reversed(inp):
            if isinstance(m, dict) and m.get("role") == "user":
                return str(m.get("content", ""))
        return str(inp[0])
    return ""


def _resolve_time_range(client, time_range):
    """Resolve time_range: use config default if not explicitly set."""
    return time_range if time_range else client.config.default_time_range


async def _fetch_traces_for_range(client, time_range, start_date, end_date, tags, user_id,
                             max_pages=10, domain=None):
    """Fetch traces for a time range. Default 10 pages (1000 traces) for fast analytics.
    If domain is set, post-filters traces to only include users from that domain."""
    time_range = _resolve_time_range(client, time_range)
    start, end = client.resolve_time_range(time_range, start_date, end_date)
    params = {
        "fromTimestamp": start.isoformat(),
        "toTimestamp": end.isoformat(),
        "max_pages": max_pages,
    }
    if tags:
        params["tags"] = tags
    if user_id:
        params["userId"] = user_id
    traces = await client.fetch_all_traces(**params)
    if domain:
        domain_lower = domain.lower()
        traces = [t for t in traces if (client.extract_domain(t.get("userId")) or "").lower() == domain_lower]
    return traces


async def _fetch_traces_and_scores(client, time_range, start_date, end_date, tags,
                                    max_trace_pages=10, max_score_pages=10):
    """Fetch traces and scores in parallel. Returns (traces, score_map)."""
    time_range = _resolve_time_range(client, time_range)
    start, end = client.resolve_time_range(time_range, start_date, end_date)
    ts_params = {
        "fromTimestamp": start.isoformat(),
        "toTimestamp": end.isoformat(),
    }
    if tags:
        ts_params["tags"] = tags

    traces_coro = client.fetch_all_traces(max_pages=max_trace_pages, **ts_params)
    scores_coro = client.fetch_all_scores(
        fromTimestamp=ts_params["fromTimestamp"],
        toTimestamp=ts_params["toTimestamp"],
        max_pages=max_score_pages,
    )
    traces, scores = await asyncio.gather(traces_coro, scores_coro)
    score_map = {s.get("traceId", ""): float(s["value"]) for s in scores if s.get("value") is not None}
    return traces, score_map


def register_analytics_tools(mcp, client):
    """Register all analytics tools on the FastMCP server."""

    @mcp.tool()
    async def aggregate_by_group(
        time_range: str = "",
        start_date: str | None = None,
        end_date: str | None = None,
        group_by: str = "name",
        tags: str | None = None,
        exclude_internal: bool = False,
        top_n: int = 20,
    ) -> dict:
        """Aggregate trace metrics by user group.

        Returns per-group: trace count, unique sessions, unique users,
        accuracy rate, average latency, total cost. Sorted by trace count.

        group_by options:
        - 'name': trace/agent name (default — works for everyone)
        - 'userId': per-user breakdown
        - 'domain': extracts domain from email-based user IDs (e.g. user@acme.com → acme.com)
        - 'tag': groups by trace tags

        Set exclude_internal=true and LANGFUSE_INTERNAL_DOMAINS env var
        to filter out internal team users (only relevant with group_by='domain').
        """
        # Fetch traces and scores in parallel
        traces, trace_scores = await _fetch_traces_and_scores(
            client, time_range, start_date, end_date, tags,
        )

        groups: dict[str, dict] = defaultdict(lambda: {
            "traces": 0, "sessions": set(), "users": set(),
            "correct": 0, "incorrect": 0, "unrated": 0,
            "total_cost": 0.0, "total_latency": 0.0, "latency_count": 0,
        })

        def _group_key(t):
            if group_by == "domain":
                k = client.extract_domain(t.get("userId"))
                if not k or (exclude_internal and client.is_internal(k)):
                    return None
                return k
            elif group_by == "name":
                return t.get("name") or "unknown"
            elif group_by == "userId":
                return t.get("userId") or "unknown"
            elif group_by == "tag":
                return ",".join(t.get("tags", [])) or "untagged"
            return str(t.get(group_by, "unknown"))

        for t in traces:
            key = _group_key(t)
            if key is None:
                continue
            g = groups[key]
            g["traces"] += 1
            if t.get("sessionId"):
                g["sessions"].add(t["sessionId"])
            if t.get("userId"):
                g["users"].add(t["userId"])
            cost = t.get("totalCost")
            if cost:
                g["total_cost"] += float(cost)
            latency = t.get("latency")
            if latency:
                g["total_latency"] += float(latency)
                g["latency_count"] += 1

            # Apply score if available
            score = trace_scores.get(t.get("id", ""))
            if score is not None:
                if score >= 0.5:
                    g["correct"] += 1
                else:
                    g["incorrect"] += 1

        result = []
        for key, g in groups.items():
            rated = g["correct"] + g["incorrect"]
            result.append({
                "group": key,
                "traces": g["traces"],
                "sessions": len(g["sessions"]),
                "users": len(g["users"]),
                "accuracy_pct": round(100 * g["correct"] / rated, 1) if rated > 0 else None,
                "rated_traces": rated,
                "avg_latency_s": round(g["total_latency"] / g["latency_count"], 2) if g["latency_count"] > 0 else None,
                "total_cost_usd": round(g["total_cost"], 4),
            })
        result.sort(key=lambda x: x["traces"], reverse=True)

        return {
            "group_by": group_by,
            "total_groups": len(result),
            "total_traces": sum(r["traces"] for r in result),
            "groups": result[:top_n],
        }

    @mcp.tool()
    async def compute_accuracy(
        time_range: str = "",
        start_date: str | None = None,
        end_date: str | None = None,
        group_by: str | None = None,
        tags: str | None = None,
        bucket_by: str | None = None,
        score_name: str | None = None,
    ) -> dict:
        """Compute accuracy from feedback scores. Accuracy = correct / (correct + incorrect).

        group_by: 'domain', 'name', 'userId'. bucket_by: 'week', 'day' for trends.
        score_name: filter to a specific score (default: all scores).
        """
        traces, trace_scores = await _fetch_traces_and_scores(
            client, time_range, start_date, end_date, tags,
        )
        trace_map = {t["id"]: t for t in traces}

        buckets: dict[str, dict] = defaultdict(lambda: {"correct": 0, "incorrect": 0, "total": 0})

        for trace_id, score in trace_scores.items():
            trace = trace_map.get(trace_id)
            if not trace:
                continue
            if group_by == "domain":
                key = client.extract_domain(trace.get("userId")) or "unknown"
            elif group_by:
                key = str(trace.get(group_by, "unknown"))
            elif bucket_by == "week":
                ts = trace.get("timestamp", "")
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    key = f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"
                except Exception:
                    key = "unknown"
            elif bucket_by == "day":
                key = trace.get("timestamp", "")[:10] or "unknown"
            else:
                key = "overall"

            b = buckets[key]
            b["total"] += 1
            if score >= 0.5:
                b["correct"] += 1
            else:
                b["incorrect"] += 1

        result = []
        for key, b in sorted(buckets.items()):
            result.append({
                "bucket": key,
                "correct": b["correct"],
                "incorrect": b["incorrect"],
                "total": b["total"],
                "accuracy_pct": round(100 * b["correct"] / b["total"], 1) if b["total"] > 0 else None,
            })

        overall_correct = sum(b["correct"] for b in buckets.values())
        overall_total = sum(b["total"] for b in buckets.values())

        return {
            "overall_accuracy_pct": round(100 * overall_correct / overall_total, 1) if overall_total > 0 else None,
            "overall_rated": overall_total,
            "total_traces": len(traces),
            "score_coverage_pct": round(100 * overall_total / len(traces), 1) if traces else 0,
            "buckets": result,
        }

    @mcp.tool()
    async def detect_failures(
        time_range: str = "",
        start_date: str | None = None,
        end_date: str | None = None,
        tags: str | None = None,
        group_by: str | None = None,
        include_examples: bool = True,
        max_examples: int = 5,
    ) -> dict:
        """Detect LLM output failures using pattern matching and feedback scores.

        Finds traces where output contains failure signals ('unable to', 'I can\\'t',
        'error occurred', etc.) OR where feedback score = 0.

        This catches LLM quality failures, NOT Python exceptions.
        Use find_exceptions for code errors.
        """
        traces, trace_scores = await _fetch_traces_and_scores(
            client, time_range, start_date, end_date, tags,
        )
        negative_traces = {tid for tid, val in trace_scores.items() if val < 0.5}

        failures = []
        pattern_counts: dict[str, int] = defaultdict(int)
        group_failures: dict[str, int] = defaultdict(int)
        group_totals: dict[str, int] = defaultdict(int)

        for t in traces:
            gkey = "overall"
            if group_by == "domain":
                gkey = client.extract_domain(t.get("userId")) or "unknown"
            elif group_by:
                gkey = str(t.get(group_by, "unknown"))
            group_totals[gkey] += 1

            output_text = _extract_output_text(t)
            matched_patterns = []
            for pattern in FAILURE_PATTERNS:
                if re.search(pattern, output_text):
                    matched_patterns.append(pattern)
                    pattern_counts[pattern] += 1

            is_feedback_failure = t.get("id", "") in negative_traces

            if matched_patterns or is_feedback_failure:
                group_failures[gkey] += 1
                failures.append({
                    "trace_id": t.get("id"),
                    "user_id": t.get("userId"),
                    "session_id": t.get("sessionId"),
                    "timestamp": t.get("timestamp"),
                    "input_preview": _extract_input_text(t)[:200],
                    "output_preview": output_text[:300],
                    "matched_patterns": matched_patterns,
                    "feedback_failure": is_feedback_failure,
                })

        group_rates = []
        for gkey in sorted(group_totals.keys()):
            f_count = group_failures.get(gkey, 0)
            total = group_totals[gkey]
            group_rates.append({
                "group": gkey,
                "failures": f_count,
                "total": total,
                "failure_rate_pct": round(100 * f_count / total, 1) if total > 0 else 0,
            })
        group_rates.sort(key=lambda x: x["failures"], reverse=True)

        return {
            "total_traces": len(traces),
            "total_failures": len(failures),
            "failure_rate_pct": round(100 * len(failures) / len(traces), 1) if traces else 0,
            "pattern_match_failures": len([f for f in failures if f["matched_patterns"]]),
            "feedback_failures": len([f for f in failures if f["feedback_failure"]]),
            "top_patterns": sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True)[:5],
            "group_rates": group_rates if group_by else None,
            "examples": failures[:max_examples] if include_examples else None,
        }

    @mcp.tool()
    async def compute_token_percentiles(
        time_range: str = "",
        start_date: str | None = None,
        end_date: str | None = None,
        tags: str | None = None,
        group_by: str | None = None,
        percentiles: str = "50,90,95,99",
    ) -> dict:
        """Compute token usage percentiles (TP50/TP90/TP95/TP99) across traces.

        Fetches generation observations to get per-trace token counts.
        Optionally group by 'domain' or other trace attribute.

        NOTE: Fetches observations per trace — can be slow for large date ranges.
        Use last_7_days or smaller for real-time results.
        """
        import numpy as np

        traces = await _fetch_traces_for_range(client, time_range, start_date, end_date, tags, None, max_pages=20)
        pcts = [int(p.strip()) for p in percentiles.split(",")]

        grouped: dict[str, list[dict]] = defaultdict(list)
        for t in traces:
            if group_by == "domain":
                key = client.extract_domain(t.get("userId")) or "unknown"
            elif group_by:
                key = str(t.get(group_by, "unknown"))
            else:
                key = "all"
            grouped[key].append(t)

        # Fetch observations: try batch first, fall back to concurrent per-trace
        start, end = client.resolve_time_range(_resolve_time_range(client, time_range), start_date, end_date)
        obs_by_trace = await client.fetch_observations_by_time_range(
            from_timestamp=start.isoformat(),
            to_timestamp=end.isoformat(),
            obs_type="GENERATION",
            max_pages=30,
        )

        results = []
        for key, group_traces in grouped.items():
            input_tokens, output_tokens, total_tokens = [], [], []
            sample = group_traces[:200]

            # If batch returned empty (volume too high), fetch per-trace concurrently
            if not obs_by_trace:
                sample_ids = [t["id"] for t in sample]
                obs_by_trace_local = await client.fetch_observations_for_traces(sample_ids, obs_type="GENERATION")
            else:
                obs_by_trace_local = obs_by_trace

            for t in sample:
                observations = obs_by_trace_local.get(t["id"], [])
                trace_input, trace_output = 0, 0
                for obs in observations:
                    usage = obs.get("usage") or obs.get("usageDetails") or {}
                    inp = int(usage.get("input") or usage.get("inputTokens") or usage.get("promptTokens") or 0)
                    out = int(usage.get("output") or usage.get("outputTokens") or usage.get("completionTokens") or 0)
                    trace_input += inp
                    trace_output += out

                if trace_input > 0 or trace_output > 0:
                    input_tokens.append(trace_input)
                    output_tokens.append(trace_output)
                    total_tokens.append(trace_input + trace_output)

            if not total_tokens:
                results.append({"group": key, "traces_sampled": len(sample), "has_token_data": False})
                continue

            results.append({
                "group": key,
                "traces_sampled": len(sample),
                "traces_with_tokens": len(total_tokens),
                "input_tokens": {f"p{p}": int(np.percentile(input_tokens, p)) for p in pcts},
                "output_tokens": {f"p{p}": int(np.percentile(output_tokens, p)) for p in pcts},
                "total_tokens": {f"p{p}": int(np.percentile(total_tokens, p)) for p in pcts},
                "input_mean": int(np.mean(input_tokens)),
                "output_mean": int(np.mean(output_tokens)),
                "total_max": int(np.max(total_tokens)),
            })

        return {"group_by": group_by, "percentiles_computed": pcts, "groups": results}

    @mcp.tool()
    async def detect_context_breaches(
        time_range: str = "",
        start_date: str | None = None,
        end_date: str | None = None,
        tags: str | None = None,
        threshold: int = 256000,
        check_per_generation: bool = True,
    ) -> dict:
        """Scan for traces where token usage exceeds a context window threshold.

        Default: 256K tokens. Set check_per_generation=true to check if any
        SINGLE generation exceeds the limit (not just trace aggregate).
        Catches context window overflow causing degraded performance or truncation.
        """
        traces = await _fetch_traces_for_range(client, time_range, start_date, end_date, tags, None, max_pages=20)

        # Fetch observations: batch first, concurrent per-trace fallback
        start, end = client.resolve_time_range(_resolve_time_range(client, time_range), start_date, end_date)
        obs_by_trace = await client.fetch_observations_by_time_range(
            from_timestamp=start.isoformat(),
            to_timestamp=end.isoformat(),
            obs_type="GENERATION",
            max_pages=30,
        )
        # If batch empty (volume too high), fetch per-trace concurrently (sample 200)
        sample = traces[:200]
        if not obs_by_trace:
            obs_by_trace = await client.fetch_observations_for_traces(
                [t["id"] for t in sample], obs_type="GENERATION"
            )

        breaches, scanned = [], 0

        for t in sample:
            observations = obs_by_trace.get(t["id"], [])
            scanned += 1
            trace_total_input, max_gen_input = 0, 0
            breaching_gens = []

            for obs in observations:
                usage = obs.get("usage") or obs.get("usageDetails") or {}
                inp = int(usage.get("input") or usage.get("inputTokens") or usage.get("promptTokens") or 0)
                trace_total_input += inp
                max_gen_input = max(max_gen_input, inp)
                if check_per_generation and inp > threshold:
                    breaching_gens.append({
                        "observation_id": obs.get("id"),
                        "model": obs.get("model"),
                        "input_tokens": inp,
                        "pct_of_threshold": round(100 * inp / threshold, 1),
                    })

            has_breach = (check_per_generation and breaching_gens) or (not check_per_generation and trace_total_input > threshold)
            if has_breach:
                breaches.append({
                    "trace_id": t["id"],
                    "user_id": t.get("userId"),
                    "session_id": t.get("sessionId"),
                    "timestamp": t.get("timestamp"),
                    "trace_total_input_tokens": trace_total_input,
                    "max_generation_input_tokens": max_gen_input,
                    "pct_of_threshold": round(100 * max_gen_input / threshold, 1),
                    "breaching_generations": breaching_gens if check_per_generation else None,
                })

        severity = {"under_300K": 0, "300K_400K": 0, "400K_500K": 0, "500K_700K": 0, "over_700K": 0}
        for b in breaches:
            m = b["max_generation_input_tokens"]
            if m >= 700000: severity["over_700K"] += 1
            elif m >= 500000: severity["500K_700K"] += 1
            elif m >= 400000: severity["400K_500K"] += 1
            elif m >= 300000: severity["300K_400K"] += 1
            else: severity["under_300K"] += 1

        return {
            "threshold": threshold,
            "check_mode": "per_generation" if check_per_generation else "trace_aggregate",
            "traces_scanned": scanned,
            "breaches_found": len(breaches),
            "breach_rate_pct": round(100 * len(breaches) / scanned, 1) if scanned else 0,
            "severity_distribution": severity,
            "breaches": breaches[:20],
        }

    @mcp.tool()
    async def analyze_sessions(
        time_range: str = "",
        start_date: str | None = None,
        end_date: str | None = None,
        tags: str | None = None,
        group_by: str | None = None,
    ) -> dict:
        """Analyze multi-turn session behavior.

        Returns: session count, depth distribution (single vs multi-turn),
        average traces per session, session-level cost/latency,
        and engagement metrics.
        """
        import numpy as np

        traces = await _fetch_traces_for_range(client, time_range, start_date, end_date, tags, None)
        sessions: dict[str, list[dict]] = defaultdict(list)
        for t in traces:
            sid = t.get("sessionId")
            if sid:
                sessions[sid].append(t)

        depths, session_costs = [], []
        group_sessions: dict[str, dict] = defaultdict(lambda: {
            "sessions": 0, "single_turn": 0, "multi_turn": 0,
            "total_depth": 0, "total_cost": 0.0,
        })

        for sid, session_traces in sessions.items():
            depth = len(session_traces)
            depths.append(depth)
            cost = sum(float(t.get("totalCost") or 0) for t in session_traces)
            session_costs.append(cost)

            gkey = "all"
            if group_by == "domain":
                gkey = client.extract_domain(session_traces[0].get("userId")) or "unknown"
            elif group_by:
                gkey = str(session_traces[0].get(group_by, "unknown"))

            gs = group_sessions[gkey]
            gs["sessions"] += 1
            gs["total_depth"] += depth
            gs["total_cost"] += cost
            gs["single_turn" if depth == 1 else "multi_turn"] += 1

        depth_dist = {
            "1_turn": len([d for d in depths if d == 1]),
            "2_3_turns": len([d for d in depths if 2 <= d <= 3]),
            "4_10_turns": len([d for d in depths if 4 <= d <= 10]),
            "10_plus": len([d for d in depths if d > 10]),
        }

        group_results = []
        for gkey, gs in sorted(group_sessions.items()):
            group_results.append({
                "group": gkey,
                "sessions": gs["sessions"],
                "single_turn": gs["single_turn"],
                "multi_turn": gs["multi_turn"],
                "multi_turn_pct": round(100 * gs["multi_turn"] / gs["sessions"], 1) if gs["sessions"] else 0,
                "avg_depth": round(gs["total_depth"] / gs["sessions"], 1) if gs["sessions"] else 0,
                "total_cost_usd": round(gs["total_cost"], 4),
            })

        return {
            "total_sessions": len(sessions),
            "total_traces": len(traces),
            "traces_without_session": len([t for t in traces if not t.get("sessionId")]),
            "depth_distribution": depth_dist,
            "avg_depth": round(float(np.mean(depths)), 2) if depths else 0,
            "max_depth": max(depths) if depths else 0,
            "multi_turn_rate_pct": round(100 * len([d for d in depths if d > 1]) / len(depths), 1) if depths else 0,
            "avg_session_cost_usd": round(float(np.mean(session_costs)), 4) if session_costs else 0,
            "groups": group_results if group_by else None,
        }

    @mcp.tool()
    async def estimate_costs(
        time_range: str = "",
        start_date: str | None = None,
        end_date: str | None = None,
        tags: str | None = None,
        group_by: str | None = None,
        bucket_by: str | None = None,
    ) -> dict:
        """Compute cost breakdown from Langfuse totalCost field.

        Groups by 'domain', 'name', 'userId', or time buckets ('day', 'week').
        Returns: total cost, average per trace, per group breakdown.
        """
        traces = await _fetch_traces_for_range(client, time_range, start_date, end_date, tags, None)
        buckets: dict[str, dict] = defaultdict(lambda: {"cost": 0.0, "traces": 0, "latency_sum": 0.0})

        for t in traces:
            cost = float(t.get("totalCost") or 0)
            latency = float(t.get("latency") or 0)

            if group_by == "domain":
                key = client.extract_domain(t.get("userId")) or "unknown"
            elif group_by:
                key = str(t.get(group_by, "unknown"))
            elif bucket_by == "week":
                ts = t.get("timestamp", "")
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    key = f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"
                except Exception:
                    key = "unknown"
            elif bucket_by == "day":
                key = t.get("timestamp", "")[:10] or "unknown"
            else:
                key = "total"

            b = buckets[key]
            b["cost"] += cost
            b["traces"] += 1
            b["latency_sum"] += latency

        result = []
        for key, b in sorted(buckets.items()):
            result.append({
                "bucket": key,
                "total_cost_usd": round(b["cost"], 4),
                "traces": b["traces"],
                "avg_cost_usd": round(b["cost"] / b["traces"], 4) if b["traces"] else 0,
                "avg_latency_s": round(b["latency_sum"] / b["traces"], 2) if b["traces"] else 0,
            })

        total_cost = sum(b["cost"] for b in buckets.values())
        total_traces = sum(b["traces"] for b in buckets.values())

        return {
            "total_cost_usd": round(total_cost, 4),
            "total_traces": total_traces,
            "avg_cost_per_trace_usd": round(total_cost / total_traces, 4) if total_traces else 0,
            "breakdown": result,
        }

    @mcp.tool()
    async def analyze_latency(
        time_range: str = "",
        start_date: str | None = None,
        end_date: str | None = None,
        tags: str | None = None,
        group_by: str | None = None,
        percentiles: str = "50,90,95,99",
        include_per_generation: bool = False,
    ) -> dict:
        """Analyze latency distribution across traces and optionally per generation.

        Returns: latency percentiles (P50/P90/P95/P99), average, max.
        group_by: 'domain', 'name', 'model'.
        Set include_per_generation=true to also analyze per-LLM-call latency
        (slower, fetches observations). Identifies which model is the bottleneck.
        """
        import numpy as np

        traces = await _fetch_traces_for_range(client, time_range, start_date, end_date, tags, None)
        pcts = [int(p.strip()) for p in percentiles.split(",")]

        grouped: dict[str, list[float]] = defaultdict(list)
        for t in traces:
            latency = t.get("latency")
            if latency is None:
                continue
            if group_by == "domain":
                key = client.extract_domain(t.get("userId")) or "unknown"
            elif group_by:
                key = str(t.get(group_by, "unknown"))
            else:
                key = "all"
            grouped[key].append(float(latency))

        results = []
        for key, latencies in sorted(grouped.items()):
            if not latencies:
                continue
            arr = np.array(latencies)
            results.append({
                "group": key,
                "count": len(latencies),
                "mean_s": round(float(np.mean(arr)), 3),
                "min_s": round(float(np.min(arr)), 3),
                "max_s": round(float(np.max(arr)), 3),
                "percentiles": {f"p{p}": round(float(np.percentile(arr, p)), 3) for p in pcts},
            })

        gen_results = None
        if include_per_generation:
            # Fetch observations for sampled traces concurrently
            sample_traces = traces[:100]
            sample_ids = [t["id"] for t in sample_traces]
            obs_by_trace = await client.fetch_observations_for_traces(sample_ids, obs_type="GENERATION")

            gen_latency: dict[str, list[float]] = defaultdict(list)
            for t in sample_traces:
                observations = obs_by_trace.get(t["id"], [])
                for obs in observations:
                    st, et = obs.get("startTime"), obs.get("endTime")
                    model = obs.get("model") or "unknown"
                    if st and et:
                        try:
                            s = datetime.fromisoformat(st.replace("Z", "+00:00"))
                            e = datetime.fromisoformat(et.replace("Z", "+00:00"))
                            gen_latency[model].append((e - s).total_seconds())
                        except Exception:
                            pass

            if gen_latency:
                gen_results = []
                for model, lats in sorted(gen_latency.items()):
                    arr = np.array(lats)
                    gen_results.append({
                        "model": model,
                        "count": len(lats),
                        "mean_s": round(float(np.mean(arr)), 3),
                        "percentiles": {f"p{p}": round(float(np.percentile(arr, p)), 3) for p in pcts},
                    })

        all_lats = [l for lats in grouped.values() for l in lats]
        overall = {}
        if all_lats:
            arr = np.array(all_lats)
            overall = {
                "count": len(all_lats),
                "mean_s": round(float(np.mean(arr)), 3),
                "percentiles": {f"p{p}": round(float(np.percentile(arr, p)), 3) for p in pcts},
            }

        return {
            "overall": overall,
            "groups": results,
            "per_generation_by_model": gen_results,
            "traces_analyzed": len(traces),
            "traces_with_latency": len(all_lats),
        }

    @mcp.tool()
    async def list_user_queries(
        time_range: str = "",
        start_date: str | None = None,
        end_date: str | None = None,
        tags: str | None = None,
        user_id: str | None = None,
        domain: str | None = None,
        name: str | None = None,
        group_by: str | None = None,
        exclude_internal: bool = False,
        limit: int = 100,
    ) -> dict:
        """List user queries extracted from trace inputs.

        Use this to answer: 'What are merchants asking?', 'What queries came in today?',
        'What did users ask about?', 'Show star insurance queries'. Returns extracted
        query text with metadata.

        domain: filter by email domain (e.g. 'starinsurance.in'). Use this when the user
        asks about a company/org by name instead of a specific user email.
        group_by: 'name' (agent), 'userId', 'domain'. Set exclude_internal=true to
        filter internal team users.
        """
        traces = await _fetch_traces_for_range(
            client, time_range, start_date, end_date, tags, user_id, domain=domain,
        )

        # Apply name filter if provided
        if name:
            traces = [t for t in traces if t.get("name") == name]

        queries = []
        group_counts: dict[str, int] = defaultdict(int)

        for t in traces:
            if exclude_internal:
                user_domain = client.extract_domain(t.get("userId"))
                if client.is_internal(user_domain):
                    continue

            query_text = _extract_input_text(t)
            if not query_text:
                continue

            gkey = None
            if group_by == "domain":
                gkey = client.extract_domain(t.get("userId")) or "unknown"
            elif group_by == "name":
                gkey = t.get("name") or "unknown"
            elif group_by == "userId":
                gkey = t.get("userId") or "unknown"
            if gkey:
                group_counts[gkey] += 1

            queries.append({
                "trace_id": t.get("id"),
                "timestamp": t.get("timestamp"),
                "user_id": t.get("userId"),
                "agent": t.get("name"),
                "session_id": t.get("sessionId"),
                "query": query_text[:500],
            })

        queries.sort(key=lambda q: q["timestamp"] or "", reverse=True)
        queries = queries[:limit]

        result: dict = {
            "total_traces": len(traces),
            "queries_extracted": len(queries),
            "queries": queries,
        }
        if group_by:
            sorted_groups = sorted(group_counts.items(), key=lambda x: x[1], reverse=True)
            result["group_counts"] = [{"group": k, "count": v} for k, v in sorted_groups[:20]]
        return result

    @mcp.tool()
    async def find_slow_traces(
        time_range: str = "",
        start_date: str | None = None,
        end_date: str | None = None,
        tags: str | None = None,
        domain: str | None = None,
        threshold_seconds: float | None = None,
        top_n: int = 20,
        group_by: str | None = None,
    ) -> dict:
        """Find the slowest traces. Returns actual trace IDs and metadata.

        Use this to answer: 'Which traces were slowest?', 'Show me traces taking >30s',
        'What's causing high latency today?'.

        domain: filter by email domain (e.g. 'acme.com').
        If threshold_seconds is set, returns all traces above that threshold.
        Otherwise returns the top_n slowest traces.
        group_by: 'name' (agent), 'userId', 'domain'.
        """
        traces = await _fetch_traces_for_range(
            client, time_range, start_date, end_date, tags, None, domain=domain,
        )

        with_latency = []
        for t in traces:
            lat = t.get("latency")
            if lat is not None:
                with_latency.append((float(lat), t))

        with_latency.sort(key=lambda x: x[0], reverse=True)

        if threshold_seconds is not None:
            slow = [(lat, t) for lat, t in with_latency if lat >= threshold_seconds]
        else:
            slow = with_latency[:top_n]

        group_stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "total_lat": 0.0})

        results = []
        for lat, t in slow:
            query_preview = _extract_input_text(t)[:200]
            results.append({
                "trace_id": t.get("id"),
                "timestamp": t.get("timestamp"),
                "user_id": t.get("userId"),
                "agent": t.get("name"),
                "latency_s": round(lat, 2),
                "cost_usd": round(float(t.get("totalCost") or 0), 4),
                "query_preview": query_preview,
            })

            gkey = None
            if group_by == "domain":
                gkey = client.extract_domain(t.get("userId")) or "unknown"
            elif group_by == "name":
                gkey = t.get("name") or "unknown"
            elif group_by == "userId":
                gkey = t.get("userId") or "unknown"
            if gkey:
                gs = group_stats[gkey]
                gs["count"] += 1
                gs["total_lat"] += lat

        result: dict = {
            "total_traces": len(traces),
            "traces_with_latency": len(with_latency),
            "slow_traces_found": len(results),
            "threshold_seconds": threshold_seconds,
            "traces": results,
        }
        if group_by:
            sorted_groups = sorted(group_stats.items(), key=lambda x: x[1]["count"], reverse=True)
            result["group_breakdown"] = [
                {"group": k, "count": v["count"], "avg_latency_s": round(v["total_lat"] / v["count"], 2)}
                for k, v in sorted_groups
            ]
        return result

    @mcp.tool()
    async def search_trace_content(
        query: str,
        time_range: str = "",
        start_date: str | None = None,
        end_date: str | None = None,
        tags: str | None = None,
        domain: str | None = None,
        search_in: str = "both",
        limit: int = 50,
    ) -> dict:
        """Search trace inputs and outputs for keywords.

        Use this to answer: 'Find traces mentioning refund', 'Which queries asked about
        payment failures?', 'Show traces related to order ID X'.

        domain: filter by email domain (e.g. 'acme.com').
        search_in: 'input', 'output', or 'both' (default).
        query: keyword or phrase to search for (case-insensitive).
        """
        traces = await _fetch_traces_for_range(
            client, time_range, start_date, end_date, tags, None, domain=domain,
        )

        pattern = re.compile(re.escape(query), re.IGNORECASE)
        matches = []

        for t in traces:
            input_text = _extract_input_text(t) if search_in in ("input", "both") else ""
            output_text = _extract_output_text(t) if search_in in ("output", "both") else ""

            input_match = bool(pattern.search(input_text)) if input_text else False
            output_match = bool(pattern.search(output_text)) if output_text else False

            if input_match or output_match:
                matches.append({
                    "trace_id": t.get("id"),
                    "timestamp": t.get("timestamp"),
                    "user_id": t.get("userId"),
                    "agent": t.get("name"),
                    "matched_in": ("both" if input_match and output_match
                                   else "input" if input_match else "output"),
                    "input_preview": input_text[:300] if input_match else None,
                    "output_preview": output_text[:300] if output_match else None,
                })

            if len(matches) >= limit:
                break

        return {
            "query": query,
            "search_in": search_in,
            "total_traces_scanned": len(traces),
            "matches_found": len(matches),
            "matches": matches,
        }

    @mcp.tool()
    async def score_traces(
        trace_ids: str,
        score_name: str,
        score_value: float,
        comment: str | None = None,
    ) -> dict:
        """Write scores back to Langfuse traces. trace_ids: comma-separated.

        Use this after analysis to annotate traces with findings.
        Example: score failing traces with 'needs-review'.
        """
        ids = [tid.strip() for tid in trace_ids.split(",")]
        tasks = []
        for tid in ids:
            data: dict = {"traceId": tid, "name": score_name, "value": score_value}
            if comment:
                data["comment"] = comment
            tasks.append(client.create_score(data))
        results = await asyncio.gather(*tasks)

        return {"scored": len(ids), "score_name": score_name, "score_value": score_value, "results": [{"trace_id": tid, "result": r} for tid, r in zip(ids, results)]}
