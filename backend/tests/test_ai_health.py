"""Health reporting, credential hygiene, and seeding safeguards."""

import json
from pathlib import Path

import pytest

from app.ai.telemetry import telemetry
from app.evaluation.seed_history import reset_synthetic, seed


@pytest.fixture(autouse=True)
def clean_telemetry():
    telemetry.reset()
    yield
    telemetry.reset()


def test_health_reports_ai_state_truthfully_without_credentials(client):
    ai = client.get("/api/v1/health").json()["ai"]
    assert ai["analyzerMode"] == "deterministic"
    assert ai["deterministicStatus"] == "healthy"
    # not selected → disabled, and never claimed healthy
    assert ai["geminiStatus"] == "disabled"
    assert ai["adkStatus"] == "disabled"
    assert ai["fallbackEnabled"] is True
    assert ai["modelName"]
    assert ai["fallbackCount"] == 0


def test_health_says_unconfigured_when_mode_selected_without_credentials(make_client):
    client = make_client(ANALYZER_MODE="gemini", GEMINI_API_KEY="")
    ai = client.get("/api/v1/health").json()["ai"]
    assert ai["analyzerMode"] == "gemini"
    # honest: selected but unusable — never "healthy"
    assert ai["geminiStatus"] == "unconfigured"
    assert ai["geminiStatus"] != "healthy"


def test_health_service_list_marks_gemini_and_adk(client):
    services = {s["id"]: s for s in client.get("/api/v1/health").json()["services"]}
    assert services["gemini"]["status"] == "disabled"
    assert services["adk"]["status"] == "disabled"
    assert services["analyzer"]["status"] == "healthy"
    assert "ANALYZER_MODE" in services["gemini"]["detail"]


def test_health_never_exposes_credentials(make_client):
    secret = "AIzaSyTOPSECRETKEYVALUE1234567890"
    client = make_client(ANALYZER_MODE="gemini", GEMINI_API_KEY=secret)
    body = client.get("/api/v1/health").text

    assert secret not in body
    assert secret[:6] not in body  # no prefix
    assert secret[-6:] not in body  # no suffix
    assert str(len(secret)) not in json.dumps(client.get("/api/v1/health").json()["ai"])
    lowered = body.lower()
    assert "api_key" not in lowered and "apikey" not in lowered


def test_configured_provider_is_unverified_until_a_call_succeeds(make_client):
    client = make_client(ANALYZER_MODE="gemini", GEMINI_API_KEY="placeholder")
    health = client.get("/api/v1/health").json()
    assert health["ai"]["geminiStatus"] == "unverified"
    service = next(item for item in health["services"] if item["id"] == "gemini")
    assert service["status"] == "degraded"
    assert "no successful provider call" in service["detail"].lower()


def test_health_reports_fallback_count_after_a_fallback(make_client, sample_package):
    client = make_client(ANALYZER_MODE="gemini", GEMINI_API_KEY="")
    client.post("/api/v1/investigations", json=sample_package)
    ai = client.get("/api/v1/health").json()["ai"]
    assert ai["fallbackCount"] >= 1
    assert ai["lastErrorCode"] == "unconfigured"


def test_unconfigured_gemini_mode_still_produces_investigations(make_client, sample_package):
    """The app must work end to end with no credentials at all."""
    client = make_client(ANALYZER_MODE="gemini", AI_FALLBACK_ENABLED="false", GEMINI_API_KEY="")
    inv_id = client.post("/api/v1/investigations", json=sample_package).json()["investigation_id"]
    inv = client.get(f"/api/v1/investigations/{inv_id}").json()

    assert inv["status"] == "needs_review"
    meta = inv["aiMetadata"]
    assert meta["provider"] == "gemini"
    assert meta["usedFallback"] is False
    assert meta["fallbackReason"] == "unconfigured"
    # never claims deterministic fallback ran when fallback is disabled
    assert meta["provider"] != "deterministic_fallback"


def test_health_reports_corpus_size_and_datasets(client):
    ai = client.get("/api/v1/health").json()["ai"]
    assert isinstance(ai["historicalCorpusSize"], int)
    assert isinstance(ai["evaluationDatasets"], list)


# --- seeding safeguards ----------------------------------------------------


def test_seeding_refuses_production_mode(monkeypatch, tmp_path):
    from app.core.config import get_settings

    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    with pytest.raises(SystemExit, match="Refusing to seed"):
        seed(10, 1, database_url=f"sqlite:///{tmp_path}/x.db")
    monkeypatch.setenv("APP_ENV", "development")
    get_settings.cache_clear()


def test_seeded_rows_are_marked_synthetic_and_cleanup_spares_real_rows(
    make_client, sample_package, tmp_path, monkeypatch
):
    db = f"sqlite:///{tmp_path}/seeded.db"
    client = make_client(DATABASE_URL=db)

    # a genuine investigation
    real_id = client.post("/api/v1/investigations", json=sample_package).json()["investigation_id"]

    summary = seed(36, 20260825, database_url=db)
    assert summary["inserted"] > 0

    from app.db.session import new_session
    from app.repositories.investigations import get, synthetic_ids

    session = new_session()
    try:
        synthetic = synthetic_ids(session)
        assert synthetic, "seeded rows should be marked synthetic"
        assert real_id not in synthetic
        assert get(session, real_id).is_synthetic is False
    finally:
        session.close()

    removed = reset_synthetic(database_url=db)
    assert removed == len(synthetic)

    session = new_session()
    try:
        # the genuine investigation survives cleanup
        assert get(session, real_id) is not None
        assert synthetic_ids(session) == []
    finally:
        session.close()


def test_seeding_does_not_duplicate_fingerprints(tmp_path):
    db = f"sqlite:///{tmp_path}/dupes.db"
    first = seed(36, 20260825, database_url=db)
    second = seed(36, 20260825, database_url=db)
    assert first["inserted"] > 0
    assert second["inserted"] == 0
    assert second["skipped_duplicates"] == first["inserted"]


def test_holdout_families_never_enter_the_seeded_corpus(tmp_path):
    from app.evaluation.datasets import HOLDOUT_FAMILIES

    db = f"sqlite:///{tmp_path}/corpus.db"
    seed(90, 20260825, database_url=db)

    from app.db.models import InvestigationRecord
    from app.db.session import new_session

    session = new_session()
    try:
        families = {
            row.synthetic_family
            for row in session.query(InvestigationRecord).all()
            if row.is_synthetic
        }
    finally:
        session.close()
    assert families
    assert not families & set(HOLDOUT_FAMILIES)


def test_evaluation_reports_contain_no_oracle_sentinel(tmp_path, monkeypatch):
    """A report must never embed the private oracle file's contents."""
    from app.evaluation.datasets import ORACLE_DIR, build
    from app.evaluation.run import run_evaluation, write_outputs

    build(36, 20260825)
    sentinel = "ORACLE-FILE-SENTINEL-XYZ"
    oracle_file = ORACLE_DIR / "holdout.oracle.json"
    payload = json.loads(oracle_file.read_text())
    payload["secret_marker"] = sentinel
    oracle_file.write_text(json.dumps(payload))

    report = run_evaluation("evaluation/datasets/holdout.json", "deterministic")
    paths = write_outputs(report, str(tmp_path / "result.json"))

    for path in paths.values():
        assert sentinel not in Path(path).read_text(), path
