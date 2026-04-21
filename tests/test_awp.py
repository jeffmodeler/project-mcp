"""Tests for the AWP (Advanced Work Packaging) module."""
from __future__ import annotations

from pathlib import Path

import pytest

from project_mcp import awp, mspdi, sidecar

FIXTURE = Path(__file__).parent / "fixtures" / "sample.xml"


@pytest.fixture
def project(tmp_path: Path) -> mspdi.Project:
    """Parse the fixture and relocate it to tmp_path so tests don't
    collide on the shared sidecar folder."""
    data = FIXTURE.read_bytes()
    staged = tmp_path / "sample.xml"
    staged.write_bytes(data)
    return mspdi.parse_file(staged)


# ---------------------------------------------------------------- sidecar


def test_sidecar_dir_derives_from_stem(tmp_path: Path) -> None:
    project_file = tmp_path / "obra-acme.mpp"
    expected = tmp_path / "obra-acme.awp"
    assert sidecar.sidecar_dir(project_file) == expected


def test_load_awp_returns_empty_when_missing(project: mspdi.Project) -> None:
    payload = sidecar.load_awp(project.source_path)
    assert payload["cwa"] == []
    assert payload["cwp"] == []
    assert payload["iwp"] == []
    assert payload["version"] == "1.0"


def test_save_and_reload_roundtrip(project: mspdi.Project) -> None:
    payload = sidecar.default_awp_payload(project.source_path)
    payload["cwa"].append({"id": "CWA-01", "name": "Fundações", "priority": 1})
    sidecar.save_awp(project.source_path, payload)

    path = sidecar.awp_file(project.source_path)
    assert path.exists()
    reloaded = sidecar.load_awp(project.source_path)
    assert reloaded["cwa"][0]["name"] == "Fundações"
    assert "updated_at" in reloaded


# ---------------------------------------------------------------- CWA


def test_upsert_cwa_creates_then_updates(project: mspdi.Project) -> None:
    created = awp.upsert_cwa(project, "CWA-01", "Fundações", priority=1)
    assert created["action"] == "created"
    updated = awp.upsert_cwa(project, "CWA-01", "Fundações e Contenções", priority=1)
    assert updated["action"] == "updated"
    assert updated["cwa"]["name"] == "Fundações e Contenções"
    listed = awp.list_cwa(project)
    assert listed["count"] == 1


def test_list_cwa_empty_state(project: mspdi.Project) -> None:
    result = awp.list_cwa(project)
    assert result["count"] == 0
    assert result["cwa"] == []


# ---------------------------------------------------------------- CWP


def test_upsert_cwp_requires_existing_cwa(project: mspdi.Project) -> None:
    result = awp.upsert_cwp(project, "CWP-01.01", "Fundação Bloco A", "CWA-INEXISTENTE")
    assert "error" in result


def test_upsert_cwp_rejects_invalid_status(project: mspdi.Project) -> None:
    awp.upsert_cwa(project, "CWA-01", "Fundações")
    result = awp.upsert_cwp(project, "CWP-01.01", "Fundação A", "CWA-01", status="xpto")
    assert "error" in result


def test_cwp_lifecycle(project: mspdi.Project) -> None:
    awp.upsert_cwa(project, "CWA-01", "Fundações")
    created = awp.upsert_cwp(project, "CWP-01.01", "Fundação A", "CWA-01")
    assert created["action"] == "created"
    assert created["cwp"]["status"] == "planned"

    # Assign a real task from the fixture (UID 1 exists in sample.xml)
    assignment = awp.assign_task_to_cwp(project, task_uid=1, cwp_id="CWP-01.01")
    assert assignment["assigned"]

    listed = awp.list_cwp(project)
    assert listed["count"] == 1
    assert listed["cwp"][0]["task_count"] == 1


def test_assign_task_moves_between_cwps(project: mspdi.Project) -> None:
    awp.upsert_cwa(project, "CWA-01", "Fundações")
    awp.upsert_cwp(project, "CWP-A", "A", "CWA-01")
    awp.upsert_cwp(project, "CWP-B", "B", "CWA-01")
    awp.assign_task_to_cwp(project, task_uid=1, cwp_id="CWP-A")
    moved = awp.assign_task_to_cwp(project, task_uid=1, cwp_id="CWP-B")
    assert moved["reassigned_from"] == "CWP-A"
    payload = sidecar.load_awp(project.source_path)
    cwp_a = next(c for c in payload["cwp"] if c["id"] == "CWP-A")
    cwp_b = next(c for c in payload["cwp"] if c["id"] == "CWP-B")
    assert 1 not in cwp_a["task_uids"]
    assert 1 in cwp_b["task_uids"]


def test_assign_task_rejects_missing_task(project: mspdi.Project) -> None:
    awp.upsert_cwa(project, "CWA-01", "Fundações")
    awp.upsert_cwp(project, "CWP-01", "A", "CWA-01")
    result = awp.assign_task_to_cwp(project, task_uid=99999, cwp_id="CWP-01")
    assert "error" in result


# ---------------------------------------------------------------- Readiness


def test_readiness_check_all_ready(project: mspdi.Project) -> None:
    awp.upsert_cwa(project, "CWA-01", "Fundações")
    awp.upsert_cwp(project, "CWP-01", "A", "CWA-01")
    awp.set_cwp_requirements(
        project, "CWP-01",
        materials=["aço CA-50"],
        documents=["AR-01"],
        access=["portão 1"],
    )
    result = awp.readiness_check(
        project, "CWP-01",
        available_materials=["aço CA-50", "concreto"],
        available_documents=["AR-01"],
        available_access=["portão 1", "portão 2"],
    )
    assert result["ready"] is True
    assert result["missing"] == {}


def test_readiness_check_missing_items(project: mspdi.Project) -> None:
    awp.upsert_cwa(project, "CWA-01", "Fundações")
    awp.upsert_cwp(project, "CWP-01", "A", "CWA-01")
    awp.set_cwp_requirements(
        project, "CWP-01",
        materials=["aço CA-50", "concreto fck25"],
        documents=["AR-01"],
    )
    result = awp.readiness_check(
        project, "CWP-01",
        available_materials=["aço CA-50"],
        available_documents=[],
    )
    assert result["ready"] is False
    assert result["missing"]["materials"] == ["concreto fck25"]
    assert result["missing"]["documents"] == ["AR-01"]


# ---------------------------------------------------------------- Path of construction


def test_path_of_construction_orders_by_earliest_start(project: mspdi.Project) -> None:
    awp.upsert_cwa(project, "CWA-01", "A")
    awp.upsert_cwp(project, "CWP-EARLY", "Early", "CWA-01")
    awp.upsert_cwp(project, "CWP-LATE", "Late", "CWA-01")
    awp.assign_task_to_cwp(project, task_uid=1, cwp_id="CWP-EARLY")
    awp.assign_task_to_cwp(project, task_uid=4, cwp_id="CWP-LATE")  # UID 4 = milestone at end
    result = awp.path_of_construction(project)
    assert result["count"] == 2
    ids = [r["cwp_id"] for r in result["sequence"]]
    assert ids.index("CWP-EARLY") < ids.index("CWP-LATE")


# ---------------------------------------------------------------- IWP generation


def test_generate_iwps_splits_by_hours(project: mspdi.Project) -> None:
    awp.upsert_cwa(project, "CWA-01", "A")
    awp.upsert_cwp(project, "CWP-01", "Pkg", "CWA-01")
    # Assign several tasks from the fixture
    for uid in (1, 2, 3):
        awp.assign_task_to_cwp(project, task_uid=uid, cwp_id="CWP-01")
    result = awp.generate_iwps(project, "CWP-01", max_hours_per_iwp=16.0)
    assert "iwp" in result
    assert result["iwp_count"] >= 1
    for iwp in result["iwp"]:
        assert iwp["id"].startswith("IWP-")


def test_generate_iwps_errors_when_cwp_empty(project: mspdi.Project) -> None:
    awp.upsert_cwa(project, "CWA-01", "A")
    awp.upsert_cwp(project, "CWP-01", "Pkg", "CWA-01")
    result = awp.generate_iwps(project, "CWP-01")
    assert "error" in result


# ---------------------------------------------------------------- WPR


def test_export_wpr_includes_cwa_cwp_tasks(project: mspdi.Project) -> None:
    awp.upsert_cwa(project, "CWA-01", "Fundações")
    awp.upsert_cwp(project, "CWP-01", "Bloco A", "CWA-01", description="Fundação")
    awp.assign_task_to_cwp(project, task_uid=1, cwp_id="CWP-01")
    wpr = awp.export_wpr(project, "CWP-01")
    assert wpr["wpr_id"] == "WPR-CWP-01"
    assert wpr["cwa"]["id"] == "CWA-01"
    assert wpr["cwp"]["id"] == "CWP-01"
    assert wpr["task_count"] == 1
    assert wpr["total_hours"] >= 0


def test_export_wpr_unknown_cwp(project: mspdi.Project) -> None:
    result = awp.export_wpr(project, "CWP-DOES-NOT-EXIST")
    assert "error" in result
