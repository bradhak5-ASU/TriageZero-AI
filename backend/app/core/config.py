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

    # --- human sign-in (Firebase Authentication) -----------------------------
    # Humans sign in through Firebase and send a short-lived ID token; machines
    # keep using INGESTION_API_TOKEN. The two are verified independently.
    # Disabled by default so local development and tests need no Firebase project.
    firebase_auth_enabled: bool = False
    firebase_project_id: str = ""

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

    @model_validator(mode="after")
    def validate_firebase_auth(self) -> "Settings":
        """Firebase must be usable when it is switched on.

        A project id is required for audience checking; without it every token
        would fail verification and the dashboard would be silently unusable.
        """
        if not self.firebase_auth_enabled:
            return self
        if not (self.firebase_project_id or self.google_cloud_project):
            raise ValueError(
                "FIREBASE_PROJECT_ID (or GOOGLE_CLOUD_PROJECT) must be set "
                "when FIREBASE_AUTH_ENABLED is true"
            )
        return self

    @model_validator(mode="after")
    def validate_durable_database(self) -> "Settings":
        """Refuse to run staging/production on an ephemeral SQLite file.

        Cloud Run gives each container an in-memory filesystem that is thrown
        away on every restart, redeploy and scale-to-zero. A SQLite database
        there appears to work and then silently loses every investigation -
        the worst possible failure mode, because nothing errors. Failing at
        startup instead makes the misconfiguration impossible to miss.
        """
        environment = self.app_env.strip().lower()
        if environment not in {"staging", "production"}:
            return self
        if self.database_url.strip().lower().startswith("sqlite"):
            raise ValueError(
                "DATABASE_URL must point at a durable database (PostgreSQL) in "
                "staging and production - a SQLite file on Cloud Run is erased "
                "on every restart. Example: "
                "postgresql+psycopg://USER:PASSWORD@/DB?host=/cloudsql/PROJECT:REGION:INSTANCE"
            )
        return self

    @model_validator(mode="after")
    def validate_cors_in_production(self) -> "Settings":
        """The browser origin allowed to call this API must be exact.

        `allow_origins=["*"]` combined with an Authorization header is the
        classic way a dashboard API becomes callable from any page the signed-in
        user happens to visit. Requiring explicit HTTPS origins in
        staging/production makes that impossible to configure by accident.
        """
        environment = self.app_env.strip().lower()
        if environment not in {"staging", "production"}:
            return self
        origins = self.cors_origins
        if not origins:
            raise ValueError("FRONTEND_ORIGINS must list the exact dashboard origin(s)")
        for origin in origins:
            if origin == "*":
                raise ValueError(
                    "FRONTEND_ORIGINS must not be '*' in staging or production - "
                    "list the exact dashboard origin"
                )
            if not origin.startswith("https://"):
                raise ValueError(
                    f"FRONTEND_ORIGINS entry {origin!r} must be an https:// origin "
                    "in staging and production"
                )
            if origin.endswith("/"):
                raise ValueError(
                    f"FRONTEND_ORIGINS entry {origin!r} must have no trailing slash - "
                    "browsers send the origin without one and it would never match"
                )
        return self

    @property
    def database_backend(self) -> str:
        """`sqlite` or `postgresql` - the backend this configuration will use."""
        url = self.database_url.strip().lower()
        if url.startswith("sqlite"):
            return "sqlite"
        if url.startswith(("postgres://", "postgresql")):
            return "postgresql"
        return url.split(":", 1)[0] or "unknown"

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
