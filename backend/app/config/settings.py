from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read from environment / `.env`. Secrets are SecretStr so they never print."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongodb_uri: SecretStr | None = None
    mongodb_database: str = "rival_coaches"

    llm_provider: str | None = None
    llm_api_key: SecretStr | None = None

    elevenlabs_api_key: SecretStr | None = None
    elevenlabs_blue_voice_id: str | None = None
    elevenlabs_red_voice_id: str | None = None

    cors_origins: list[str] = ["http://localhost:5173"]

    # Seconds between simulation steps for live matches (40 steps per match).
    match_step_seconds: float = 1.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
