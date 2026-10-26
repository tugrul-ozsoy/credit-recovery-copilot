"""Web API tests (offline, no AI calls): uses the saved real extraction fixtures, never the live model."""

import json
import shutil

import pytest
from fastapi.testclient import TestClient

import app.review as review
import app.server as server

FIX = "tests/fixtures"


@pytest.fixture
def client(tmp_path, monkeypatch):
    runs = tmp_path / "extractions"
    runs.mkdir()
    for name, stem in (("ww_extraction_real.json", "ww_international-43489932c7e0"),
                       ("enviva_extraction_real.json", "enviva-aaf49a80efc2")):
        shutil.copy(f"{FIX}/{name}", runs / f"{stem}.json")
    monkeypatch.setattr(server, "EXTRACTIONS", runs)
    monkeypatch.setattr(review, "CORRECTIONS_LOG", tmp_path / "corrections.json")
    monkeypatch.setattr(server, "save", lambda rec: _save(rec, runs))  # reviewed files land in tmp
    return TestClient(server.app)


def _save(rec, runs):  # same naming rule as app.review.save, but inside the test's temp folder
    n = len(rec['corrections'])
    path = runs / f"{rec['case']}-{rec['run_id']}-reviewed-{n}.json"
    while path.exists():
        n += 1
        path = runs / f"{rec['case']}-{rec['run_id']}-reviewed-{n}.json"
    path.write_text(json.dumps(rec), encoding="utf-8")
    return path


def test_page_and_cases(client):
    assert "Credit Recovery Decision Copilot" in client.get("/").text
    cases = client.get("/api/cases").json()
    assert [c["slug"] for c in cases] == ["ww_international", "wolfspeed", "enviva", "dean_foods"]
    assert all(c["url"].startswith(("https://www.sec.gov/", "https://document.epiq11.com/")) for c in cases)


def test_run_view_keeps_extraction_and_reference_separate(client):
    v = client.get("/api/runs/ww_international-43489932c7e0").json()
    assert v["result"]["assessment"]["status"] == "reconciled"
    assert v["reference_check"]["correct"] == v["reference_check"]["fields_scored"] == 108
    assert set(v["result"]["provenance"].values()) == {"extracted", "computed (code)"}
    assert [s["by"] for s in v["activity"]] == ["code", "code", "gpt-6-luna", "code", "engine"]


def test_bad_run_names_are_rejected(client):
    assert client.get("/api/runs/..%2F..%2Fdata%2Fprices").status_code in (400, 404)
    assert client.get("/api/runs/not-a-run").status_code == 400


def test_stress_moves_nothing_unless_asked_and_validates_inputs(client):
    url = "/api/runs/ww_international-43489932c7e0/scenario"
    r = client.post(url, json={"scenario": 0}).json()
    assert r["base"] == r["stressed"]
    r = client.post(url, json={"scenario": 0, "asset_pct": {"Accounts Receivable": 100}}).json()
    assert r["stressed"]["gross_proceeds"] - r["base"]["gross_proceeds"] == pytest.approx(13568 - 5427)
    assert client.post(url, json={"scenario": 0, "asset_pct": {"Not an asset": 5}}).status_code == 400
    assert client.post(url, json={"scenario": 9}).status_code == 400


def test_correction_needs_a_name_and_keeps_failure_visible(client):
    url = "/api/runs/enviva-aaf49a80efc2/corrections"
    assert client.post(url, json={"by": "", "corrections": [{"field": "claims[1].priority", "value": 2}]}).status_code == 422
    v = client.post(url, json={"by": "Test Reviewer", "corrections": [{"field": "claims[1].priority", "value": 2}]}).json()
    assert v["name"].endswith("-reviewed-1")
    assert v["result"]["provenance"]["claims[1].priority"] == "corrected by Test Reviewer"
    assert v["result"]["assessment"]["status"] == "needs_review"  # a correction never forces a reconciliation
    assert any(s["by"] == "person: Test Reviewer" for s in v["activity"])


def test_live_runs_are_rate_limited(client, monkeypatch):
    monkeypatch.setattr(server, "MAX_LIVE_RUNS_PER_HOUR", 0)
    monkeypatch.setattr(server, "extract", lambda *a, **k: pytest.fail("the model must not be called"))
    assert client.post("/api/cases/ww_international/extract").status_code == 429


def test_missing_api_key_returns_a_clear_503_and_the_server_stays_up(client, monkeypatch):
    def no_key(*a, **k):
        raise SystemExit("PORTKEY_API_KEY is not set. Put it in a .env file in this folder or the folder above it.")
    monkeypatch.setattr(server, "extract", no_key)
    r = client.post("/api/cases/ww_international/extract")
    assert r.status_code == 503 and "PORTKEY_API_KEY" in r.json()["detail"] and "Saved runs" in r.json()["detail"]
    assert client.get("/api/cases").status_code == 200  # still serving
    assert client.post("/api/cases/ww_international/extract").status_code == 503  # the run lock was released


def test_blanking_filed_values_cannot_force_a_reconciliation(client):
    """Regression (audit F1): a reviewer used to be able to blank the cells that disagree and turn Enviva RECONCILED."""
    v = client.get("/api/runs/enviva-aaf49a80efc2").json()
    a = v["result"]["analysis"]
    fails = [w["message"] for w in v["result"]["assessment"]["warnings"] if w["kind"] == "reconciliation"]
    corrections = []
    for i, c in enumerate(a["claims"]):
        for j, s in enumerate(a["scenarios"]):
            if any(m.startswith(f"{s}: {c['label']}:") for m in fails):
                corrections += [{"field": f"claims[{i}].filed_recovery_pct[{j}]", "value": None},
                                {"field": f"claims[{i}].filed_recovery_value[{j}]", "value": None}]
    assert corrections
    r = client.post("/api/runs/enviva-aaf49a80efc2/corrections", json={"by": "Test Reviewer", "corrections": corrections[:60]})
    assessment = r.json()["result"]["assessment"]
    assert assessment["status"] == "needs_review" and not assessment["reconciles_with_filed"]
    assert any("no filed recovery to check" in w["message"] for w in assessment["warnings"])


def test_rounding_step_is_not_correctable_and_reviews_never_overwrite(client):
    url = "/api/runs/enviva-aaf49a80efc2/corrections"
    assert client.post(url, json={"by": "T", "corrections": [{"field": "rounding_step", "value": 1000}]}).status_code == 400
    first = client.post(url, json={"by": "T", "corrections": [{"field": "claims[1].priority", "value": 2}]}).json()["name"]
    second = client.post(url, json={"by": "T", "corrections": [{"field": "claims[2].priority", "value": 2}]}).json()["name"]
    assert first != second  # the second review of the same run gets its own file


def test_cross_site_posts_are_refused_without_calling_the_model(client, monkeypatch):
    monkeypatch.setattr(server, "extract", lambda *a, **k: pytest.fail("the model must not be called"))
    evil = {"Origin": "https://evil.example"}
    assert client.post("/api/cases/ww_international/extract", headers=evil).status_code == 403
    body = {"by": "T", "corrections": [{"field": "claims[1].priority", "value": 2}]}
    assert client.post("/api/runs/enviva-aaf49a80efc2/corrections", json=body, headers=evil).status_code == 403
    long_field = {"by": "T", "corrections": [{"field": "x" * 81, "value": 1}]}
    assert client.post("/api/runs/enviva-aaf49a80efc2/corrections", json=long_field).status_code == 422
