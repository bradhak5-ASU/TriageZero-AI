"""Regression tests for the pre-hosting hardening review:
chunked request-size bypass, idempotency-key conflicts and races,
and the strict (closed) v1 package contract."""

import copy

import pytest

from tests.conftest import SAMPLE_PACKAGE


def post(client, pkg, **kwargs):
    return client.post("/api/v1/investigations", json=pkg, **kwargs)


# ---------------------------------------------------------------------------
# request size — chunked bodies carry no Content-Length
# ---------------------------------------------------------------------------


def test_chunked_body_cannot_bypass_size_limit(make_client, sample_package):
    import json as jsonlib

    client = make_client(MAX_REQUEST_BYTES="1000")
    sample_package["failure"]["stack_trace"] = "x" * 8000
    payload = jsonlib.dumps(sample_package).encode()

    def chunks():
        for i in range(0, len(payload), 512):
            yield payload[i : i + 512]

    # a generator body makes httpx send Transfer-Encoding: chunked,
    # so the middleware's Content-Length check cannot see the size
    res = client.post(
        "/api/v1/investigations",
        content=chunks(),
        headers={"content-type": "application/json"},
    )
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "request_too_large"
    assert client.get("/api/v1/investigations").json() == []


def test_chunked_body_within_limit_is_accepted(client, sample_package):
    import json as jsonlib

    payload = jsonlib.dumps(sample_package).encode()

    def chunks():
        yield payload[: len(payload) // 2]
        yield payload[len(payload) // 2 :]

    res = client.post(
        "/api/v1/investigations",
        content=chunks(),
        headers={"content-type": "application/json"},
    )
    assert res.status_code == 202


# ---------------------------------------------------------------------------
# idempotency
# ---------------------------------------------------------------------------


def test_same_key_same_package_is_idempotent(client, sample_package):
    headers = {"Idempotency-Key": "run-1"}
    first = post(client, sample_package, headers=headers).json()
    second = post(client, sample_package, headers=headers)
    assert second.status_code == 202
    assert second.json()["investigation_id"] == first["investigation_id"]
    assert len(client.get("/api/v1/investigations").json()) == 1


def test_same_key_different_evidence_returns_conflict(client, sample_package):
    headers = {"Idempotency-Key": "run-1"}
    first = post(client, sample_package, headers=headers).json()

    other = copy.deepcopy(sample_package)
    other["failure"]["message"] = "a completely different failure"
    res = post(client, other, headers=headers)

    assert res.status_code == 409
    body = res.json()["error"]
    assert body["code"] == "idempotency_key_conflict"
    assert body["details"]["investigation_id"] == first["investigation_id"]
    # the conflicting package must not have been stored
    assert len(client.get("/api/v1/investigations").json()) == 1


def test_concurrent_duplicate_key_creates_one_investigation(
    client, sample_package, monkeypatch
):
    """Simulates two requests passing the pre-check simultaneously: the second
    insert hits the unique constraint and must resolve to the winner rather
    than erroring or duplicating."""
    first = post(client, sample_package, headers={"Idempotency-Key": "race"}).json()

    from app.repositories import investigations as repo
    from app.services import investigations as service

    # capture the genuine lookups before patching
    real_by_key = repo.get_by_idempotency_key
    calls = {"n": 0}

    def flaky_by_key(session, key):
        # first call = the pre-check, which "misses" as it would under a race;
        # later calls = the post-IntegrityError recovery, which must find the winner
        calls["n"] += 1
        return None if calls["n"] == 1 else real_by_key(session, key)

    monkeypatch.setattr(service.repo, "get_by_idempotency_key", flaky_by_key)

    res = post(client, sample_package, headers={"Idempotency-Key": "race"})
    assert res.status_code == 202
    assert res.json()["investigation_id"] == first["investigation_id"]
    assert len(client.get("/api/v1/investigations").json()) == 1


def test_concurrent_duplicate_package_without_key_deduplicates(
    client, sample_package, monkeypatch
):
    first = post(client, sample_package).json()

    from app.repositories import investigations as repo
    from app.services import investigations as service

    real_by_fp = repo.get_by_fingerprint
    calls = {"n": 0}

    def flaky_by_fp(session, fingerprint):
        calls["n"] += 1
        return None if calls["n"] == 1 else real_by_fp(session, fingerprint)

    monkeypatch.setattr(service.repo, "get_by_fingerprint", flaky_by_fp)

    res = post(client, sample_package)
    assert res.status_code == 202
    assert res.json()["investigation_id"] == first["investigation_id"]
    assert len(client.get("/api/v1/investigations").json()) == 1


# ---------------------------------------------------------------------------
# strict closed schema
# ---------------------------------------------------------------------------


def test_unknown_top_level_field_rejected(client, sample_package):
    sample_package["extra_metadata"] = {"anything": True}
    res = post(client, sample_package)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_error"
    assert client.get("/api/v1/investigations").json() == []


@pytest.mark.parametrize(
    "section,field",
    [
        ("run", "operator_notes"),
        ("repository", "internal_id"),
        ("environment", "secrets"),
        ("test", "annotations"),
        ("failure", "raw_dump"),
    ],
)
def test_unknown_nested_field_rejected(client, sample_package, section, field):
    sample_package[section][field] = "unexpected"
    res = post(client, sample_package)
    assert res.status_code == 422
    fields = [d["field"] for d in res.json()["error"]["details"]]
    assert any(field in f for f in fields)


def test_unknown_field_in_network_evidence_rejected(client, sample_package):
    sample_package["network_evidence"][0]["request_body"] = "{...}"
    assert post(client, sample_package).status_code == 422


def test_unknown_artifact_key_rejected(client, sample_package):
    sample_package["artifacts"]["har_path"] = "test-results/run/net.har"
    assert post(client, sample_package).status_code == 422


@pytest.mark.parametrize("browser", ["edge", "Chromium", "", "chrome"])
def test_unsupported_browser_rejected(client, sample_package, browser):
    sample_package["environment"]["browser"] = browser
    res = post(client, sample_package)
    assert res.status_code == 422
    assert any("browser" in d["field"] for d in res.json()["error"]["details"])


@pytest.mark.parametrize("env", ["prod", "qa", "Local", ""])
def test_unsupported_environment_rejected(client, sample_package, env):
    sample_package["environment"]["name"] = env
    res = post(client, sample_package)
    assert res.status_code == 422
    assert any("name" in d["field"] for d in res.json()["error"]["details"])


@pytest.mark.parametrize(
    "browser,env",
    [("chromium", "local"), ("firefox", "staging"), ("webkit", "production")],
)
def test_supported_browser_environment_combinations_accepted(
    client, sample_package, browser, env
):
    sample_package["environment"]["browser"] = browser
    sample_package["environment"]["name"] = env
    sample_package["run"]["run_id"] = f"run-{browser}-{env}"
    res = post(client, sample_package)
    assert res.status_code == 202
    inv = client.get(f"/api/v1/investigations/{res.json()['investigation_id']}").json()
    assert inv["browser"] == browser
    assert inv["environment"] == env


def test_invalid_http_method_rejected(client, sample_package):
    sample_package["network_evidence"][0]["method"] = "PO ST;"
    assert post(client, sample_package).status_code == 422


def test_oracle_rejection_still_takes_precedence_over_strictness(
    client, sample_package
):
    """An oracle key is also an unknown field now; it must still be reported
    with the specific oracle error code, not a generic schema error."""
    sample_package["private_oracle"] = {"scenario_name": "controlled-500"}
    res = post(client, sample_package)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "private_oracle_fields"


def test_canonical_sample_package_still_valid(client):
    res = post(client, copy.deepcopy(SAMPLE_PACKAGE))
    assert res.status_code == 202


def test_key_is_adopted_when_a_duplicate_package_first_supplies_one(client, sample_package):
    """A key attached to a fingerprint-duplicate must not be silently dropped,
    or a later reuse with different evidence would go undetected."""
    first = post(client, sample_package).json()          # no key
    again = post(client, sample_package, headers={"Idempotency-Key": "late-key"}).json()
    assert again["investigation_id"] == first["investigation_id"]

    other = copy.deepcopy(sample_package)
    other["failure"]["message"] = "a different failure entirely"
    res = post(client, other, headers={"Idempotency-Key": "late-key"})

    assert res.status_code == 409
    assert res.json()["error"]["code"] == "idempotency_key_conflict"
    assert len(client.get("/api/v1/investigations").json()) == 1
