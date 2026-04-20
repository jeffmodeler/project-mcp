"""project-mcp: MCP server exposing Microsoft Project data as tools."""
from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from project_mcp import mspdi
from project_mcp.pbip_writer import PbipWriter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("project-mcp")

mcp = FastMCP("project-mcp")

_state: dict[str, mspdi.Project | None] = {"project": None}


def _project() -> mspdi.Project:
    project = _state["project"]
    if project is None:
        raise RuntimeError("No project loaded. Call load_project(path) first.")
    return project


def _serialize(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str, ensure_ascii=False)


@mcp.tool()
def load_project(path: str) -> str:
    """Load a Microsoft Project file into memory.

    Currently supports MSPDI XML format (.xml), exported from Microsoft Project
    via File → Save As → Save as Type → XML Format. Support for native .mpp is
    available when the optional `mpxj` extra is installed (requires Java).

    Args:
        path: Absolute path to the project file.

    Returns:
        JSON with project metadata: title, author, dates, task and resource counts.
    """
    file_path = Path(path).expanduser()
    if not file_path.exists():
        return _serialize({"error": f"File not found: {path}"})
    suffix = file_path.suffix.lower()
    if suffix in (".xml",):
        project = mspdi.parse_file(file_path)
    elif suffix == ".mpp":
        try:
            from project_mcp import mpp_loader  # type: ignore
        except ImportError:
            return _serialize({
                "error": ".mpp requires the optional 'mpp' extra. "
                         "Install with: uv pip install 'project-mcp[mpp]' "
                         "or export the file as XML from Microsoft Project."
            })
        project = mpp_loader.parse_file(file_path)
    else:
        return _serialize({
            "error": f"Unsupported file extension: {suffix}. Use .xml (MSPDI) or .mpp.",
            "hint": "From Microsoft Project: File → Save As → Save as Type → XML Format (*.xml)",
        })
    _state["project"] = project
    return _serialize({
        "loaded": True,
        "source_path": project.source_path,
        "title": project.title,
        "name": project.name,
        "author": project.author,
        "company": project.company,
        "start_date": project.start_date,
        "finish_date": project.finish_date,
        "currency_code": project.currency_code,
        "tasks_count": len(project.tasks),
        "resources_count": len(project.resources),
        "assignments_count": len(project.assignments),
    })


@mcp.tool()
def open_in_ms_project(path: str | None = None) -> str:
    """Open a project file in Microsoft Project using the default OS association.

    If path is omitted, opens the file that is currently loaded in memory.
    Uses the Windows shell (cmd /c start) so the file opens with whatever
    application is registered for .xml or .mpp on the user's machine.

    Args:
        path: Absolute path to the project file. Optional — defaults to the
              source_path of the currently loaded project.

    Returns:
        JSON confirming the file was sent to the OS for opening, or an error.
    """
    target: str | None = path

    if target is None:
        project = _state.get("project")
        if project is None:
            return _serialize({
                "error": "No project loaded and no path provided. "
                         "Call load_project(path) first or pass a path explicitly."
            })
        target = str(project.source_path)

    file_path = Path(target).expanduser()
    if not file_path.exists():
        return _serialize({"error": f"File not found: {target}"})

    try:
        # Use 'start' via cmd so Windows opens with the registered app (MS Project)
        subprocess.Popen(
            ["cmd", "/c", "start", "", str(file_path)],
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("Sent to OS for opening: %s", file_path)
        return _serialize({
            "opened": True,
            "path": str(file_path),
            "note": "File dispatched to the OS. Microsoft Project should open shortly.",
        })
    except Exception as exc:  # noqa: BLE001
        return _serialize({"error": f"Failed to open file: {exc}"})


@mcp.tool()
def project_info() -> str:
    """Return metadata about the currently loaded project.

    Returns:
        JSON with title, author, company, schedule window, currency and counts.
    """
    p = _project()
    summary_count = sum(1 for t in p.tasks if t.is_summary)
    milestone_count = sum(1 for t in p.tasks if t.is_milestone)
    critical_count = sum(1 for t in p.tasks if t.is_critical)
    total_work = sum(t.work_hours for t in p.tasks if not t.is_summary)
    total_duration = sum(t.duration_hours for t in p.tasks if not t.is_summary)
    return _serialize({
        "title": p.title,
        "name": p.name,
        "author": p.author,
        "company": p.company,
        "subject": p.subject,
        "category": p.category,
        "start_date": p.start_date,
        "finish_date": p.finish_date,
        "currency_code": p.currency_code,
        "currency_symbol": p.currency_symbol,
        "schema_version": p.schema_version,
        "source_path": p.source_path,
        "counts": {
            "tasks_total": len(p.tasks),
            "tasks_summary": summary_count,
            "tasks_milestone": milestone_count,
            "tasks_critical": critical_count,
            "resources": len(p.resources),
            "assignments": len(p.assignments),
        },
        "totals": {
            "work_hours": round(total_work, 2),
            "duration_hours": round(total_duration, 2),
        },
    })


@mcp.tool()
def list_tasks(
    include_summaries: bool = True,
    include_milestones: bool = True,
    only_critical: bool = False,
    name_contains: str | None = None,
    top_n: int | None = None,
) -> str:
    """List tasks in the loaded project, with optional filters.

    Args:
        include_summaries: Include summary tasks (parent rollup rows).
        include_milestones: Include milestone tasks (zero-duration markers).
        only_critical: Return only tasks on the critical path.
        name_contains: Substring filter on task name (case-insensitive).
        top_n: Limit the output to the first N tasks (None returns all).

    Returns:
        JSON with array of tasks containing UID, ID, name, dates, duration,
        percent complete, priority, and critical/summary/milestone flags.
    """
    p = _project()
    tasks = p.tasks
    if not include_summaries:
        tasks = [t for t in tasks if not t.is_summary]
    if not include_milestones:
        tasks = [t for t in tasks if not t.is_milestone]
    if only_critical:
        tasks = [t for t in tasks if t.is_critical]
    if name_contains:
        needle = name_contains.lower()
        tasks = [t for t in tasks if t.name and needle in t.name.lower()]
    if top_n:
        tasks = tasks[: int(top_n)]
    return _serialize({"count": len(tasks), "tasks": [t.to_dict() for t in tasks]})


@mcp.tool()
def get_task(uid: int | None = None, id: int | None = None, name: str | None = None) -> str:
    """Get the full record of a single task by UID, ID, or exact name.

    Args:
        uid: Task UID (the unique numeric identifier in MSPDI).
        id: Task ID (the row number shown in Project; not stable across edits).
        name: Exact task name (case-sensitive).

    Returns:
        JSON with all task fields, predecessors with link types, and resource
        assignments derived from the assignments table.
    """
    p = _project()
    task = None
    if uid is not None:
        task = p.task_by_uid(int(uid))
    elif id is not None:
        task = p.task_by_id(int(id))
    elif name:
        task = p.task_by_name(name)
    else:
        return _serialize({"error": "Provide one of: uid, id, name"})
    if task is None:
        return _serialize({"error": "Task not found"})
    assignments = [
        {**a.to_dict(), "resource_name": (
            r.name if (r := p.resource_by_uid(a.resource_uid)) else None
        )}
        for a in p.assignments if a.task_uid == task.uid
    ]
    return _serialize({**task.to_dict(), "assignments": assignments})


@mcp.tool()
def list_resources(only_overallocated: bool = False, type_filter: str | None = None) -> str:
    """List resources in the project.

    Args:
        only_overallocated: Return only resources flagged as overallocated.
        type_filter: Filter by resource type: 'Work', 'Material', or 'Cost'.

    Returns:
        JSON with array of resources including units, rates, and allocation status.
    """
    p = _project()
    resources = p.resources
    if only_overallocated:
        resources = [r for r in resources if r.overallocated]
    if type_filter:
        resources = [r for r in resources if r.type == type_filter]
    return _serialize({
        "count": len(resources),
        "resources": [r.to_dict() for r in resources],
    })


@mcp.tool()
def get_resource_assignments(
    resource_uid: int | None = None,
    resource_name: str | None = None,
) -> str:
    """List task assignments for one resource (or all resources if no filter given).

    Args:
        resource_uid: Resource UID to filter by.
        resource_name: Exact resource name to filter by.

    Returns:
        JSON with assignments enriched with task and resource names.
    """
    p = _project()
    target_uid = None
    if resource_uid is not None:
        target_uid = int(resource_uid)
    elif resource_name:
        r = p.resource_by_name(resource_name)
        if r is None:
            return _serialize({"error": f"Resource not found: {resource_name}"})
        target_uid = r.uid

    assignments = p.assignments
    if target_uid is not None:
        assignments = [a for a in assignments if a.resource_uid == target_uid]

    enriched = []
    for a in assignments:
        task = p.task_by_uid(a.task_uid)
        resource = p.resource_by_uid(a.resource_uid)
        enriched.append({
            **a.to_dict(),
            "task_name": task.name if task else None,
            "resource_name": resource.name if resource else None,
        })
    return _serialize({"count": len(enriched), "assignments": enriched})


@mcp.tool()
def find_overallocated_resources() -> str:
    """List resources flagged as overallocated by Microsoft Project.

    Returns:
        JSON with overallocated resources and the number of assignments for each.
    """
    p = _project()
    over = [r for r in p.resources if r.overallocated]
    result = []
    for r in over:
        assignments = [a for a in p.assignments if a.resource_uid == r.uid]
        result.append({
            **r.to_dict(),
            "assignment_count": len(assignments),
            "total_assigned_hours": round(sum(a.work_hours for a in assignments), 2),
        })
    return _serialize({"count": len(result), "overallocated": result})


@mcp.tool()
def get_critical_path() -> str:
    """Return tasks on the critical path (Critical=1 in MSPDI).

    Critical tasks have zero or negative slack and directly determine the
    project finish date. Sorted by start date.

    Returns:
        JSON with critical tasks ordered chronologically.
    """
    p = _project()
    critical = sorted(
        [t for t in p.tasks if t.is_critical and not t.is_summary],
        key=lambda t: t.start or "",
    )
    return _serialize({
        "count": len(critical),
        "total_critical_duration_hours": round(sum(t.duration_hours for t in critical), 2),
        "tasks": [t.to_dict() for t in critical],
    })


@mcp.tool()
def get_predecessors_successors(task_uid: int) -> str:
    """Return the dependency network for a task: its predecessors and successors.

    Args:
        task_uid: UID of the task to inspect.

    Returns:
        JSON with two arrays (predecessors, successors) listing linked tasks
        with their link type (FS/SS/FF/SF) and lag in hours.
    """
    p = _project()
    target = p.task_by_uid(int(task_uid))
    if target is None:
        return _serialize({"error": f"Task not found: uid={task_uid}"})

    predecessors = []
    for link in target.predecessors:
        pred = p.task_by_uid(link["predecessor_uid"])
        if pred:
            predecessors.append({
                "uid": pred.uid,
                "id": pred.id,
                "name": pred.name,
                "link_type": link["link_type"],
                "lag_hours": link["lag_hours"],
            })

    successors = []
    for t in p.tasks:
        for link in t.predecessors:
            if link["predecessor_uid"] == target.uid:
                successors.append({
                    "uid": t.uid,
                    "id": t.id,
                    "name": t.name,
                    "link_type": link["link_type"],
                    "lag_hours": link["lag_hours"],
                })

    return _serialize({
        "task": {"uid": target.uid, "id": target.id, "name": target.name},
        "predecessors_count": len(predecessors),
        "successors_count": len(successors),
        "predecessors": predecessors,
        "successors": successors,
    })


@mcp.tool()
def get_baseline_variance(only_off_track: bool = False) -> str:
    """Compare current dates against the saved baseline.

    Variance is computed in hours: positive = task is later than baseline,
    negative = task is earlier than baseline. Tasks without a baseline are skipped.

    Args:
        only_off_track: Return only tasks where current dates differ from baseline.

    Returns:
        JSON listing each task with current vs baseline dates and variance.
    """
    p = _project()
    rows = []
    for t in p.tasks:
        if t.is_summary or not t.baseline_finish:
            continue
        variance_hours = t.duration_hours - t.baseline_duration_hours
        unchanged = (
            variance_hours == 0
            and t.start == t.baseline_start
            and t.finish == t.baseline_finish
        )
        if only_off_track and unchanged:
            continue
        rows.append({
            "uid": t.uid,
            "id": t.id,
            "name": t.name,
            "start": t.start,
            "baseline_start": t.baseline_start,
            "finish": t.finish,
            "baseline_finish": t.baseline_finish,
            "duration_hours": round(t.duration_hours, 2),
            "baseline_duration_hours": round(t.baseline_duration_hours, 2),
            "duration_variance_hours": round(variance_hours, 2),
        })
    return _serialize({
        "count": len(rows),
        "tasks": rows,
    })


@mcp.tool()
def get_gantt_data(top_n: int | None = None, exclude_summaries: bool = False) -> str:
    """Return tasks formatted for Gantt-chart consumption.

    Each entry has the minimum fields needed by frontend Gantt libraries:
    id, name, start, end, duration_hours, percent_complete, parent_id (for
    hierarchy), and dependencies (predecessor list with link types).

    Args:
        top_n: Limit to the first N tasks.
        exclude_summaries: Drop summary rows so only leaf tasks remain.

    Returns:
        JSON array of Gantt-ready task dicts.
    """
    p = _project()
    tasks = p.tasks
    if exclude_summaries:
        tasks = [t for t in tasks if not t.is_summary]
    if top_n:
        tasks = tasks[: int(top_n)]

    parent_by_outline: dict[str, int] = {}
    for t in p.tasks:
        if t.outline_number:
            parent_by_outline[t.outline_number] = t.uid

    def _parent_uid(outline_number: str | None) -> int | None:
        if not outline_number or "." not in outline_number:
            return None
        parent_outline = outline_number.rsplit(".", 1)[0]
        return parent_by_outline.get(parent_outline)

    gantt = []
    for t in tasks:
        gantt.append({
            "id": t.uid,
            "name": t.name,
            "start": t.start,
            "end": t.finish,
            "duration_hours": round(t.duration_hours, 2),
            "percent_complete": t.percent_complete,
            "is_summary": t.is_summary,
            "is_milestone": t.is_milestone,
            "is_critical": t.is_critical,
            "parent_id": _parent_uid(t.outline_number),
            "outline_level": t.outline_level,
            "dependencies": [
                {
                    "from_id": link["predecessor_uid"],
                    "type": link["link_type"],
                    "lag_hours": link["lag_hours"],
                }
                for link in t.predecessors
            ],
        })
    return _serialize({"count": len(gantt), "gantt": gantt})


@mcp.tool()
def export_to_json(output_path: str | None = None) -> str:
    """Export the entire loaded project to a JSON file (or return inline).

    Args:
        output_path: Absolute path for the JSON output. If None, returns the
            full JSON inline (may be large).

    Returns:
        JSON with the output path and summary, or the full project JSON inline.
    """
    p = _project()
    payload = {
        "metadata": {
            "title": p.title,
            "name": p.name,
            "author": p.author,
            "company": p.company,
            "start_date": p.start_date,
            "finish_date": p.finish_date,
            "currency_code": p.currency_code,
            "source_path": p.source_path,
        },
        "tasks": [t.to_dict() for t in p.tasks],
        "resources": [r.to_dict() for r in p.resources],
        "assignments": [a.to_dict() for a in p.assignments],
    }
    if output_path:
        out = Path(output_path).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_serialize(payload), encoding="utf-8")
        return _serialize({
            "exported": True,
            "output_path": str(out.resolve()),
            "tasks": len(payload["tasks"]),
            "resources": len(payload["resources"]),
            "assignments": len(payload["assignments"]),
        })
    return _serialize(payload)


@mcp.tool()
def generate_pbip_dashboard(
    output_dir: str,
    project_name: str = "ProjectDashboard",
    open_in_power_bi: bool = True,
    xml_path: str | None = None,
) -> str:
    """Generate a Power BI Project (PBIP) dashboard from the loaded project.

    Creates a complete PBIP folder structure with SemanticModel (tables, measures,
    relationships) and a Report folder. The resulting folder can be opened in
    Power BI Desktop by double-clicking the .pbip file.

    The semantic model includes:
    - Three tables: Tarefas (non-summary tasks), Recursos (resources), Atribuicoes
      (assignments) with inline M-query partitions containing the project data.
    - Ten standard DAX measures (Avanco Geral, Custo Total, Tarefas Concluidas,
      Custo por Fase, etc.)
    - Two relationships (Atribuicoes -> Tarefas and Atribuicoes -> Recursos).
    - pt-BR culture.

    Args:
        output_dir: Absolute path to the folder where the PBIP project is written.
            The folder is created if missing.
        project_name: Name of the PBIP project (used as folder prefix and in the
            Power BI Desktop title bar). Defaults to "ProjectDashboard".
        open_in_power_bi: If True (default), launches Power BI Desktop on the
            generated .pbip file after writing.
        xml_path: Optional path to an MSPDI XML file to load before generating.
            If None, uses the currently-loaded project (load_project must have
            been called first).

    Returns:
        JSON with the output path, the .pbip file path, counts of what was
        written, and whether Power BI Desktop was launched.
    """
    if xml_path:
        file_path = Path(xml_path).expanduser()
        if not file_path.exists():
            return _serialize({"error": f"XML file not found: {xml_path}"})
        _state["project"] = mspdi.parse_file(file_path)

    project = _project()
    output = Path(output_dir).expanduser()

    writer = PbipWriter(project=project, output_dir=output, project_name=project_name)
    info = writer.write()

    launched = False
    launch_error: str | None = None
    if open_in_power_bi:
        pbip_file = info["pbip_file"]
        try:
            if os.name == "nt":
                os.startfile(pbip_file)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", pbip_file])
            launched = True
        except Exception as exc:
            launch_error = str(exc)

    return _serialize({
        **info,
        "opened_in_power_bi": launched,
        "launch_error": launch_error,
        "instructions": (
            "Open the .pbip file in Power BI Desktop (auto-launched if open_in_power_bi=True). "
            "After loading, add visuals to the 'Resumo' page: Card with [Avanco Geral], "
            "Card with [Custo Total], bar chart by Fase, and a table of critical tasks."
        ),
    })


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
