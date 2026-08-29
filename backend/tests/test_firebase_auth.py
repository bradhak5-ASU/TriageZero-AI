"""Firebase ID-token verification on dashboard routes.

Every test here is offline: a fake verifier is installed, so nothing contacts
Firebase, Google's public keys, or the network. The point of these tests is the
*separation* — a machine ingestion token must never open the dashboard, and a
human ID token must never be required of CI.
"""

import pytest

from app.core.firebase_auth import (
    FirebaseAuthError,
    VerifiedUser,
    firebase_enabled,
    reset_firebase_app,
    set_token_verifier,
    verify_id_token,
)

INGESTION = "i" * 40
DASHBOARD = "d" * 40
GOOD_ID_TOKEN = "firebase-id-token-for-a-signed-in-user"
EXPIRED_ID_TOKEN = "expired-firebase-id-token"

AUTH_ENV = {
    "API_AUTH_REQUIRED": "true",
    "INGESTION_API_TOKEN": INGESTION,
    "DASHBOARD_API_TOKEN": DASHBOARD,
    "FIREBASE_AUTH_ENABLED": "true",
    "FIREBASE_PROJECT_ID": "triagezero",
}


def fake_verifier(token: str) -> VerifiedUser:
    """Stands in for Firebase Admin. Never leaves the process."""
    if token == GOOD_ID_TOKEN:
        return VerifiedUser(uid="demo-user-1", email="demo@example.com", email_verified=True)
    if token == EXPIRED_ID_TOKEN:
        raise FirebaseAuthError("token expired")
    raise FirebaseAuthError("invalid token")


@pytest.fixture(autouse=True)
def offline_verifier():
    set_token_verifier(fake_verifier)
    yield
    set_token_verifier(None)
    reset_firebase_app()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- configuration ---------------------------------------------------------


def test_firebase_is_disabled_by_default(client):
    """Local development and the existing suite need no Firebase project."""
    from app.core.config import get_settings

    assert get_settings().firebase_auth_enabled is False


def test_enabling_firebase_without_a_project_id_is_rejected():
    from app.core.config import Settings

    with pytest.raises(ValueError, match="FIREBASE_PROJECT_ID"):
        Settings(firebase_auth_enabled=True, firebase_project_id="", google_cloud_project="")


def test_enabling_firebase_with_a_project_id_is_accepted():
    from app.core.config import Settings

    settings = Settings(firebase_auth_enabled=True, firebase_project_id="triagezero")
    assert settings.firebase_auth_enabled is True


def test_firebase_enabled_reports_configuration_state(make_client):
    make_client(**AUTH_ENV)
    assert firebase_enabled() is True


# --- dashboard access with an ID token -------------------------------------


def test_valid_id_token_opens_the_dashboard(make_client, sample_package):
    client = make_client(**AUTH_ENV)
    client.post("/api/v1/investigations", json=sample_package, headers=bearer(INGESTION))

    listed = client.get("/api/v1/investigations", headers=bearer(GOOD_ID_TOKEN))

    assert listed.status_code == 200
    assert isinstance(listed.json(), list)


def test_missing_token_is_401(make_client):
    client = make_client(**AUTH_ENV)
    assert client.get("/api/v1/investigations").status_code == 401


def test_malformed_authorization_header_is_401(make_client):
    client = make_client(**AUTH_ENV)
    for header in ({"Authorization": GOOD_ID_TOKEN}, {"Authorization": "Bearer "},
                   {"Authorization": "Basic abc"}):
        assert client.get("/api/v1/investigations", headers=header).status_code == 401


def test_expired_id_token_is_401_not_403(make_client):
    """An expired credential failed to AUTHENTICATE — it is not an
    authorization problem, and the frontend refreshes on 401."""
    client = make_client(**AUTH_ENV)
    res = client.get("/api/v1/investigations", headers=bearer(EXPIRED_ID_TOKEN))
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "authentication_failed"


def test_garbage_id_token_is_401(make_client):
    client = make_client(**AUTH_ENV)
    assert client.get(
        "/api/v1/investigations", headers=bearer("not-a-real-token")
    ).status_code == 401


def test_token_contents_are_never_echoed(make_client):
    client = make_client(**AUTH_ENV)
    secret_looking = "eyJhbGciOiJIUzI1NiJ9.SUPERSECRETPAYLOAD.sig"
    res = client.get("/api/v1/investigations", headers=bearer(secret_looking))
    assert res.status_code == 401
    assert "SUPERSECRETPAYLOAD" not in res.text


# --- the separation that matters -------------------------------------------


def test_ingestion_token_still_cannot_read_the_dashboard(make_client):
    """The machine credential must stay machine-only even with Firebase on."""
    client = make_client(**AUTH_ENV)
    res = client.get("/api/v1/investigations", headers=bearer(INGESTION))
    assert res.status_code == 403


def test_ingestion_token_still_works_for_ci_without_firebase(make_client, sample_package):
    """CI must never need a Firebase identity."""
    client = make_client(**AUTH_ENV)
    res = client.post(
        "/api/v1/investigations", json=sample_package, headers=bearer(INGESTION)
    )
    assert res.status_code == 202


def test_signed_in_human_may_use_the_manual_ingest_page(make_client, sample_package):
    client = make_client(**AUTH_ENV)
    res = client.post(
        "/api/v1/investigations", json=sample_package, headers=bearer(GOOD_ID_TOKEN)
    )
    assert res.status_code == 202


def test_dashboard_service_token_still_works(make_client, sample_package):
    """Break-glass/scripting credential is unaffected by Firebase."""
    client = make_client(**AUTH_ENV)
    created = client.post(
        "/api/v1/investigations", json=sample_package, headers=bearer(DASHBOARD)
    )
    listed = client.get("/api/v1/investigations", headers=bearer(DASHBOARD))
    assert created.status_code == 202
    assert listed.status_code == 200


def test_id_token_is_rejected_when_firebase_is_disabled(make_client, sample_package):
    """With Firebase off, an ID token is just an unrecognized bearer token."""
    client = make_client(
        API_AUTH_REQUIRED="true",
        INGESTION_API_TOKEN=INGESTION,
        DASHBOARD_API_TOKEN=DASHBOARD,
        FIREBASE_AUTH_ENABLED="false",
    )
    assert client.get(
        "/api/v1/investigations", headers=bearer(GOOD_ID_TOKEN)
    ).status_code == 403


def test_all_dashboard_routes_are_protected(make_client, sample_package):
    client = make_client(**AUTH_ENV)
    inv = client.post(
        "/api/v1/investigations", json=sample_package, headers=bearer(INGESTION)
    ).json()["investigation_id"]

    for method, path in (
        ("get", "/api/v1/investigations"),
        ("get", f"/api/v1/investigations/{inv}"),
        ("post", f"/api/v1/investigations/{inv}/retry"),
        ("post", f"/api/v1/investigations/{inv}/actions/approve"),
    ):
        anonymous = getattr(client, method)(path)
        assert anonymous.status_code == 401, path
        with_ingestion = getattr(client, method)(path, headers=bearer(INGESTION))
        assert with_ingestion.status_code == 403, path


def test_health_stays_open_for_platform_probes(make_client):
    """Cloud Run startup/liveness probes are unauthenticated by design."""
    client = make_client(**AUTH_ENV)
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert "token" not in res.text.lower()


# --- offline guarantee ------------------------------------------------------


def test_no_network_call_is_made_during_verification(monkeypatch):
    """Fail loudly if a test ever tries to reach Firebase for real."""
    import socket

    def blocked(*args, **kwargs):  # pragma: no cover - only runs on regression
        raise AssertionError("a test attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    assert verify_id_token(GOOD_ID_TOKEN).uid == "demo-user-1"


def test_default_verifier_is_not_constructed_at_import():
    """Importing the module must not initialize Firebase Admin."""
    import app.core.firebase_auth as module

    assert module._app is None
