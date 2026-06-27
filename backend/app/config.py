"""Runtime settings, all overridable via PLCVC_* environment variables."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PLCVC_", env_file=".env", extra="ignore"
    )

    # Everything that must survive restarts lives under data_dir: the SQLite
    # database and one Git repository per project. In production this is a
    # mounted persistent volume (e.g. /data).
    data_dir: Path = Path("./data")
    jwt_secret: str = "dev-insecure-change-me"
    jwt_expire_minutes: int = 60 * 24 * 7  # one week
    # Comma-separated allowed origins, or "*" for any (fine for a pilot).
    cors_origins: str = "*"
    # Login rate limit: max attempts per client IP within the window (seconds).
    login_rate_max: int = 10
    login_rate_window_seconds: int = 60
    # Invite rate limit: max preview/accept calls per client IP within the
    # window (seconds). Guards the public invite endpoints against token
    # enumeration. Roomier than login since a legit accept page makes a couple
    # of calls (preview + submit, with retries).
    invite_rate_max: int = 20
    invite_rate_window_seconds: int = 60
    # Max size of a single uploaded file (megabytes). Enforced per file in the
    # upload handler. NOTE: this is per-file; the Caddy edge separately caps the
    # whole request body (see Caddyfile `request_body max_size`), which must be
    # large enough to admit a batch of these.
    max_upload_mb: int = 100
    # Per-organization storage cap (gigabytes). Counts each org's Git repos and
    # their cached diffs on disk; enforced when a commit is uploaded.
    org_storage_limit_gb: float = 2.0
    # Soft cap on the whole diff cache (megabytes). When exceeded, the least
    # recently used cache files are evicted (a diff is cheap to recompute lazily).
    diff_cache_max_mb: int = 500
    # Public base URL of the web app (not the API). Used only to build the
    # device-login verification URL the CLI opens in the browser
    # (`<web_app_url>/cli-auth?code=...`).
    web_app_url: str = "https://app.spykeautomation.com"
    # CLI device-login (RFC 8628): how long a device/user code stays valid, and
    # how often the CLI is told to poll for the token.
    device_code_ttl_minutes: int = 10
    device_poll_interval_seconds: int = 5
    # Device-auth rate limit: max code/token calls per client IP within the
    # window (seconds). Guards the public device endpoints against flooding.
    device_rate_max: int = 60
    device_rate_window_seconds: int = 60

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def org_storage_limit_bytes(self) -> int:
        return int(self.org_storage_limit_gb * 1024 * 1024 * 1024)

    @property
    def diff_cache_max_bytes(self) -> int:
        return self.diff_cache_max_mb * 1024 * 1024

    @property
    def repos_dir(self) -> Path:
        return self.data_dir / "repos"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{(self.data_dir / 'app.db').resolve()}"


settings = Settings()
settings.repos_dir.mkdir(parents=True, exist_ok=True)
