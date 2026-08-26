"""Ingestion contract, persistence, idempotency, limits, CORS."""

import json


def test_valid_package_returns_202_with_investigation_id(client, sample_package):
    res = client.post("/api/v1/investigations", json=sample_package)
    assert res.status_code == 202
    body = res.json()
    assert body["investigation_id"].startswith("INV-")
    assert body["status"] == "received"
    assert body["received_at"]


def test_investigation_persists_and_is_retrievable(client, sample_package):
    inv_id = client.post("/api/v1/investigations", json=sample_package).json()[
        "investigation_id"
    ]
    res = client.get(f"/api/v1/investigations/{inv_id}")
    assert res.status_code == 200
    inv = res.json()
    assert inv["id"] == inv_id
    assert inv["testName"] == sample_package["test"]["name"]
    assert inv["evidence"]["message"] == sample_package["failure"]["message"]


def test_list_includes_created_investigation(client, sample_package):
    inv_id = client.post("/api/v1/investigations", json=sample_package).json()[
        "investigation_id"
    ]
    ids = [i["id"] for i in client.get("/api/v1/investigations").json()]
    assert inv_id in ids


def test_response_uses_frontend_camel_case_contract(client, sample_package):
    inv_id = client.post("/api/v1/investigations", json=sample_package).json()[
        "investigation_id"
    ]
    inv = client.get(f"/api/v1/investigations/{inv_id}").json()
    for key in (
        "testName",
        "testFile",
        "commitSha",
        "runId",
        "createdAt",
        "releaseRisk",
        "similarFailures",
        "recommendedAction",
        "actionHistory",
    ):
        assert key in inv, key
    assert "confidenceExplanation" in inv["rootCause"]
    assert "nextStep" in inv["rootCause"]
    assert "approvalState" in inv["recommendedAction"]
    # snake_case variants must not leak into the payload
    assert "test_name" not in inv and "release_risk" not in inv


def test_duplicate_package_returns_same_investigation(client, sample_package):
    first = client.post("/api/v1/investigations", json=sample_package).json()
    second = client.post("/api/v1/investigations", json=sample_package).json()
    assert first["investigation_id"] == second["investigation_id"]
    assert len(client.get("/api/v1/investigations").json()) == 1


def test_duplicate_idempotency_key_returns_same_investigation(
    client, sample_package
):
    """Replaying the SAME package under the same key is idempotent.
    (Reusing a key for different evidence is a 409 — see test_hardening.)"""
    headers = {"Idempotency-Key": "run-12345-attempt-1"}
    first = client.post(
        "/api/v1/investigations", json=sample_package, headers=headers
    ).json()
    second = client.post(
        "/api/v1/investigations", json=sample_package, headers=headers
    ).json()
    assert first["investigation_id"] == second["investigation_id"]
    assert len(client.get("/api/v1/investigations").json()) == 1


def test_request_size_limit_enforced(make_client, sample_package):
    client = make_client(MAX_REQUEST_BYTES="1000")
    sample_package["failure"]["stack_trace"] = "x" * 5000
    res = client.post("/api/v1/investigations", json=sample_package)
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "request_too_large"


def test_persistence_survives_new_app_instance(make_client, sample_package):
    first_client = make_client()
    inv_id = first_client.post("/api/v1/investigations", json=sample_package).json()[
        "investigation_id"
    ]
    second_client = make_client()  # fresh engine + app over the same sqlite file
    res = second_client.get(f"/api/v1/investigations/{inv_id}")
    assert res.status_code == 200
    assert res.json()["status"] in ("completed", "needs_review")


def test_cors_allows_configured_origin_only(client):
    allowed = client.get(
        "/api/v1/health", headers={"Origin": "http://localhost:5174"}
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5174"
    denied = client.get(
        "/api/v1/health", headers={"Origin": "https://evil.example.com"}
    )
    assert "access-control-allow-origin" not in denied.headers


def test_unknown_investigation_returns_404(client):
    res = client.get("/api/v1/investigations/INV-DOESNOTEXIST")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"


def test_original_evidence_retained_for_audit(client, sample_package):
    inv_id = client.post("/api/v1/investigations", json=sample_package).json()[
        "investigation_id"
    ]
    from app.db.session import new_session
    from app.repositories.investigations import get

    session = new_session()
    try:
        record = get(session, inv_id)
        stored = json.loads(record.package_json)
        assert stored["failure"]["message"] == sample_package["failure"]["message"]
        assert stored["run"]["run_id"] == sample_package["run"]["run_id"]
    finally:
        session.close()
