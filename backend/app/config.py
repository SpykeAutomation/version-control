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

    @property
    def repos_dir(self) -> Path:
        return self.data_dir / "repos"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{(self.data_dir / 'app.db').resolve()}"


settings = Settings()
settings.repos_dir.mkdir(parents=True, exist_ok=True)
