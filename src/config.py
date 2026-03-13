from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    gemini_api_key: str = Field(description="Google Gemini API key")
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/game_content",
        description="PostgreSQL connection URL",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
