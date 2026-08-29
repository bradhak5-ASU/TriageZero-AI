import pytest

from app.core.config import Settings

INGESTION_TOKEN = "ingestion-token-0123456789-abcdef-XYZ"
DASHBOARD_TOKEN = "dashboard-token-0123456789-abcdef-XYZ"
#: Any non-SQLite URL satisfies the production durability check. Nothing here
#: connects to it - these tests only construct Settings.
DURABLE_DATABASE_URL = "postgresql+psycopg://u:p@db.internal:5432/triagezero"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def auth_env() -> dict[str, str]:
    return {
        "API_AUTH_REQUIRED": "true",
        "INGESTION_API_TOKEN": INGESTION_TOKEN,
        "DASHBOARD_API_TOKEN": DASHBOARD_TOKEN,
    }


def test_local_auth_is_optional_by_default():
    settings = Settings(
        app_env="development",
        api_auth_required=False,
        ingestion_api_token="",
        dashboard_api_token="",
    )
    assert settings.api_auth_required is False


def test_production_fails_closed_without_authentication():
    with pytest.raises(ValueError, match="API_AUTH_REQUIRED"):
        Settings(
            app_env="production",
            api_auth_required=False,
            ingestion_api_token="",
            dashboard_api_token="",
        )


@pytest.mark.parametrize(
    "ingestion,dashboard,match",
    [
        ("short", DASHBOARD_TOKEN, "at least 32"),
        (INGESTION_TOKEN, "short", "at least 32"),
        (INGESTION_TOKEN, INGESTION_TOKEN, "must be different"),
    ],
)
def test_enabled_auth_requires_strong_distinct_tokens(ingestion, dashboard, match):
    with pytest.raises(ValueError, match=match):
        Settings(
            app_env="production",
            api_auth_required=True,
            ingestion_api_token=ingestion,
            dashboard_api_token=dashboard,
        )


def test_secret_tokens_are_masked_in_settings_representation():
    settings = Settings(
        app_env="production",
        # production also requires a durable database - see test_postgres_support
        database_url=DURABLE_DATABASE_URL,
        frontend_origins="https://tz.example.com",
        api_auth_required=True,
        ingestion_api_token=INGESTION_TOKEN,
        dashboard_api_token=DASHBOARD_TOKEN,
    )
    rendered = repr(settings)
    assert INGESTION_TOKEN not in rendered
    assert DASHBOARD_TOKEN not in rendered


def test_ingestion_requires_a_valid_bearer_token(make_client, sample_package):
    client = make_client(**auth_env())

    missing = client.post("/api/v1/investigations", json=sample_package)
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "authentication_required"

    malformed = client.post(
        "/api/v1/investigations",
        json=sample_package,
        headers={"Authorization": INGESTION_TOKEN},
    )
    assert malformed.status_code == 401

    wrong = client.post(
        "/api/v1/investigations", json=sample_package, headers=bearer("x" * 40)
    )
    assert wrong.status_code == 403
    assert wrong.json()["error"]["code"] == "forbidden"

    accepted = client.post(
        "/api/v1/investigations", json=sample_package, headers=bearer(INGESTION_TOKEN)
    )
    assert accepted.status_code == 202


def test_ingestion_token_cannot_read_or_mutate_investigations(make_client, sample_package):
    client = make_client(**auth_env())
    created = client.post(
        "/api/v1/investigations", json=sample_package, headers=bearer(INGESTION_TOKEN)
    )
    investigation_id = created.json()["investigation_id"]

    denied = client.get(
        f"/api/v1/investigations/{investigation_id}", headers=bearer(INGESTION_TOKEN)
    )
    assert denied.status_code == 403

    allowed = client.get(
        f"/api/v1/investigations/{investigation_id}", headers=bearer(DASHBOARD_TOKEN)
    )
    assert allowed.status_code == 200


def test_dashboard_token_can_ingest_and_list(make_client, sample_package):
    client = make_client(**auth_env())
    created = client.post(
        "/api/v1/investigations", json=sample_package, headers=bearer(DASHBOARD_TOKEN)
    )
    assert created.status_code == 202
    listed = client.get("/api/v1/investigations", headers=bearer(DASHBOARD_TOKEN))
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_health_remains_secret_free_and_available_for_platform_probes(make_client):
    client = make_client(**auth_env())
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.text
    assert INGESTION_TOKEN not in body
    assert DASHBOARD_TOKEN not in body
