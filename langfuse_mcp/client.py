"""Async Langfuse API client with caching, batch fetching, and rate limiting."""
import asyncio
import base64
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx
from cachetools import TTLCache

from .config import Config


class RateLimiter:
    """Token bucket rate limiter. RPM=0 means unlimited."""

    def __init__(self, rpm: int):
        self._rpm = rpm
        self._interval = 60.0 / rpm if rpm > 0 else 0
        self._last_request = 0.0

    async def acquire(self):
        if self._rpm <= 0:
            return
        now = time.monotonic()
        wait = self._interval - (now - self._last_request)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request = time.monotonic()

    def backoff(self):
        """Called on 429 — halve the RPM."""
        if self._rpm > 0:
            self._rpm = max(5, self._rpm // 2)
            self._interval = 60.0 / self._rpm


class LangfuseClient:
    """Async wrapper around the Langfuse REST API."""

    def __init__(self, config: Config):
        self.config = config
        self.base_url = f"{config.host}/api/public"
        auth = base64.b64encode(f"{config.public_key}:{config.secret_key}".encode()).decode()
        self.headers = {"Authorization": f"Basic {auth}"}
        self._http = httpx.AsyncClient(timeout=90, headers=self.headers)
        self._rate_limiter = RateLimiter(config.effective_rpm)
        self._semaphore = asyncio.Semaphore(config.concurrent_limit)
        self._cache = TTLCache(maxsize=config.cache_max_size, ttl=config.cache_ttl_seconds)
        self._cache_hist = TTLCache(maxsize=config.cache_max_size, ttl=config.cache_ttl_historical_seconds)

    def _cache_key(self, endpoint: str, params: dict) -> str:
        items = sorted((k, str(v)) for k, v in params.items())
        return f"{endpoint}|{'|'.join(f'{k}={v}' for k, v in items)}"

    def _is_historical(self, params: dict) -> bool:
        to_ts = params.get("toTimestamp")
        if not to_ts:
            return False
        try:
            today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            end = datetime.fromisoformat(str(to_ts).replace("Z", "+00:00"))
            return end < today
        except Exception:
            return False

    async def _get(self, endpoint: str, params: dict | None = None) -> dict:
        params = params or {}
        for attempt in range(1, self.config.max_retries + 1):
            try:
                async with self._semaphore:
                    await self._rate_limiter.acquire()
                    r = await self._http.get(f"{self.base_url}/{endpoint}", params=params)
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 429:
                    self._rate_limiter.backoff()
                    retry_after = int(r.headers.get("Retry-After", str(2 ** attempt)))
                    await asyncio.sleep(retry_after)
                    continue
                if attempt == self.config.max_retries:
                    return {"error": f"HTTP {r.status_code}", "body": r.text[:500]}
                await asyncio.sleep(2 ** attempt)
            except httpx.TimeoutException:
                if attempt == self.config.max_retries:
                    return {"error": "timeout"}
                await asyncio.sleep(2 ** attempt)
            except Exception as e:
                if attempt == self.config.max_retries:
                    return {"error": str(e)}
                await asyncio.sleep(2 ** attempt)
        return {"error": "max_retries_exceeded"}

    async def _get_cached(self, endpoint: str, params: dict) -> dict:
        key = self._cache_key(endpoint, params)
        cache = self._cache_hist if self._is_historical(params) else self._cache
        if key in cache:
            return cache[key]
        result = await self._get(endpoint, params)
        if "error" not in result:
            cache[key] = result
        return result

    async def _post(self, endpoint: str, data: dict) -> dict:
        for attempt in range(1, self.config.max_retries + 1):
            try:
                async with self._semaphore:
                    await self._rate_limiter.acquire()
                    r = await self._http.post(f"{self.base_url}/{endpoint}", json=data)
                if r.status_code in (200, 201):
                    return r.json()
                if r.status_code == 429:
                    self._rate_limiter.backoff()
                    await asyncio.sleep(int(r.headers.get("Retry-After", str(2 ** attempt))))
                    continue
                if attempt == self.config.max_retries:
                    return {"error": f"HTTP {r.status_code}", "body": r.text[:500]}
                await asyncio.sleep(2 ** attempt)
            except Exception as e:
                if attempt == self.config.max_retries:
                    return {"error": str(e)}
                await asyncio.sleep(2 ** attempt)
        return {"error": "max_retries_exceeded"}

    async def _delete(self, endpoint: str) -> dict:
        async with self._semaphore:
            await self._rate_limiter.acquire()
            r = await self._http.delete(f"{self.base_url}/{endpoint}")
        if r.status_code in (200, 204):
            return {"success": True}
        return {"error": f"HTTP {r.status_code}"}

    async def _paginate(self, endpoint: str, params: dict, key: str = "data",
                        max_pages: int | None = None) -> list[dict]:
        all_items = []
        page = 1
        while True:
            page_params = {**params, "page": page, "limit": self.config.default_page_limit}
            data = await self._get_cached(endpoint, page_params)
            if "error" in data:
                break
            items = data.get(key, [])
            if not items:
                break
            all_items.extend(items)
            total_pages = data.get("meta", {}).get("totalPages", 1)
            if page >= total_pages:
                break
            if max_pages and page >= max_pages:
                break
            page += 1
        return all_items

    # --- Traces ---
    async def get_traces(self, **kwargs) -> dict:
        return await self._get_cached("traces", kwargs)

    async def get_trace(self, trace_id: str) -> dict:
        return await self._get_cached(f"traces/{trace_id}", {})

    async def fetch_all_traces(self, **kwargs) -> list[dict]:
        max_pages = kwargs.pop("max_pages", None)
        return await self._paginate("traces", kwargs, key="data", max_pages=max_pages)

    # --- Observations ---
    async def get_observations(self, **kwargs) -> dict:
        return await self._get_cached("observations", kwargs)

    async def get_observation(self, observation_id: str) -> dict:
        return await self._get_cached(f"observations/{observation_id}", {})

    async def get_trace_observations(self, trace_id: str, obs_type: str | None = None) -> list[dict]:
        params: dict = {"traceId": trace_id}
        if obs_type:
            params["type"] = obs_type
        return await self._paginate("observations", params, key="data")

    async def fetch_observations_for_traces(
        self,
        trace_ids: list[str],
        obs_type: str | None = None,
    ) -> dict[str, list[dict]]:
        """Concurrent per-trace observation fetch. Use when trace count is small
        but total observation volume is large (e.g., 2M+ observations in the time range).
        Fetches observations for each trace concurrently via semaphore."""
        grouped: dict[str, list[dict]] = defaultdict(list)

        async def fetch_one(tid: str):
            obs = await self.get_trace_observations(tid, obs_type=obs_type)
            return tid, obs

        tasks = [fetch_one(tid) for tid in trace_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                continue
            tid, obs = r
            grouped[tid] = obs
        return grouped

    async def fetch_observations_by_time_range(
        self,
        from_timestamp: str,
        to_timestamp: str,
        obs_type: str | None = None,
        max_pages: int = 30,
    ) -> dict[str, list[dict]]:
        """Batch fetch: get ALL observations for a time range, grouped by traceId.
        Falls back to per-trace concurrent fetch if volume is too large (>5000 pages)."""
        # Check volume first
        check_params: dict[str, Any] = {
            "fromTimestamp": from_timestamp,
            "toTimestamp": to_timestamp,
            "limit": 1,
            "page": 1,
        }
        if obs_type:
            check_params["type"] = obs_type
        check = await self._get_cached("observations", check_params)
        total_pages = check.get("meta", {}).get("totalPages", 0)

        if total_pages > 5000:
            # Too many observations — return empty, caller should use fetch_observations_for_traces
            return {}

        params: dict[str, Any] = {
            "fromTimestamp": from_timestamp,
            "toTimestamp": to_timestamp,
        }
        if obs_type:
            params["type"] = obs_type
        all_obs = await self._paginate("observations", params, key="data", max_pages=max_pages)
        grouped: dict[str, list[dict]] = defaultdict(list)
        for obs in all_obs:
            tid = obs.get("traceId")
            if tid:
                grouped[tid].append(obs)
        return grouped

    # --- Sessions ---
    async def get_sessions(self, **kwargs) -> dict:
        return await self._get_cached("sessions", kwargs)

    async def get_session(self, session_id: str) -> dict:
        return await self._get_cached(f"sessions/{session_id}", {})

    # --- Scores ---
    async def get_scores(self, **kwargs) -> dict:
        return await self._get_cached("scores", kwargs)

    async def fetch_all_scores(self, **kwargs) -> list[dict]:
        max_pages = kwargs.pop("max_pages", None)
        return await self._paginate("scores", kwargs, key="data", max_pages=max_pages)

    async def create_score(self, data: dict) -> dict:
        return await self._post("scores", data)

    # --- Prompts ---
    async def get_prompts(self, **kwargs) -> dict:
        return await self._get_cached("prompts", kwargs)

    async def get_prompt(self, name: str, **kwargs) -> dict:
        return await self._get_cached(f"prompts/{name}", kwargs)

    async def create_prompt(self, data: dict) -> dict:
        return await self._post("prompts", data)

    async def update_prompt_labels(self, prompt_name: str, version: int, labels: list[str]) -> dict:
        async with self._semaphore:
            await self._rate_limiter.acquire()
            r = await self._http.patch(
                f"{self.base_url}/v2/prompts/{prompt_name}/versions/{version}",
                json={"labels": labels},
            )
        if r.status_code == 200:
            return r.json()
        return {"error": f"HTTP {r.status_code}"}

    # --- Datasets ---
    async def get_datasets(self, **kwargs) -> dict:
        return await self._get_cached("datasets", kwargs)

    async def get_dataset(self, name: str) -> dict:
        return await self._get_cached(f"datasets/{name}", {})

    async def create_dataset(self, data: dict) -> dict:
        return await self._post("datasets", data)

    async def get_dataset_items(self, dataset_name: str, **kwargs) -> dict:
        kwargs["datasetName"] = dataset_name
        return await self._get_cached("dataset-items", kwargs)

    async def get_dataset_item(self, item_id: str) -> dict:
        return await self._get_cached(f"dataset-items/{item_id}", {})

    async def create_dataset_item(self, data: dict) -> dict:
        return await self._post("dataset-items", data)

    async def delete_dataset_item(self, item_id: str) -> dict:
        return await self._delete(f"dataset-items/{item_id}")

    # --- Metrics ---
    async def get_daily_metrics(self, **kwargs) -> dict:
        return await self._get_cached("metrics/daily", kwargs)

    # --- Utility (sync — no I/O) ---
    def resolve_time_range(self, time_range: str,
                           start_date: str | None = None,
                           end_date: str | None = None) -> tuple[datetime, datetime]:
        now = datetime.now(timezone.utc)
        presets = {
            "today": (now.replace(hour=0, minute=0, second=0, microsecond=0), now),
            "yesterday": (
                (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
                now.replace(hour=0, minute=0, second=0, microsecond=0),
            ),
            "last_7_days": (now - timedelta(days=7), now),
            "last_15_days": (now - timedelta(days=15), now),
            "last_30_days": (now - timedelta(days=30), now),
            "last_90_days": (now - timedelta(days=90), now),
        }
        if time_range == "custom":
            s = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            e = datetime.strptime(end_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
            return s, e
        return presets.get(time_range, presets["last_30_days"])

    def extract_domain(self, user_id: str | None) -> str | None:
        if not user_id or "@" not in user_id:
            return None
        return user_id.split("@", 1)[1].lower()

    def is_internal(self, domain: str | None) -> bool:
        if not domain:
            return True
        return domain in self.config.internal_domains
