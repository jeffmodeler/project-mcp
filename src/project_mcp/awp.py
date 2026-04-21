"""Advanced Work Packaging (AWP) — CII methodology.

Domain model and tool implementations for:

    CWA (Construction Work Area)  →  CWP (Construction Work Package)
                                          ↓
                                     IWP (Installation Work Package)

Metadata is persisted in the project sidecar folder (see `sidecar.py`). The
`.mpp`/`.xml` schedule remains untouched — tasks are linked to CWPs via their
UID only.

All public functions in this module return plain `dict`s so they serialize
cleanly to JSON for MCP tool responses.
"""
from __future__ import annotations

import logging
from typing import Any

from project_mcp import mspdi, sidecar

logger = logging.getLogger(__name__)

VALID_CWP_STATUS = {"planned", "ready", "in-progress", "complete", "on-hold"}
VALID_IWP_STATUS = {"planned", "ready", "released", "complete"}


def _find_cwa(payload: dict[str, Any], cwa_id: str) -> dict[str, Any] | None:
    return next((c for c in payload["cwa"] if c["id"] == cwa_id), None)


def _find_cwp(payload: dict[str, Any], cwp_id: str) -> dict[str, Any] | None:
    return next((c for c in payload["cwp"] if c["id"] == cwp_id), None)


def _task_to_cwp_map(payload: dict[str, Any]) -> dict[int, str]:
    """Reverse index: task_uid -> cwp_id."""
    mapping: dict[int, str] = {}
    for cwp in payload["cwp"]:
        for uid in cwp.get("task_uids", []):
            mapping[int(uid)] = cwp["id"]
    return mapping


# ---------------------------------------------------------------- CWA tools


def list_cwa(project: mspdi.Project) -> dict[str, Any]:
    """Return all Construction Work Areas defined in the sidecar."""
    if project.source_path is None:
        return {"error": "Project has no source_path; load_project first."}
    payload = sidecar.load_awp(project.source_path)
    return {
        "source": project.source_path,
        "count": len(payload["cwa"]),
        "cwa": payload["cwa"],
    }


def upsert_cwa(
    project: mspdi.Project,
    cwa_id: str,
    name: str,
    description: str | None = None,
    priority: int = 500,
) -> dict[str, Any]:
    """Create or update a CWA. `cwa_id` is the stable identifier."""
    if project.source_path is None:
        return {"error": "Project has no source_path; load_project first."}
    payload = sidecar.load_awp(project.source_path)
    existing = _find_cwa(payload, cwa_id)
    record = {
        "id": cwa_id,
        "name": name,
        "description": description,
        "priority": priority,
    }
    if existing is None:
        payload["cwa"].append(record)
        action = "created"
    else:
        existing.update(record)
        action = "updated"
    sidecar.save_awp(project.source_path, payload)
    return {"action": action, "cwa": record}


# ---------------------------------------------------------------- CWP tools


def list_cwp(
    project: mspdi.Project, cwa_id: str | None = None
) -> dict[str, Any]:
    """List Construction Work Packages, optionally filtered by CWA."""
    if project.source_path is None:
        return {"error": "Project has no source_path; load_project first."}
    payload = sidecar.load_awp(project.source_path)
    items = payload["cwp"]
    if cwa_id:
        items = [c for c in items if c.get("cwa_id") == cwa_id]
    enriched = [_enrich_cwp(c, project) for c in items]
    return {"count": len(enriched), "cwp": enriched}


def upsert_cwp(
    project: mspdi.Project,
    cwp_id: str,
    name: str,
    cwa_id: str,
    description: str | None = None,
    status: str = "planned",
) -> dict[str, Any]:
    """Create or update a CWP. Must reference an existing CWA."""
    if project.source_path is None:
        return {"error": "Project has no source_path; load_project first."}
    if status not in VALID_CWP_STATUS:
        return {"error": f"Invalid status '{status}'. Valid: {sorted(VALID_CWP_STATUS)}"}
    payload = sidecar.load_awp(project.source_path)
    if _find_cwa(payload, cwa_id) is None:
        return {"error": f"CWA '{cwa_id}' does not exist. Create it first with upsert_cwa."}
    existing = _find_cwp(payload, cwp_id)
    if existing is None:
        record = {
            "id": cwp_id,
            "name": name,
            "cwa_id": cwa_id,
            "description": description,
            "status": status,
            "task_uids": [],
            "requirements": {"materials": [], "documents": [], "access": []},
        }
        payload["cwp"].append(record)
        action = "created"
    else:
        existing.update({
            "name": name, "cwa_id": cwa_id,
            "description": description, "status": status,
        })
        record = existing
        action = "updated"
    sidecar.save_awp(project.source_path, payload)
    return {"action": action, "cwp": record}


def assign_task_to_cwp(
    project: mspdi.Project, task_uid: int, cwp_id: str
) -> dict[str, Any]:
    """Link a task (by UID) to a CWP. The task must exist in the project."""
    if project.source_path is None:
        return {"error": "Project has no source_path; load_project first."}
    task = project.task_by_uid(task_uid)
    if task is None:
        return {"error": f"Task UID {task_uid} not found in project."}
    payload = sidecar.load_awp(project.source_path)
    cwp = _find_cwp(payload, cwp_id)
    if cwp is None:
        return {"error": f"CWP '{cwp_id}' does not exist."}
    # Remove this task from any other CWP it might be assigned to
    reassigned_from: str | None = None
    for other in payload["cwp"]:
        if other["id"] == cwp_id:
            continue
        if task_uid in other.get("task_uids", []):
            other["task_uids"].remove(task_uid)
            reassigned_from = other["id"]
    task_uids: list[int] = cwp.setdefault("task_uids", [])
    if task_uid not in task_uids:
        task_uids.append(task_uid)
    sidecar.save_awp(project.source_path, payload)
    return {
        "assigned": True,
        "task_uid": task_uid,
        "task_name": task.name,
        "cwp_id": cwp_id,
        "reassigned_from": reassigned_from,
    }


def set_cwp_requirements(
    project: mspdi.Project,
    cwp_id: str,
    materials: list[str] | None = None,
    documents: list[str] | None = None,
    access: list[str] | None = None,
) -> dict[str, Any]:
    """Set readiness requirements for a CWP.

    Any argument left as None preserves the existing list.
    """
    if project.source_path is None:
        return {"error": "Project has no source_path; load_project first."}
    payload = sidecar.load_awp(project.source_path)
    cwp = _find_cwp(payload, cwp_id)
    if cwp is None:
        return {"error": f"CWP '{cwp_id}' does not exist."}
    default_reqs: dict[str, list[str]] = {"materials": [], "documents": [], "access": []}
    reqs: dict[str, list[str]] = cwp.setdefault("requirements", default_reqs)
    if materials is not None:
        reqs["materials"] = materials
    if documents is not None:
        reqs["documents"] = documents
    if access is not None:
        reqs["access"] = access
    sidecar.save_awp(project.source_path, payload)
    return {"cwp_id": cwp_id, "requirements": reqs}


def readiness_check(
    project: mspdi.Project,
    cwp_id: str,
    available_materials: list[str] | None = None,
    available_documents: list[str] | None = None,
    available_access: list[str] | None = None,
) -> dict[str, Any]:
    """Check whether a CWP has all requirements available.

    The `available_*` arguments represent what is currently on-site / approved.
    Typically provided by the LLM based on procurement/document status.
    """
    if project.source_path is None:
        return {"error": "Project has no source_path; load_project first."}
    payload = sidecar.load_awp(project.source_path)
    cwp = _find_cwp(payload, cwp_id)
    if cwp is None:
        return {"error": f"CWP '{cwp_id}' does not exist."}
    reqs = cwp.get("requirements", {})
    avail = {
        "materials": set(available_materials or []),
        "documents": set(available_documents or []),
        "access": set(available_access or []),
    }
    missing: dict[str, list[str]] = {}
    for key in ("materials", "documents", "access"):
        needed = set(reqs.get(key, []))
        lack = sorted(needed - avail[key])
        if lack:
            missing[key] = lack
    is_ready = not missing
    return {
        "cwp_id": cwp_id,
        "ready": is_ready,
        "missing": missing,
        "requirements": reqs,
    }


# ---------------------------------------------------------- Path of construction


def path_of_construction(project: mspdi.Project) -> dict[str, Any]:
    """Compute the ideal execution sequence of CWPs based on task dependencies.

    For each CWP, aggregates:
      - Earliest start among its tasks
      - Latest finish among its tasks
      - Whether any task is on the critical path
      - Total duration (sum of tasks, in hours)

    Then sorts by earliest start.
    """
    if project.source_path is None:
        return {"error": "Project has no source_path; load_project first."}
    payload = sidecar.load_awp(project.source_path)
    cwps = payload["cwp"]
    if not cwps:
        return {"count": 0, "sequence": [], "note": "No CWPs defined yet."}
    result: list[dict[str, Any]] = []
    for cwp in cwps:
        tasks = [project.task_by_uid(uid) for uid in cwp.get("task_uids", [])]
        tasks = [t for t in tasks if t is not None]
        if not tasks:
            result.append({
                "cwp_id": cwp["id"], "name": cwp["name"], "status": cwp.get("status"),
                "task_count": 0,
            })
            continue
        starts = [t.start for t in tasks if t.start]
        finishes = [t.finish for t in tasks if t.finish]
        critical_count = sum(1 for t in tasks if t.is_critical)
        total_hours = sum(t.duration_hours for t in tasks)
        result.append({
            "cwp_id": cwp["id"],
            "name": cwp["name"],
            "cwa_id": cwp.get("cwa_id"),
            "status": cwp.get("status"),
            "task_count": len(tasks),
            "earliest_start": min(starts) if starts else None,
            "latest_finish": max(finishes) if finishes else None,
            "duration_hours": round(total_hours, 2),
            "critical_task_count": critical_count,
            "on_critical_path": critical_count > 0,
        })
    result.sort(key=lambda r: (r.get("earliest_start") or "9999"))
    return {"count": len(result), "sequence": result}


# ---------------------------------------------------------------- IWP tools


def generate_iwps(
    project: mspdi.Project,
    cwp_id: str,
    max_hours_per_iwp: float = 40.0,
) -> dict[str, Any]:
    """Split a CWP into IWPs (Installation Work Packages) sized by labor hours.

    Walks the CWP's tasks in schedule order and groups them into IWPs such
    that no IWP exceeds `max_hours_per_iwp` (default: one work-week). Any
    task already larger than the cap becomes a standalone IWP.
    """
    if project.source_path is None:
        return {"error": "Project has no source_path; load_project first."}
    payload = sidecar.load_awp(project.source_path)
    cwp = _find_cwp(payload, cwp_id)
    if cwp is None:
        return {"error": f"CWP '{cwp_id}' does not exist."}
    tasks = [project.task_by_uid(uid) for uid in cwp.get("task_uids", [])]
    tasks = [t for t in tasks if t is not None]
    if not tasks:
        return {"error": f"CWP '{cwp_id}' has no tasks assigned."}
    tasks.sort(key=lambda t: (t.start or "9999", t.id))

    iwps: list[dict[str, Any]] = []
    current_uids: list[int] = []
    current_hours = 0.0
    seq = 1
    for task in tasks:
        hours = task.duration_hours or 0.0
        if current_uids and current_hours + hours > max_hours_per_iwp:
            iwps.append(_make_iwp(cwp_id, seq, current_uids, current_hours))
            seq += 1
            current_uids = []
            current_hours = 0.0
        current_uids.append(task.uid)
        current_hours += hours
    if current_uids:
        iwps.append(_make_iwp(cwp_id, seq, current_uids, current_hours))

    # Replace any existing IWPs for this CWP
    payload["iwp"] = [i for i in payload["iwp"] if i.get("cwp_id") != cwp_id]
    payload["iwp"].extend(iwps)
    sidecar.save_awp(project.source_path, payload)
    return {"cwp_id": cwp_id, "iwp_count": len(iwps), "iwp": iwps}


def _make_iwp(cwp_id: str, seq: int, task_uids: list[int], hours: float) -> dict[str, Any]:
    return {
        "id": f"IWP-{cwp_id.replace('CWP-', '')}.{seq:03d}",
        "cwp_id": cwp_id,
        "task_uids": task_uids,
        "labor_hours": round(hours, 2),
        "status": "planned",
    }


# ---------------------------------------------------------------- Work Package Release


def export_wpr(project: mspdi.Project, cwp_id: str) -> dict[str, Any]:
    """Generate a Work Package Release — everything needed to send the CWP to the field.

    Returns a self-contained JSON structure with CWP metadata, requirements,
    full task list (names, dates, hours), and IWP breakdown. Field teams
    receive this to start execution without further coordination.
    """
    if project.source_path is None:
        return {"error": "Project has no source_path; load_project first."}
    payload = sidecar.load_awp(project.source_path)
    cwp = _find_cwp(payload, cwp_id)
    if cwp is None:
        return {"error": f"CWP '{cwp_id}' does not exist."}
    cwa = _find_cwa(payload, cwp.get("cwa_id", ""))
    tasks_dict = [
        project.task_by_uid(uid).to_dict()
        for uid in cwp.get("task_uids", [])
        if project.task_by_uid(uid) is not None
    ]
    iwps = [i for i in payload["iwp"] if i.get("cwp_id") == cwp_id]
    return {
        "wpr_id": f"WPR-{cwp_id}",
        "project": {"title": project.title, "source": project.source_path},
        "cwa": cwa,
        "cwp": cwp,
        "tasks": tasks_dict,
        "iwp": iwps,
        "task_count": len(tasks_dict),
        "total_hours": round(sum(t["duration_hours"] for t in tasks_dict), 2),
    }


def _enrich_cwp(cwp: dict[str, Any], project: mspdi.Project) -> dict[str, Any]:
    """Add computed fields to a CWP record for listing."""
    tasks = [project.task_by_uid(uid) for uid in cwp.get("task_uids", [])]
    tasks = [t for t in tasks if t is not None]
    return {
        **cwp,
        "task_count": len(tasks),
        "total_hours": round(sum(t.duration_hours for t in tasks), 2),
        "any_critical": any(t.is_critical for t in tasks),
    }
