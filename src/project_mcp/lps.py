"""Last Planner System (LPS) — Lean Construction methodology.

Five planning levels:

    Master → Phase (pull plan) → Lookahead (N weeks, clears constraints)
          → WWP (Weekly Work Plan, commitments) → Daily huddle

Key metric: PPC (Percent Plan Complete) — commitments kept / commitments made.

State persisted in the LPS sidecar (see `sidecar.py`). The `.mpp` schedule
remains authoritative for tasks; LPS layer adds phases, constraints, weekly
commitments, and completion tracking.

All public functions return plain `dict`s for MCP tool serialization.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

from project_mcp import mspdi, sidecar

logger = logging.getLogger(__name__)

VALID_CONSTRAINT_TYPES = {
    "material", "document", "information", "design",
    "labor", "equipment", "access", "permit",
    "prerequisite", "other",
}

VALID_CONSTRAINT_STATUS = {"open", "cleared"}

VALID_VARIANCE_REASONS = {
    "weather", "design_change", "material_delay", "labor_unavailable",
    "equipment_breakdown", "rework", "permit", "prerequisite_incomplete",
    "scope_change", "other",
}


def _find_phase(payload: dict[str, Any], phase_id: str) -> dict[str, Any] | None:
    return next((p for p in payload["phases"] if p["id"] == phase_id), None)


def _find_constraint(payload: dict[str, Any], constraint_id: str) -> dict[str, Any] | None:
    return next((c for c in payload["constraints"] if c["id"] == constraint_id), None)


def _find_wwp(payload: dict[str, Any], week: str) -> dict[str, Any] | None:
    return next((w for w in payload["weekly_work_plans"] if w["week"] == week), None)


def _today_iso() -> str:
    return date.today().isoformat()


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


def _iso_week(d: date) -> str:
    """Return ISO week string like '2025-W03' for a date."""
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


# ======================================================================
# Phases & Pull Plan
# ======================================================================


def list_phases(project: mspdi.Project) -> dict[str, Any]:
    """Return all project phases defined in the sidecar."""
    if project.source_path is None:
        return {"error": "Project has no source_path; load_project first."}
    payload = sidecar.load_lps(project.source_path)
    return {"count": len(payload["phases"]), "phases": payload["phases"]}


def upsert_phase(
    project: mspdi.Project,
    phase_id: str,
    name: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Create or update a project phase (used as container for pull plans)."""
    if project.source_path is None:
        return {"error": "Project has no source_path; load_project first."}
    payload = sidecar.load_lps(project.source_path)
    existing = _find_phase(payload, phase_id)
    if existing is None:
        record = {
            "id": phase_id, "name": name,
            "start_date": start_date, "end_date": end_date,
            "pull_plan": [],
        }
        payload["phases"].append(record)
        action = "created"
    else:
        existing.update({"name": name, "start_date": start_date, "end_date": end_date})
        record = existing
        action = "updated"
    sidecar.save_lps(project.source_path, payload)
    return {"action": action, "phase": record}


def set_pull_plan(
    project: mspdi.Project,
    phase_id: str,
    task_uids: list[int],
) -> dict[str, Any]:
    """Set the pull-plan sequence for a phase.

    Pull planning works backwards from the phase milestone. `task_uids` should
    be in the order the team committed to — first item executes first. Each
    entry is validated against the project tasks.
    """
    if project.source_path is None:
        return {"error": "Project has no source_path; load_project first."}
    payload = sidecar.load_lps(project.source_path)
    phase = _find_phase(payload, phase_id)
    if phase is None:
        return {"error": f"Phase '{phase_id}' does not exist. Create it with upsert_phase first."}
    sequence = []
    unknown: list[int] = []
    for uid in task_uids:
        task = project.task_by_uid(uid)
        if task is None:
            unknown.append(uid)
            continue
        sequence.append({
            "task_uid": uid, "name": task.name,
            "duration_hours": task.duration_hours,
            "is_milestone": task.is_milestone,
        })
    phase["pull_plan"] = sequence
    sidecar.save_lps(project.source_path, payload)
    return {
        "phase_id": phase_id, "sequence_count": len(sequence),
        "unknown_task_uids": unknown, "pull_plan": sequence,
    }


def get_pull_plan(project: mspdi.Project, phase_id: str) -> dict[str, Any]:
    """Get the pull plan for a phase."""
    if project.source_path is None:
        return {"error": "Project has no source_path; load_project first."}
    payload = sidecar.load_lps(project.source_path)
    phase = _find_phase(payload, phase_id)
    if phase is None:
        return {"error": f"Phase '{phase_id}' does not exist."}
    return {
        "phase_id": phase_id, "name": phase.get("name"),
        "start_date": phase.get("start_date"), "end_date": phase.get("end_date"),
        "pull_plan": phase.get("pull_plan", []),
    }


# ======================================================================
# Constraints
# ======================================================================


def register_constraint(
    project: mspdi.Project,
    task_uid: int,
    constraint_type: str,
    description: str,
    owner: str | None = None,
    due_date: str | None = None,
) -> dict[str, Any]:
    """Register a constraint blocking a task.

    Types: material | document | information | design | labor | equipment |
           access | permit | prerequisite | other
    """
    if project.source_path is None:
        return {"error": "Project has no source_path; load_project first."}
    if constraint_type not in VALID_CONSTRAINT_TYPES:
        return {
            "error": f"Invalid type '{constraint_type}'",
            "valid_types": sorted(VALID_CONSTRAINT_TYPES),
        }
    task = project.task_by_uid(task_uid)
    if task is None:
        return {"error": f"Task UID {task_uid} not found in project."}
    payload = sidecar.load_lps(project.source_path)
    constraint = {
        "id": f"CST-{uuid4().hex[:8].upper()}",
        "task_uid": task_uid,
        "task_name": task.name,
        "type": constraint_type,
        "description": description,
        "owner": owner,
        "registered_date": _today_iso(),
        "due_date": due_date,
        "resolved_date": None,
        "status": "open",
    }
    payload["constraints"].append(constraint)
    sidecar.save_lps(project.source_path, payload)
    return {"registered": True, "constraint": constraint}


def clear_constraint(project: mspdi.Project, constraint_id: str) -> dict[str, Any]:
    """Mark a constraint as cleared (resolved)."""
    if project.source_path is None:
        return {"error": "Project has no source_path; load_project first."}
    payload = sidecar.load_lps(project.source_path)
    constraint = _find_constraint(payload, constraint_id)
    if constraint is None:
        return {"error": f"Constraint '{constraint_id}' not found."}
    if constraint["status"] == "cleared":
        return {"already_cleared": True, "constraint": constraint}
    constraint["status"] = "cleared"
    constraint["resolved_date"] = _today_iso()
    sidecar.save_lps(project.source_path, payload)
    return {"cleared": True, "constraint": constraint}


def list_constraints(
    project: mspdi.Project,
    task_uid: int | None = None,
    status: str | None = None,
    constraint_type: str | None = None,
) -> dict[str, Any]:
    """List constraints, optionally filtered by task, status, or type."""
    if project.source_path is None:
        return {"error": "Project has no source_path; load_project first."}
    payload = sidecar.load_lps(project.source_path)
    items = payload["constraints"]
    if task_uid is not None:
        items = [c for c in items if c.get("task_uid") == task_uid]
    if status is not None:
        items = [c for c in items if c.get("status") == status]
    if constraint_type is not None:
        items = [c for c in items if c.get("type") == constraint_type]
    return {"count": len(items), "constraints": items}


# ======================================================================
# Lookahead
# ======================================================================


def lookahead(
    project: mspdi.Project,
    weeks: int = 6,
    from_date: str | None = None,
) -> dict[str, Any]:
    """Return tasks starting within the next N weeks + their open constraints.

    Tasks are gathered from the project schedule (not from WWPs), giving the
    classic LPS lookahead: "what's coming, and what's blocking it?"
    """
    if project.source_path is None:
        return {"error": "Project has no source_path; load_project first."}
    origin = _parse_iso_date(from_date) or datetime.now(UTC).date()
    horizon = origin + timedelta(weeks=weeks)
    payload = sidecar.load_lps(project.source_path)
    open_constraints: dict[int, list[dict[str, Any]]] = {}
    for c in payload["constraints"]:
        if c.get("status") != "open":
            continue
        open_constraints.setdefault(int(c["task_uid"]), []).append(c)

    upcoming: list[dict[str, Any]] = []
    for task in project.tasks:
        if task.is_summary or task.is_null:
            continue
        start = _parse_iso_date(task.start)
        if start is None or start < origin or start > horizon:
            continue
        cs = open_constraints.get(task.uid, [])
        upcoming.append({
            "task_uid": task.uid, "name": task.name,
            "start": task.start, "finish": task.finish,
            "duration_hours": task.duration_hours,
            "is_critical": task.is_critical,
            "constraint_count": len(cs),
            "constraints": cs,
            "ready": len(cs) == 0,
        })
    upcoming.sort(key=lambda t: (t["start"] or "9999", t["task_uid"]))
    ready_count = sum(1 for t in upcoming if t["ready"])
    return {
        "origin": origin.isoformat(),
        "horizon": horizon.isoformat(),
        "weeks": weeks,
        "task_count": len(upcoming),
        "ready_count": ready_count,
        "blocked_count": len(upcoming) - ready_count,
        "tasks": upcoming,
    }


# ======================================================================
# Weekly Work Plan + PPC
# ======================================================================


def add_commitment(
    project: mspdi.Project,
    week: str,
    task_uid: int,
    committed_by: str | None = None,
    promised_hours: float | None = None,
) -> dict[str, Any]:
    """Add a task commitment to a weekly work plan.

    `week` uses ISO format 'YYYY-Www' (e.g. '2025-W03'). Creates the WWP
    if it does not exist yet.
    """
    if project.source_path is None:
        return {"error": "Project has no source_path; load_project first."}
    task = project.task_by_uid(task_uid)
    if task is None:
        return {"error": f"Task UID {task_uid} not found in project."}
    payload = sidecar.load_lps(project.source_path)
    wwp = _find_wwp(payload, week)
    if wwp is None:
        wwp = {"week": week, "commitments": []}
        payload["weekly_work_plans"].append(wwp)
    existing = next((c for c in wwp["commitments"] if c["task_uid"] == task_uid), None)
    commitment = {
        "task_uid": task_uid,
        "task_name": task.name,
        "committed_by": committed_by,
        "promised_hours": promised_hours,
        "actual_hours": None,
        "complete": False,
        "variance_reason": None,
    }
    if existing is None:
        wwp["commitments"].append(commitment)
        action = "added"
    else:
        existing.update({
            "committed_by": committed_by,
            "promised_hours": promised_hours,
        })
        commitment = existing
        action = "updated"
    sidecar.save_lps(project.source_path, payload)
    return {"action": action, "week": week, "commitment": commitment}


def mark_complete(
    project: mspdi.Project,
    week: str,
    task_uid: int,
    complete: bool,
    actual_hours: float | None = None,
    variance_reason: str | None = None,
) -> dict[str, Any]:
    """Close a commitment at week end. If not complete, a variance reason is required."""
    if project.source_path is None:
        return {"error": "Project has no source_path; load_project first."}
    if not complete and not variance_reason:
        return {"error": "Incomplete commitments require variance_reason."}
    if variance_reason and variance_reason not in VALID_VARIANCE_REASONS:
        return {
            "error": f"Invalid variance_reason '{variance_reason}'",
            "valid_reasons": sorted(VALID_VARIANCE_REASONS),
        }
    payload = sidecar.load_lps(project.source_path)
    wwp = _find_wwp(payload, week)
    if wwp is None:
        return {"error": f"No weekly work plan for '{week}'."}
    commitment = next((c for c in wwp["commitments"] if c["task_uid"] == task_uid), None)
    if commitment is None:
        return {"error": f"Task UID {task_uid} is not committed in {week}."}
    commitment["complete"] = complete
    commitment["actual_hours"] = actual_hours
    commitment["variance_reason"] = None if complete else variance_reason
    sidecar.save_lps(project.source_path, payload)
    return {"updated": True, "week": week, "commitment": commitment}


def get_wwp(project: mspdi.Project, week: str) -> dict[str, Any]:
    """Get the weekly work plan for a given ISO week."""
    if project.source_path is None:
        return {"error": "Project has no source_path; load_project first."}
    payload = sidecar.load_lps(project.source_path)
    wwp = _find_wwp(payload, week)
    if wwp is None:
        return {"error": f"No weekly work plan for '{week}'.", "week": week}
    return {
        "week": week,
        "commitment_count": len(wwp["commitments"]),
        "commitments": wwp["commitments"],
    }


def calculate_ppc(
    project: mspdi.Project,
    week: str | None = None,
    weeks_back: int = 4,
) -> dict[str, Any]:
    """Compute Percent Plan Complete.

    If `week` is given, returns PPC for that single week. Otherwise returns
    a series of the last `weeks_back` weeks that have WWPs recorded.
    """
    if project.source_path is None:
        return {"error": "Project has no source_path; load_project first."}
    payload = sidecar.load_lps(project.source_path)
    wwps = payload["weekly_work_plans"]
    if not wwps:
        return {"series": [], "note": "No weekly work plans recorded."}

    def _compute_one(w: dict[str, Any]) -> dict[str, Any]:
        commitments = w["commitments"]
        total = len(commitments)
        complete = sum(1 for c in commitments if c.get("complete"))
        failed = [c for c in commitments if not c.get("complete")]
        reasons: dict[str, int] = {}
        for f in failed:
            r = f.get("variance_reason") or "unspecified"
            reasons[r] = reasons.get(r, 0) + 1
        ppc = round(complete / total * 100, 1) if total else 0.0
        return {
            "week": w["week"], "committed": total, "complete": complete,
            "failed": total - complete, "ppc": ppc,
            "variance_reasons": reasons,
        }

    if week is not None:
        target = _find_wwp(payload, week)
        if target is None:
            return {"error": f"No weekly work plan for '{week}'."}
        return _compute_one(target)

    sorted_wwps = sorted(wwps, key=lambda w: w["week"])
    recent = sorted_wwps[-weeks_back:]
    series = [_compute_one(w) for w in recent]
    avg = round(sum(s["ppc"] for s in series) / len(series), 1) if series else 0.0
    return {"series": series, "average_ppc": avg, "weeks_included": len(series)}
