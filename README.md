# project-mcp

[![CI](https://github.com/jeffmodeler/project-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/jeffmodeler/project-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Model Context Protocol (MCP) server that exposes Microsoft Project files
to LLM clients like Claude Desktop. Reads schedules, resources, dependencies,
critical-path data, and baseline variance — all locally, with no cloud calls
and no Microsoft Project license required.

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

Restart Claude Desktop. The 12 tools become available in any conversation.

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

## Development

```bash
uv sync --extra dev
uv run pytest -v
uv run ruff check src tests
```

## License

MIT — see [LICENSE](LICENSE).
