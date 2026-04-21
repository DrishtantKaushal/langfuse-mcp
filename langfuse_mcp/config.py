"""Configuration for langfuse-mcp."""
import os
from dataclasses import dataclass, field


@dataclass
class Config:
    """Per-project configuration."""
    public_key: str = ""
    secret_key: str = ""
    host: str = "https://cloud.langfuse.com"
    read_only: bool = False
    internal_domains: list[str] = field(default_factory=list)
    default_page_limit: int = 100
    max_retries: int = 3
    # Rate limiting
    rate_limit_rpm: int = 0  # 0 = auto-detect (30 for cloud, unlimited for self-hosted)
    concurrent_limit: int = 3
    # Caching
    cache_ttl_seconds: int = 300  # 5 min for today's data
    cache_ttl_historical_seconds: int = 3600  # 1 hour for past data
    cache_max_size: int = 256
    # Default time range for analytics tools when user doesn't specify
    default_time_range: str = "today"

    @property
    def is_cloud(self) -> bool:
        return "cloud.langfuse.com" in self.host

    @property
    def effective_rpm(self) -> int:
        """Resolved RPM: explicit setting > auto-detect."""
        if self.rate_limit_rpm > 0:
            return self.rate_limit_rpm
        return 30 if self.is_cloud else 0  # self-hosted = unlimited

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            **_shared_env(),
        )


def _shared_env() -> dict:
    """Env vars shared across all projects (read-only flag, paging, rate limits, etc.)."""
    internal = os.getenv("LANGFUSE_INTERNAL_DOMAINS", "")
    return dict(
        read_only=os.getenv("LANGFUSE_MCP_READ_ONLY", "").lower() in ("true", "1"),
        internal_domains=[d.strip() for d in internal.split(",") if d.strip()],
        default_page_limit=int(os.getenv("LANGFUSE_PAGE_LIMIT", "100")),
        max_retries=int(os.getenv("LANGFUSE_MAX_RETRIES", "3")),
        rate_limit_rpm=int(os.getenv("LANGFUSE_RATE_LIMIT_RPM", "0")),
        concurrent_limit=int(os.getenv("LANGFUSE_CONCURRENT_LIMIT", "3")),
        cache_ttl_seconds=int(os.getenv("LANGFUSE_CACHE_TTL", "300")),
        cache_ttl_historical_seconds=int(os.getenv("LANGFUSE_CACHE_TTL_HISTORICAL", "3600")),
        cache_max_size=int(os.getenv("LANGFUSE_CACHE_MAX_SIZE", "256")),
        default_time_range=os.getenv("LANGFUSE_DEFAULT_TIME_RANGE", "today"),
    )


@dataclass
class MultiProjectConfig:
    """Holds a dict of project-name → Config plus the name of the default project."""
    projects: dict[str, Config]
    default_project: str

    @classmethod
    def from_env(cls) -> "MultiProjectConfig":
        """Load project configs from env.

        Two modes, tried in order:
        1. Multi-project: LANGFUSE_PROJECT_{N}_NAME + _PUBLIC_KEY / _SECRET_KEY / _HOST (N=1,2,...).
           Default project name from LANGFUSE_DEFAULT_PROJECT (else the first index found).
        2. Legacy single-project: LANGFUSE_PUBLIC_KEY / _SECRET_KEY / _HOST. Registered under
           the name 'default'.
        """
        projects: dict[str, Config] = {}
        shared = _shared_env()

        # Mode 1: scan indexed env vars
        idx = 1
        while True:
            name = os.getenv(f"LANGFUSE_PROJECT_{idx}_NAME")
            if not name:
                break
            pk = os.getenv(f"LANGFUSE_PROJECT_{idx}_PUBLIC_KEY", "")
            sk = os.getenv(f"LANGFUSE_PROJECT_{idx}_SECRET_KEY", "")
            host = os.getenv(
                f"LANGFUSE_PROJECT_{idx}_HOST", "https://cloud.langfuse.com"
            )
            if not pk or not sk:
                raise RuntimeError(
                    f"LANGFUSE_PROJECT_{idx}_NAME='{name}' is set but "
                    f"LANGFUSE_PROJECT_{idx}_PUBLIC_KEY and/or _SECRET_KEY are missing."
                )
            if name in projects:
                raise RuntimeError(
                    f"Duplicate project name '{name}' at index {idx}; names must be unique."
                )
            projects[name] = Config(public_key=pk, secret_key=sk, host=host, **shared)
            idx += 1

        if projects:
            default = os.getenv("LANGFUSE_DEFAULT_PROJECT") or next(iter(projects))
            if default not in projects:
                raise RuntimeError(
                    f"LANGFUSE_DEFAULT_PROJECT='{default}' does not match any configured "
                    f"project. Available: {sorted(projects)}"
                )
            return cls(projects=projects, default_project=default)

        # Mode 2: legacy single-project
        legacy = Config.from_env()
        if legacy.public_key and legacy.secret_key:
            return cls(projects={"default": legacy}, default_project="default")

        raise RuntimeError(
            "No Langfuse project configured. Set either the legacy single-project vars "
            "(LANGFUSE_PUBLIC_KEY / _SECRET_KEY / _HOST) or indexed multi-project vars "
            "(LANGFUSE_PROJECT_1_NAME / _PUBLIC_KEY / _SECRET_KEY / _HOST, ...)."
        )
