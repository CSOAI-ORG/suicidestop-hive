"""Tests for ASI-Evolve hive telemetry consumption and candidate queue."""

import os
import tempfile

from meok_one import asi_evolve_hive, telemetry


def _with_temp_telemetry(tmp_path, monkeypatch):
    log = tmp_path / "telemetry.jsonl"
    monkeypatch.setenv("MEOK_TELEMETRY_LOG", str(log))
    telemetry._TELEMETRY_LOG = str(log)


def test_telemetry_publish_and_aggregate(tmp_path, monkeypatch):
    _with_temp_telemetry(tmp_path, monkeypatch)
    telemetry.publish("fishkeeper", "queen_interaction", {"safe": True, "tags": ["honey"]})
    telemetry.publish("grabhire", "queen_interaction", {"safe": False, "tags": ["honey"]})
    agg = telemetry.aggregate(window_seconds=3600)
    assert agg["total_events"] == 2
    assert "fishkeeper" in agg["hives"]
    assert "grabhire" in agg["hives"]


def test_evolve_tick_proposes_candidate(tmp_path, monkeypatch):
    _with_temp_telemetry(tmp_path, monkeypatch)
    telemetry.publish("grabhire", "queen_interaction", {"safe": False, "tags": ["honey"]})
    telemetry.publish("fishkeeper", "queen_interaction", {"safe": True, "tags": ["honey"]})

    hive = asi_evolve_hive.ASIEvolveHive()
    out = hive.tick()
    assert "candidate" in out
    assert out["candidate"]["target_capability"] == "grabhire"  # weakest safe ratio
    assert hive.status()["candidates_total"] == 1


def test_evolve_status_with_no_telemetry(tmp_path, monkeypatch):
    _with_temp_telemetry(tmp_path, monkeypatch)
    hive = asi_evolve_hive.ASIEvolveHive()
    assert hive.status()["candidates_total"] == 0
