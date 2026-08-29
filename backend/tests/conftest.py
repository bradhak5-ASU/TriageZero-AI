import copy
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

SAMPLE_PACKAGE = {
    "schema_version": "1.0",
    "source": "novacart-playwright",
    "run": {
        "run_id": "github-run-12345",
        "trigger": "local",
        "started_at": "2026-08-25T18:00:00Z",
    },
    "repository": {
        "name": "novacart-target",
        "branch": "main",
        "commit_sha": "abc123def4567890abc123def4567890abc123de",
    },
    "environment": {
        "name": "local",
        "target_url": "http://localhost:5173",
        "browser": "chromium",
    },
    "test": {
        "name": "successful checkout shows confirmation page",
        "file": "playwright-tests/tests/novacart-baseline.spec.ts",
        "status": "failed",
        "retry": 0,
    },
    "failure": {
        "expected": "201",
        "actual": "500",
        "message": "Expected HTTP 201 but received HTTP 500",
        "stack_trace": "Error: Expected HTTP 201 but received HTTP 500\n    at spec.ts:214:11",
    },
    "network_evidence": [
        {"method": "POST", "url": "http://localhost:8000/api/v1/orders", "status": 500}
    ],
    "console_errors": [
        "Failed to load resource: the server responded with status 500"
    ],
    "artifacts": {
        "screenshot_path": "test-results/run/test-failed-1.png",
        "trace_path": "test-results/run/trace.zip",
    },
}


@pytest.fixture(autouse=True)
def disable_live_ai_providers(monkeypatch):
    """The test suite is offline even when a developer's ignored .env selects
    Vertex or contains live credentials.

    Tests that exercise provider behavior inject fakes and may construct
    Settings with explicit values, but no test may inherit a live provider
    configuration from the workstation.
    """
    monkeypatch.setenv("ANALYZER_MODE", "deterministic")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "false")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "")


@pytest.fixture()
def sample_package() -> dict:
    return copy.deepcopy(SAMPLE_PACKAGE)


@pytest.fixture()
def make_client(tmp_path, monkeypatch) -> Callable[..., TestClient]:
    """Factory building a fresh app instance over the same temp database —
    used both for normal tests and for restart-persistence tests."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("LOCAL_PROCESSING_DELAY_MS", "0")
    monkeypatch.setenv("FRONTEND_ORIGINS", "http://localhost:5174")
    monkeypatch.setenv("ANALYZER_MODE", "deterministic")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "false")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "")
    monkeypatch.setenv("API_AUTH_REQUIRED", "false")
    monkeypatch.setenv("INGESTION_API_TOKEN", "")
    monkeypatch.setenv("DASHBOARD_API_TOKEN", "")

    created: list[TestClient] = []

    def factory(**env: str) -> TestClient:
        from app.core.config import get_settings
        from app.db.session import reset_db_state
        from app.main import create_app

        for key, value in env.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()
        reset_db_state()
        client = TestClient(create_app())
        client.__enter__()
        created.append(client)
        return client

    yield factory

    for client in created:
        client.__exit__(None, None, None)
    from app.core.config import get_settings
    from app.db.session import reset_db_state

    reset_db_state()
    get_settings.cache_clear()


@pytest.fixture()
def client(make_client) -> TestClient:
    return make_client()
