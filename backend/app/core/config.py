from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Centralized configuration. All values come from the environment
    (or backend/.env in local development). Secret values use ``SecretStr``
    so settings representations cannot disclose them accidentally."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    database_url: str = "sqlite:///./data/triagezero.db"
    frontend_origins: str = "http://localhost:5174"
    max_request_bytes: int = 2_097_152
    local_processing_delay_ms: int = 250
    log_level: str = "INFO"

    # --- API authentication -------------------------------------------------
    # Local development is open by default. Staging/production fail closed:
    # authentication must be enabled with distinct high-entropy tokens.
    api_auth_required: bool = False
    ingestion_api_token: SecretStr = SecretStr("")
    dashboard_api_token: SecretStr = SecretStr("")

    # --- analysis providers -------------------------------------------------
    # Default stays deterministic: no credentials, no network, fully local.
    # Switch to gemini / gemini_adk only after credentials are supplied
    # intentionally (see docs/CREDENTIALS_SETUP.md).
    analyzer_mode: str = "deterministic"
    ai_fallback_enabled: bool = True
    ai_prompt_version: str = "v2"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    gemini_request_timeout_seconds: int = 60
    gemini_max_retries: int = 2
    # ADK may perform multiple sequential model/tool turns, so its total
    # workflow deadline must be independent from the direct Gemini call.
    adk_request_timeout_seconds: int = 120

    google_genai_use_vertexai: bool = False
    google_cloud_project: str = ""
    google_cloud_location: str = "global"

    @field_validator("analyzer_mode")
    @classmethod
    def known_mode(cls, v: str) -> str:
        allowed = ("deterministic", "gemini", "gemini_adk")
        if v not in allowed:
            raise ValueError(f"ANALYZER_MODE must be one of {allowed}, got {v!r}")
        return v

    @model_validator(mode="after")
    def validate_api_auth(self) -> "Settings":
        environment = self.app_env.strip().lower()
        if environment in {"staging", "production"} and not self.api_auth_required:
            raise ValueError("API_AUTH_REQUIRED must be true in staging and production")
        if not self.api_auth_required:
            return self

        ingestion = self.ingestion_api_token.get_secret_value()
        dashboard = self.dashboard_api_token.get_secret_value()
        if len(ingestion) < 32 or len(dashboard) < 32:
            raise ValueError(
                "INGESTION_API_TOKEN and DASHBOARD_API_TOKEN must each be at least 32 characters"
            )
        if ingestion == dashboard:
            raise ValueError("INGESTION_API_TOKEN and DASHBOARD_API_TOKEN must be different")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origins.split(",") if o.strip()]

    @property
    def resolved_database_url(self) -> str:
        """Anchor relative sqlite paths at the backend directory so behavior
        does not depend on the process working directory."""
        prefix = "sqlite:///"
        url = self.database_url
        if url.startswith(prefix) and not url[len(prefix) :].startswith("/"):
            db_path = (BACKEND_DIR / url[len(prefix) :].lstrip("./")).resolve()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            return f"{prefix}{db_path}"
        if url.startswith(prefix):
            Path(url[len(prefix) :]).parent.mkdir(parents=True, exist_ok=True)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
