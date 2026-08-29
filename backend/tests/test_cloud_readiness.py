"""Cloud Run readiness: probes, port binding, and production CORS.

These are the properties a deployment silently gets wrong. Each test states
the failure it is preventing rather than restating the code.
"""

import pytest

from app.core.config import Settings

PROD = {
    "app_env": "production",
    "database_url": "postgresql+psycopg://u:p@db.internal:5432/triagezero",
    "api_auth_required": True,
    "ingestion_api_token": "i" * 40,
    "dashboard_api_token": "d" * 40,
}


# --- probes -----------------------------------------------------------------


def test_livez_answers_without_touching_the_database(client, monkeypatch):
    """A liveness probe must not fail because the database is down - that
    would make Cloud Run restart a healthy container in a loop while the real
    problem is elsewhere."""
    import app.api.routes.probes as probes

    def explode():
        raise RuntimeError("database is unreachable")

    monkeypatch.setattr(probes, "new_session", explode)

    res = client.get("/api/v1/livez")
    assert res.status_code == 200
    assert res.json()["status"] == "alive"


def test_readyz_reports_ready_when_the_datastore_answers(client):
    res = client.get("/api/v1/readyz")
    assert res.status_code == 200
    assert res.json()["status"] == "ready"


def test_readyz_returns_503_when_the_datastore_is_unreachable(client, monkeypatch):
    """503 holds traffic off this instance. Returning 200 here is how a
    revision with a wrong DATABASE_URL ends up serving 500s to judges."""
    import app.api.routes.probes as probes

    def explode():
        raise RuntimeError("connection refused")

    monkeypatch.setattr(probes, "new_session", explode)

    res = client.get("/api/v1/readyz")
    assert res.status_code == 503
    assert res.json()["status"] == "not_ready"


def test_probes_are_open_so_the_platform_can_call_them(make_client):
    """Cloud Run's probes send no credentials. If probes required auth the
    revision would never pass its startup check."""
    client = make_client(
        API_AUTH_REQUIRED="true",
        INGESTION_API_TOKEN="i" * 40,
        DASHBOARD_API_TOKEN="d" * 40,
    )
    assert client.get("/api/v1/livez").status_code == 200
    assert client.get("/api/v1/readyz").status_code == 200


def test_probe_failure_discloses_nothing_about_the_datastore(client, monkeypatch):
    """These endpoints are unauthenticated and internet-reachable, so the body
    must never carry a hostname, DSN or driver message."""
    import app.api.routes.probes as probes

    secret = "postgresql://tzuser:sup3rs3cret@10.9.8.7:5432/triagezero"

    def explode():
        raise RuntimeError(f"could not connect to {secret}")

    monkeypatch.setattr(probes, "new_session", explode)

    body = client.get("/api/v1/readyz").text
    assert "sup3rs3cret" not in body
    assert "10.9.8.7" not in body
    assert "tzuser" not in body
    assert body.count(":") < 5  # a fixed status object, not a leaked message


def test_probes_are_absent_from_the_public_api_schema(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/livez" not in paths
    assert "/api/v1/readyz" not in paths
    assert "/api/v1/health" in paths  # the dashboard's own endpoint stays


# --- production CORS --------------------------------------------------------


def test_production_rejects_a_wildcard_origin():
    """`*` plus an Authorization header means any page the signed-in user
    visits can call this API."""
    with pytest.raises(ValueError, match="must not be"):
        Settings(**PROD, frontend_origins="*")


def test_production_rejects_a_plaintext_origin():
    with pytest.raises(ValueError, match="https"):
        Settings(**PROD, frontend_origins="http://dashboard.example.com")


def test_production_rejects_a_trailing_slash_origin():
    """A browser sends `https://host` with no path. A configured
    `https://host/` never matches, and CORS then fails at demo time with a
    message that points nowhere useful."""
    with pytest.raises(ValueError, match="trailing slash"):
        Settings(**PROD, frontend_origins="https://dashboard.example.com/")


def test_production_requires_at_least_one_origin():
    with pytest.raises(ValueError, match="exact dashboard origin"):
        Settings(**PROD, frontend_origins="")


def test_production_accepts_exact_https_origins():
    settings = Settings(
        **PROD,
        frontend_origins="https://tz.example.com,https://tz-staging.example.com",
    )
    assert settings.cors_origins == [
        "https://tz.example.com",
        "https://tz-staging.example.com",
    ]


def test_local_development_keeps_its_localhost_origin():
    settings = Settings(app_env="development")
    assert settings.cors_origins == ["http://localhost:5174"]
