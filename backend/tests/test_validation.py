"""Package validation: schema rules, oracle rejection, artifact safety."""


def post(client, pkg, **kwargs):
    return client.post("/api/v1/investigations", json=pkg, **kwargs)


def test_top_level_oracle_field_rejected(client, sample_package):
    sample_package["expected_classification"] = "backend_application_defect"
    res = post(client, sample_package)
    assert res.status_code == 422
    body = res.json()["error"]
    assert body["code"] == "private_oracle_fields"
    assert "expected_classification" in body["details"]["forbidden_fields"]


def test_nested_oracle_field_rejected(client, sample_package):
    sample_package["failure"]["private_oracle"] = {"scenario_name": "controlled-500"}
    res = post(client, sample_package)
    assert res.status_code == 422
    forbidden = res.json()["error"]["details"]["forbidden_fields"]
    assert "failure.private_oracle" in forbidden
    assert "failure.private_oracle.scenario_name" in forbidden


def test_every_forbidden_key_detected_deeply(client, sample_package):
    from app.services.evidence import FORBIDDEN_ORACLE_FIELDS

    for key in FORBIDDEN_ORACLE_FIELDS:
        pkg = dict(sample_package)
        pkg["run"] = {**sample_package["run"], "meta": [{"deep": {key: True}}]}
        res = post(client, pkg)
        assert res.status_code == 422, key
        assert res.json()["error"]["code"] == "private_oracle_fields"


def test_oracle_package_is_not_persisted(client, sample_package):
    sample_package["controlled_defect"] = True
    assert post(client, sample_package).status_code == 422
    assert client.get("/api/v1/investigations").json() == []


def test_oracle_values_never_echoed(client, sample_package):
    sample_package["defect_scenario"] = "SECRET-SCENARIO-VALUE"
    res = post(client, sample_package)
    assert "SECRET-SCENARIO-VALUE" not in res.text


def test_invalid_schema_version_rejected(client, sample_package):
    sample_package["schema_version"] = "2.0"
    res = post(client, sample_package)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_error"


def test_missing_required_fields_rejected(client):
    res = post(client, {"schema_version": "1.0", "source": "x"})
    assert res.status_code == 422
    fields = [d["field"] for d in res.json()["error"]["details"]]
    assert any("test" in f for f in fields)
    assert any("repository" in f for f in fields)


def test_non_failed_test_rejected(client, sample_package):
    sample_package["test"]["status"] = "passed"
    res = post(client, sample_package)
    assert res.status_code == 422
    assert "failed" in res.text


def test_invalid_network_status_rejected(client, sample_package):
    sample_package["network_evidence"] = [{"method": "GET", "url": "/x", "status": 99}]
    assert post(client, sample_package).status_code == 422


def test_absolute_artifact_path_rejected(client, sample_package):
    sample_package["artifacts"]["screenshot_path"] = "/etc/passwd"
    res = post(client, sample_package)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "invalid_artifact_path"


def test_traversal_artifact_path_rejected(client, sample_package):
    sample_package["artifacts"]["trace_path"] = "test-results/../../secrets/trace.zip"
    assert post(client, sample_package).status_code == 422


def test_file_url_and_home_artifact_paths_rejected(client, sample_package):
    for bad in ("file:///tmp/x.png", "~/screenshots/x.png", "C:\\evidence\\x.png"):
        pkg = dict(sample_package)
        pkg["artifacts"] = {"screenshot_path": bad}
        assert post(client, pkg).status_code == 422, bad


def test_safe_relative_artifact_path_accepted(client, sample_package):
    sample_package["artifacts"]["screenshot_path"] = "test-results\\run\\shot.png"
    res = post(client, sample_package)
    assert res.status_code == 202
    inv = client.get(f"/api/v1/investigations/{res.json()['investigation_id']}").json()
    paths = [a["path"] for a in inv["evidence"]["artifacts"]]
    assert "test-results/run/shot.png" in paths


def test_invalid_json_rejected(client):
    res = client.post(
        "/api/v1/investigations",
        content=b"{not json",
        headers={"content-type": "application/json"},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "invalid_json"
