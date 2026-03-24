"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server configuration loaded from environment / .env file."""

    model_config = SettingsConfigDict(env_file=".env")

    DATABASE_URL: str = "postgresql+asyncpg://localhost:5432/etelemetry"
    MAXMIND_DB_PATH: str = "/data/GeoLite2-City.mmdb"
    GITHUB_TOKEN: str | None = None
    CACHE_TTL_SECONDS: int = 21600  # 6 hours
    ALLOWLIST_PATH: str = "allowlist.yml"
    TIME_BUCKET_HOURS: int = 1
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000


settings = Settings()
