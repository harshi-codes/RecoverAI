"""
RecoverAI – application settings via pydantic-settings.
All values come from environment variables or .env file.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "RecoverAI"
    environment: str = "development"
    debug: bool = False

    # Database – default SQLite for zero-install local dev
    database_url: str = "sqlite+aiosqlite:///./recoverai.db"

    # Razorpay (test/sandbox only)
    razorpay_key_id: str = "rzp_test_placeholder"
    razorpay_key_secret: str = "placeholder"
    razorpay_webhook_secret: str = "placeholder"

    # Gemini (optional – RCA reasoning text fallback if absent)
    gemini_api_key: str = ""

    # CORS
    frontend_url: str = "http://localhost:5173"

    # ML artifact paths
    @property
    def ml_artifacts_dir(self) -> Path:
        return Path(__file__).parent / "ml" / "artifacts"

    @property
    def model_path(self) -> Path:
        return self.ml_artifacts_dir / "model.joblib"

    @property
    def encoder_path(self) -> Path:
        return self.ml_artifacts_dir / "encoder.joblib"


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance (singleton)."""
    return Settings()
