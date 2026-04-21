# project-mcp

[![CI](https://github.com/jeffmodeler/project-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/jeffmodeler/project-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

> 🇺🇸 English · 🇧🇷 [Versão em português](README.pt-BR.md)

Model Context Protocol (MCP) server that exposes Microsoft Project files
to LLM clients like Claude Desktop and Claude Code. Reads schedules, resources,
dependencies, critical-path data, and baseline variance — and adds **AWP**
(Advanced Work Packaging, CII) and **LPS** (Last Planner System, Lean) layers
for work-package planning, constraints, weekly commitments and PPC tracking.
All local, no cloud calls, no Microsoft Project license required.

## Why

Construction, engineering, and BIM workflows live in Microsoft Project
schedules. This server lets your LLM:

- Inspect a project schedule and answer questions about it (deadlines,
  critical path, resource overload).
- Cross-reference task data with quantities from BIM models or with
  cost data from Power BI dashboards.
- Generate JSON exports for downstream automation (dashboards, reports,
  ETL pipelines).

It's read-only by design. Project edits stay where they belong: in
Microsoft Project itself.

## Requirements

- Python 3.11+
- An MCP-compatible client (Claude Desktop, Claude Code, etc.)
- For `.xml` (MSPDI): no extra dependencies
- For `.mpp` (native Microsoft Project): the optional `[mpp]` extra (requires
  a JVM via the `mpxj` package)

## Installation

### Option A — `uv` (recommended)

```bash
git clone https://github.com/jeffmodeler/project-mcp.git
cd project-mcp
uv sync
```

### Option B — `pip`

```bash
pip install git+https://github.com/jeffmodeler/project-mcp.git
```

For `.mpp` support:

```bash
uv sync --extra mpp
# or
pip install "project-mcp[mpp] @ git+https://github.com/jeffmodeler/project-mcp.git"
```

## Claude Desktop integration

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "project-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "C:\\path\\to\\project-mcp",
        "run",
        "project-mcp"
      ]
    }
  }
}
```

Restart Claude Desktop. The 35 tools become available in any conversation
(13 core MS Project + 10 AWP + 12 LPS).

## Tools

| Tool | Purpose |
|---|---|
| `load_project` | Load an MSPDI `.xml` or `.mpp` file into memory |
| `project_info` | Title, author, schedule window, currency, aggregate counts |
| `list_tasks` | Filter tasks by type, criticality, name substring, top N |
| `get_task` | Full record of a single task by UID, ID, or name |
| `list_resources` | Resources, optionally filtered by type or overallocation |
| `get_resource_assignments` | Assignments for one or all resources |
| `find_overallocated_resources` | Resources flagged as overallocated |
| `get_critical_path` | Tasks on the critical path, sorted by start date |
| `get_predecessors_successors` | Dependency network for a task |
| `get_baseline_variance` | Current vs baseline date and duration comparison |
| `get_gantt_data` | Tasks formatted for Gantt-chart libraries |
| `export_to_json` | Full project export to JSON file (or inline) |
| `generate_pbip_dashboard` | Generate a Power BI Project (.pbip) and open it in Power BI Desktop |

## Exporting `.mpp` to MSPDI XML

If you don't want to install Java for the optional `mpp` extra, export your
schedule from Microsoft Project as XML:

1. Open the `.mpp` file in Microsoft Project.
2. **File → Save As → Save as Type → XML Format (\*.xml)**.
3. Point `load_project` at the resulting `.xml`.

The XML format is the official Microsoft Project Data Interchange (MSPDI)
schema and contains tasks, resources, assignments, predecessors, baseline,
and most of the project metadata.

## Example prompts

After loading a project, ask Claude:

```
Load the project at C:\schedules\obra-acme.xml
Give me the critical path with total duration in days.
Which resources are overallocated and by how much?
List the 5 tasks with the largest baseline variance.
Export the full project to C:\reports\obra-acme.json
```

## AWP — Advanced Work Packaging

Construction Industry Institute (CII) methodology. Breaks execution into
aligned packages across engineering, procurement and field:

```
CWA (Construction Work Area) → CWP (Construction Work Package)
                                     ↓
                               IWP (Installation Work Package)
```

Focus: path of construction + readiness (nothing starts in the field until
materials, documents and access are available).

### AWP tools

| Tool | Purpose |
|---|---|
| `awp_list_cwa` | List Construction Work Areas |
| `awp_upsert_cwa` | Create or update a CWA |
| `awp_list_cwp` | List CWPs with `task_count`, `total_hours`, `any_critical` |
| `awp_upsert_cwp` | Create or update a CWP (status: planned/ready/in-progress/complete/on-hold) |
| `awp_assign_task_to_cwp` | Link a task UID to a CWP (moves it if already elsewhere) |
| `awp_set_cwp_requirements` | Set CWP requirements (materials, documents, access) |
| `awp_readiness_check` | Check whether a CWP is ready — compares requirements vs available |
| `awp_path_of_construction` | Sequence CWPs by earliest start, with critical-task counts |
| `awp_generate_iwps` | Split a CWP into IWPs sized by labor hours |
| `awp_export_wpr` | Generate a Work Package Release — self-contained JSON for field teams |

## LPS — Last Planner System

Lean Construction method with five planning levels:

```
Master → Phase (pull plan) → Lookahead (N weeks, clears constraints)
                              → WWP (Weekly Work Plan) → Daily huddle
```

Key metric: **PPC** (Percent Plan Complete) — commitments kept / commitments made.

### LPS tools

| Tool | Purpose |
|---|---|
| `lps_list_phases` | List project phases |
| `lps_upsert_phase` | Create or update a phase (with start/end dates) |
| `lps_set_pull_plan` | Set execution sequence (pull planning) with task UIDs |
| `lps_get_pull_plan` | Retrieve a phase's pull plan |
| `lps_register_constraint` | Register a constraint (material/document/labor/equipment/access/permit/…) |
| `lps_clear_constraint` | Mark a constraint as resolved |
| `lps_list_constraints` | List with filters by task, status, type |
| `lps_lookahead` | N-week horizon with ready/blocked tasks (from open constraints) |
| `lps_add_commitment` | Add a commitment to a weekly work plan (ISO week e.g. `2026-W03`) |
| `lps_mark_complete` | Close a commitment with `actual_hours` or `variance_reason` |
| `lps_get_wwp` | Read a weekly work plan |
| `lps_ppc` | Compute PPC for a single week or a series of the last N weeks |

**Constraint types**: material, document, information, design, labor,
equipment, access, permit, prerequisite, other.

**Variance reasons**: weather, design_change, material_delay, labor_unavailable,
equipment_breakdown, rework, permit, prerequisite_incomplete, scope_change, other.

## Sidecar storage

The `.mpp`/`.xml` file remains authoritative (read-only preserved). Next to
the project file, an `<name>.awp/` folder holds metadata that Microsoft
Project does not represent well:

```
C:\schedules\
├── obra-acme.mpp              ← authoritative schedule (never modified)
└── obra-acme.awp/             ← sidecar folder, created on demand
    ├── awp.json               ← CWA / CWP / IWP hierarchy
    └── lps.json               ← phases, pull plans, constraints, WWPs
```

Every write updates `updated_at` (ISO 8601 UTC) in the JSON.

## Development

```bash
uv sync --extra dev
uv run pytest -v
uv run ruff check src tests
```

## License

MIT — see [LICENSE](LICENSE).
