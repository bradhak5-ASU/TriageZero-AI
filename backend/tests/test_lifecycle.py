"""Retry, action decisions, timeline, similar failures, health."""


def create(client, pkg):
    return client.post("/api/v1/investigations", json=pkg).json()["investigation_id"]


def test_retry_reruns_analysis(client, sample_package):
    inv_id = create(client, sample_package)
    res = client.post(f"/api/v1/investigations/{inv_id}/retry")
    assert res.status_code == 200
    inv = client.get(f"/api/v1/investigations/{inv_id}").json()
    assert inv["status"] in ("completed", "needs_review")
    assert inv["classification"] == "backend_application_defect"
    labels = [t["label"] for t in inv["timeline"]]
    assert "Retry requested" in labels
    assert inv["evidence"]["message"] == sample_package["failure"]["message"]


def test_retry_of_active_investigation_is_rejected(client, sample_package):
    inv_id = create(client, sample_package)

    from app.db.session import new_session
    from app.repositories.investigations import get

    session = new_session()
    try:
        record = get(session, inv_id)
        record.status = "analyzing"
        session.commit()
    finally:
        session.close()

    res = client.post(f"/api/v1/investigations/{inv_id}/retry")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "retry_conflict"


def test_retry_unknown_returns_404(client):
    assert client.post("/api/v1/investigations/INV-NOPE/retry").status_code == 404


def test_approve_decision_is_persisted(client, sample_package):
    inv_id = create(client, sample_package)
    res = client.post(f"/api/v1/investigations/{inv_id}/actions/approve")
    assert res.status_code == 200
    inv = res.json()
    assert inv["recommendedAction"]["approvalState"] == "approved"
    last = inv["actionHistory"][-1]
    assert last["state"] == "approved"
    assert "no external action" in last["note"].lower()
    # persisted, not just echoed
    again = client.get(f"/api/v1/investigations/{inv_id}").json()
    assert again["recommendedAction"]["approvalState"] == "approved"


def test_reject_decision_is_persisted(client, sample_package):
    inv_id = create(client, sample_package)
    inv = client.post(f"/api/v1/investigations/{inv_id}/actions/reject").json()
    assert inv["recommendedAction"]["approvalState"] == "rejected"


def test_action_on_unknown_investigation_returns_404(client):
    assert (
        client.post("/api/v1/investigations/INV-NOPE/actions/approve").status_code
        == 404
    )


def test_invalid_decision_rejected(client, sample_package):
    inv_id = create(client, sample_package)
    assert (
        client.post(f"/api/v1/investigations/{inv_id}/actions/execute").status_code
        == 422
    )


def test_timeline_records_full_pipeline(client, sample_package):
    inv_id = create(client, sample_package)
    labels = [
        t["label"]
        for t in client.get(f"/api/v1/investigations/{inv_id}").json()["timeline"]
    ]
    for expected in (
        "Failure received",
        "Evidence validated",
        "Investigation queued",
        "Analysis started",
        "Classification completed",
        "Similarity search completed",
        "Release risk calculated",
        "Recommendation produced",
    ):
        assert expected in labels, expected


def test_similar_failures_rank_matching_investigation(client, sample_package):
    """Only human-reviewed history informs a later investigation, so the first
    case must be resolved before it can be retrieved as a similar failure."""
    first_id = create(client, sample_package)
    client.post(
        f"/api/v1/investigations/{first_id}/resolution",
        json={
            "classification": "backend_application_defect",
            "severity": "critical",
            "releaseRisk": "block_release",
            "resolutionSummary": "Orders service raised on missing inventory row.",
            "responsibleComponent": "novacart-api · orders",
            "resolver": "b.radhakrishnan",
        },
    )
    second = dict(sample_package)
    second["run"] = {**sample_package["run"], "run_id": "github-run-22222"}
    second["failure"] = {
        **sample_package["failure"],
        "message": "Expected HTTP 201 but received HTTP 500 again",
    }
    second_id = create(client, second)
    inv = client.get(f"/api/v1/investigations/{second_id}").json()
    similar_ids = [s["id"] for s in inv["similarFailures"]]
    assert first_id in similar_ids
    top = inv["similarFailures"][0]
    assert 0 < top["similarity"] <= 0.97
    assert top["classification"] == "backend_application_defect"
    # matches are explainable: the signals that fired are reported
    assert top["matchingSignals"]
    assert "same_test_file" in top["matchingSignals"]


def test_unreviewed_investigations_do_not_enter_retrieval(client, sample_package):
    """An unreviewed AI prediction must never become 'truth' for a later case."""
    create(client, sample_package)
    second = dict(sample_package)
    second["run"] = {**sample_package["run"], "run_id": "github-run-33333"}
    second["failure"] = {
        **sample_package["failure"],
        "message": "Expected HTTP 201 but received HTTP 500 v3",
    }
    second_id = create(client, second)
    inv = client.get(f"/api/v1/investigations/{second_id}").json()
    assert inv["similarFailures"] == []


def test_health_matches_frontend_snapshot_shape(client, sample_package):
    create(client, sample_package)
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    health = res.json()
    assert health["status"] == "ok"
    assert health["overall"] in ("healthy", "degraded", "offline", "disabled")
    for key in (
        "services",
        "queueDepth",
        "workerThroughputPerMin",
        "ingestionLastHour",
        "ingestionVolume",
        "events",
    ):
        assert key in health, key
    assert health["ingestionLastHour"] >= 1
    by_id = {s["id"]: s for s in health["services"]}
    for disabled in ("gemini", "adk", "pubsub", "firestore", "storage", "github"):
        assert by_id[disabled]["status"] == "disabled"
    assert by_id["ingestion-api"]["status"] == "healthy"


def test_list_filters_and_limits(client, sample_package):
    create(client, sample_package)
    assert (
        len(
            client.get(
                "/api/v1/investigations",
                params={"classification": "backend_application_defect"},
            ).json()
        )
        == 1
    )
    assert (
        client.get("/api/v1/investigations", params={"status": "completed"}).json()
    )
    assert client.get("/api/v1/investigations", params={"search": "checkout"}).json()
    assert client.get("/api/v1/investigations", params={"limit": "9999"}).status_code == 422
    assert client.get("/api/v1/investigations", params={"status": "bogus"}).status_code == 422
