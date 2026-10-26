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


def _save(rec, runs):
    path = runs / f"{rec['case']}-{rec['run_id']}-reviewed-{len(rec['corrections'])}.json"
    path.write_text(json.dumps(rec), encoding="utf-8")
    return path


def test_page_and_cases(client):
    assert "Credit Recovery Copilot" in client.get("/").text
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
