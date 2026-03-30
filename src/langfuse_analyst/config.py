"""Configuration for langfuse-analyst."""
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
    rate_limit_sleep: float = 0.3

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
            rate_limit_sleep=float(os.getenv("LANGFUSE_RATE_LIMIT_SLEEP", "0.3")),
        )
