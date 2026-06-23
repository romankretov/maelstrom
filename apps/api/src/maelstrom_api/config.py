from functools import lru_cache
from pathlib import Path

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    domain: str = Field(default="maelstromhub.com", alias="MAELSTROM_DOMAIN")
    env: str = Field(default="development", alias="MAELSTROM_ENV")
    log_level: str = Field(default="INFO", alias="MAELSTROM_LOG_LEVEL")

    database_url: PostgresDsn = Field(alias="DATABASE_URL")
    redis_url: RedisDsn = Field(alias="REDIS_URL")

    api_host: str = Field(default="0.0.0.0", alias="API_HOST")  # noqa: S104
    api_port: int = Field(default=8000, alias="API_PORT")
    api_secret_key: SecretStr = Field(alias="API_SECRET_KEY")
    api_cors_origins: str = Field(default="", alias="API_CORS_ORIGINS")

    session_cookie_domain: str | None = Field(default=None, alias="SESSION_COOKIE_DOMAIN")
    session_cookie_secure: bool = Field(default=True, alias="SESSION_COOKIE_SECURE")

    master_key_path: Path = Field(
        default=Path("/run/secrets/master_key"),
        alias="MAELSTROM_MASTER_KEY_PATH",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
