"""Configuration for langfuse-mcp."""
import os
from dataclasses import dataclass, field


@dataclass
class Config:
    """Server configuration, loaded from environment variables."""
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
        internal = os.getenv("LANGFUSE_INTERNAL_DOMAINS", "")
        return cls(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
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
