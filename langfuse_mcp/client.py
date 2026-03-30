"""Langfuse API client wrapper with pagination, retries, and rate limiting."""
import base64
import time
from datetime import datetime, timezone, timedelta

import httpx

from .config import Config


class LangfuseClient:
    """Thin wrapper around the Langfuse REST API."""

    def __init__(self, config: Config):
        self.config = config
        self.base_url = f"{config.host}/api/public"
        auth = base64.b64encode(f"{config.public_key}:{config.secret_key}".encode()).decode()
        self.headers = {"Authorization": f"Basic {auth}"}
        self._http = httpx.Client(timeout=90, headers=self.headers)

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        params = params or {}
        for attempt in range(1, self.config.max_retries + 1):
            try:
                r = self._http.get(f"{self.base_url}/{endpoint}", params=params)
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 429:
                    time.sleep(2 ** attempt)
                    continue
                if attempt == self.config.max_retries:
                    return {"error": f"HTTP {r.status_code}", "body": r.text[:500]}
                time.sleep(2 ** attempt)
            except httpx.TimeoutException:
                if attempt == self.config.max_retries:
                    return {"error": "timeout"}
                time.sleep(2 ** attempt)
            except Exception as e:
                if attempt == self.config.max_retries:
                    return {"error": str(e)}
                time.sleep(2 ** attempt)
        return {"error": "max_retries_exceeded"}

    def _post(self, endpoint: str, data: dict) -> dict:
        for attempt in range(1, self.config.max_retries + 1):
            try:
                r = self._http.post(f"{self.base_url}/{endpoint}", json=data)
                if r.status_code in (200, 201):
                    return r.json()
                if r.status_code == 429:
                    time.sleep(2 ** attempt)
                    continue
                if attempt == self.config.max_retries:
                    return {"error": f"HTTP {r.status_code}", "body": r.text[:500]}
                time.sleep(2 ** attempt)
            except Exception as e:
                if attempt == self.config.max_retries:
                    return {"error": str(e)}
                time.sleep(2 ** attempt)
        return {"error": "max_retries_exceeded"}

    def _delete(self, endpoint: str) -> dict:
        r = self._http.delete(f"{self.base_url}/{endpoint}")
        if r.status_code in (200, 204):
            return {"success": True}
        return {"error": f"HTTP {r.status_code}"}

    def _paginate(self, endpoint: str, params: dict, key: str = "data",
                  max_pages: int | None = None) -> list[dict]:
        all_items = []
        page = 1
        while True:
            params["page"] = page
            params["limit"] = self.config.default_page_limit
            data = self._get(endpoint, params)
            if "error" in data:
                break
            items = data.get(key, [])
            if not items:
                break
            all_items.extend(items)
            meta = data.get("meta", {})
            total_pages = meta.get("totalPages", 1)
            if page >= total_pages:
                break
            if max_pages and page >= max_pages:
                break
            page += 1
            time.sleep(self.config.rate_limit_sleep)
        return all_items

    # --- Traces ---
    def get_traces(self, **kwargs) -> dict:
        return self._get("traces", kwargs)

    def get_trace(self, trace_id: str) -> dict:
        return self._get(f"traces/{trace_id}")

    def fetch_all_traces(self, **kwargs) -> list[dict]:
        max_pages = kwargs.pop("max_pages", None)
        return self._paginate("traces", kwargs, key="data", max_pages=max_pages)

    # --- Observations ---
    def get_observations(self, **kwargs) -> dict:
        return self._get("observations", kwargs)

    def get_observation(self, observation_id: str) -> dict:
        return self._get(f"observations/{observation_id}")

    def get_trace_observations(self, trace_id: str, obs_type: str | None = None) -> list[dict]:
        params: dict = {"traceId": trace_id}
        if obs_type:
            params["type"] = obs_type
        return self._paginate("observations", params, key="data")

    # --- Sessions ---
    def get_sessions(self, **kwargs) -> dict:
        return self._get("sessions", kwargs)

    def get_session(self, session_id: str) -> dict:
        return self._get(f"sessions/{session_id}")

    # --- Scores ---
    def get_scores(self, **kwargs) -> dict:
        return self._get("scores", kwargs)

    def fetch_all_scores(self, **kwargs) -> list[dict]:
        max_pages = kwargs.pop("max_pages", None)
        return self._paginate("scores", kwargs, key="data", max_pages=max_pages)

    def create_score(self, data: dict) -> dict:
        return self._post("scores", data)

    # --- Prompts ---
    def get_prompts(self, **kwargs) -> dict:
        return self._get("prompts", kwargs)

    def get_prompt(self, name: str, **kwargs) -> dict:
        return self._get(f"prompts/{name}", kwargs)

    def create_prompt(self, data: dict) -> dict:
        return self._post("prompts", data)

    def update_prompt_labels(self, prompt_name: str, version: int, labels: list[str]) -> dict:
        r = self._http.patch(
            f"{self.base_url}/v2/prompts/{prompt_name}/versions/{version}",
            json={"labels": labels},
        )
        if r.status_code == 200:
            return r.json()
        return {"error": f"HTTP {r.status_code}"}

    # --- Datasets ---
    def get_datasets(self, **kwargs) -> dict:
        return self._get("datasets", kwargs)

    def get_dataset(self, name: str) -> dict:
        return self._get(f"datasets/{name}")

    def create_dataset(self, data: dict) -> dict:
        return self._post("datasets", data)

    def get_dataset_items(self, dataset_name: str, **kwargs) -> dict:
        kwargs["datasetName"] = dataset_name
        return self._get("dataset-items", kwargs)

    def get_dataset_item(self, item_id: str) -> dict:
        return self._get(f"dataset-items/{item_id}")

    def create_dataset_item(self, data: dict) -> dict:
        return self._post("dataset-items", data)

    def delete_dataset_item(self, item_id: str) -> dict:
        return self._delete(f"dataset-items/{item_id}")

    # --- Metrics ---
    def get_daily_metrics(self, **kwargs) -> dict:
        return self._get("metrics/daily", kwargs)

    # --- Utility ---
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
