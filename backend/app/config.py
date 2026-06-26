"""Central configuration for the Reset Radar backend.

Pydantic-Settings-based: every env variable in `.env` becomes a typed
attribute on the shared `Settings` instance. Import `settings` from
anywhere in the backend.

Carried over from `legacy-sonar/src/config.py`, refactored to Pydantic
BaseSettings and extended with the new Reset Radar variable set.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parent.parent
MVP_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    """All env-driven configuration for the Reset Radar backend."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # === API keys ===
    groq_api_key: str = Field(default="", description="Groq Cloud API key")
    spotify_client_id: str = Field(default="", description="Spotify Developer app client ID")
    spotify_client_secret: str = Field(default="", description="Spotify Developer app client secret")
    spotify_redirect_uri: str = Field(
        default="http://127.0.0.1:8000/auth/callback",
        description="OAuth callback URL registered with Spotify",
    )

    # === Session signing (R4 OAuth) ===
    session_secret_key: str = Field(
        default="reset-radar-dev-secret-CHANGE-IN-PROD",
        description=(
            "Used to sign the session cookie that links a browser to a user_id "
            "after OAuth callback. CHANGE for any deploy; the dev default is "
            "fine for local mock-mode demos."
        ),
    )
    frontend_origin: str = Field(
        default="http://127.0.0.1:5173",
        description="Where /auth/callback redirects after a successful login.",
    )

    # === LLM models ===
    groq_model_reasoner: str = Field(default="llama-3.3-70b-versatile")
    groq_model_fast: str = Field(default="llama-3.1-8b-instant")

    # === Mock mode (the live-demo default) ===
    mock_mode: bool = Field(
        default=True,
        description=(
            "When True, the backend reads from mock_data/ and never calls "
            "the live Spotify Web API. The Groq calls still happen unless "
            "explicitly stubbed in tests."
        ),
    )

    # === Persistence ===
    database_url: str = Field(default=f"sqlite:///{BACKEND_DIR / 'reset_radar.db'}")

    # === Detection trigger thresholds (see architecture.md section 2) ===
    stuck_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    stuck_streak_weeks: int = Field(default=3, ge=1)
    cooldown_weeks: int = Field(default=4, ge=0)

    # === Reset session trial window ===
    trial_window_days: int = Field(default=10, ge=1)

    # === Jobs API auth (R6 GitHub Action) ===
    jobs_api_token: str = Field(
        default="",
        description=(
            "Optional shared secret required on POST /jobs/run-detection. "
            "When empty (the default for local dev + the live demo), the "
            "endpoint is open and the workflow runs unauthenticated against "
            "a single-tenant deployment. When set, the GitHub Actions "
            "workflow must send `Authorization: Bearer <token>` matching "
            "this value."
        ),
    )

    # === Operational knobs ===
    max_candidates_from_search: int = Field(default=80, ge=20)
    spotify_search_page_size: int = Field(default=10, ge=1, le=10)
    reset_playlist_size: int = Field(default=20, ge=5)

    # === Paths ===
    @property
    def backend_dir(self) -> Path:
        return BACKEND_DIR

    @property
    def mvp_dir(self) -> Path:
        return MVP_DIR

    @property
    def mock_data_dir(self) -> Path:
        return BACKEND_DIR / "mock_data"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton. Import `settings` instead in normal code."""
    return Settings()


settings = get_settings()


__all__ = ["Settings", "get_settings", "settings", "BACKEND_DIR", "MVP_DIR"]
