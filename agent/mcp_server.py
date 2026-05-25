"""RepoSense MCP server.

Exposes RepoSense's Coral-powered commands as MCP tools so any MCP client
(Claude Desktop, Continue, Cursor, etc.) can call them directly.

Usage:
    reposense --mcp                # stdio transport (Claude Desktop)
    reposense --mcp --repo o/r     # default repo pre-set

Claude Desktop config (~/.config/claude/claude_desktop_config.json):
    {
      "mcpServers": {
        "reposense": {
          "command": "reposense",
          "args": ["--mcp"]
        }
      }
    }
"""

import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from agent.coral_runner import run_query, get_installed_sources, get_table_columns, substitute_tokens

app = Server("reposense")

# ── Tool definitions ──────────────────────────────────────────────────────────

_COMMANDS = [
    "triage", "stale-prs", "release-notes", "contributors",
    "hn-buzz", "cve-scan", "duplicates", "health",
    "pulse", "so-buzz", "dev-buzz", "scorecard",
]


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="run_command",
            description=(
                "Run one of RepoSense's 12 built-in commands against any GitHub repo. "
                "Each command queries live data via Coral SQL. Results are cached "
                "to disk for 5 minutes (matching Coral's own HTTP cache window) — "
                "repeated calls return instantly with a ⚡ cached indicator. "
                f"Available commands: {', '.join(_COMMANDS)}. "
                "Returns formatted results as text."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "enum": _COMMANDS,
                        "description": "The RepoSense command to run.",
                    },
                    "owner": {
                        "type": "string",
                        "description": "GitHub organisation or username (e.g. 'django').",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name (e.g. 'django').",
                    },
                },
                "required": ["command", "owner", "repo"],
            },
        ),
        types.Tool(
            name="coral_sql",
            description=(
                "Execute any SQL query directly against Coral's live data sources "
                "(GitHub, Hacker News, OSV, Scorecard, Stack Overflow, Dev.to, and more). "
                "Supports cross-source JOINs. Tokens {owner}, {repo}, {7_days_ago}, "
                "{14_days_ago}, {30_days_ago} are substituted automatically."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "A complete SQL SELECT statement.",
                    },
                    "owner": {
                        "type": "string",
                        "description": "GitHub owner for token substitution.",
                    },
                    "repo": {
                        "type": "string",
                        "description": "GitHub repo for token substitution.",
                    },
                },
                "required": ["sql"],
            },
        ),
        types.Tool(
            name="list_sources",
            description=(
                "List all Coral data sources and tables currently installed on this machine. "
                "Use this to discover what data is queryable before running coral_sql."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Optional: source name to get column details for a specific table.",
                    },
                    "table": {
                        "type": "string",
                        "description": "Optional: table name (requires source).",
                    },
                },
                "required": [],
            },
        ),
    ]


# ── SQL files map ─────────────────────────────────────────────────────────────

import os

_QUERIES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "queries")

# Commands whose SQL files contain multiple queries separated by -- ==QUERY_X==
_MULTI_QUERY_COMMANDS = {"cve-scan"}

# Commands implemented in Python (no single SQL file)
_PYTHON_COMMANDS = {"health"}

_COMMAND_SQL: dict[str, str] = {
    "triage":        "triage.sql",
    "stale-prs":     "stale_prs.sql",
    "release-notes": "release_notes.sql",
    "contributors":  "contributors.sql",
    "hn-buzz":       "hn_buzz.sql",
    "cve-scan":      "cve_scan.sql",
    "duplicates":    "duplicates.sql",
    "pulse":         "pulse.sql",
    "so-buzz":       "so_buzz.sql",
    "dev-buzz":      "dev_buzz.sql",
    "scorecard":     "scorecard.sql",
}


def _load_sql(filename: str) -> str:
    path = os.path.join(_QUERIES_DIR, filename)
    with open(path) as f:
        return f.read()


def _split_queries(sql: str) -> list[str]:
    """Split a multi-query SQL file by the -- ==QUERY_X== delimiter."""
    import re
    parts = re.split(r"--\s*==QUERY_\w+==", sql)
    return [p.strip() for p in parts if p.strip()]


def _run_command(command: str, owner: str, repo: str) -> str:
    if command == "health":
        from ui.splash import calculate_health_score
        score, summary = calculate_health_score(owner, repo)
        return f"Repo health score: {score}%\n{summary}"

    filename = _COMMAND_SQL.get(command)
    if not filename:
        return f"Unknown command: {command}"

    raw_sql = _load_sql(filename)

    if command in _MULTI_QUERY_COMMANDS:
        queries = _split_queries(raw_sql)
        parts = []
        for i, sql in enumerate(queries, 1):
            result = run_query(sql, owner, repo)
            parts.append(f"--- Query {i} ---\n{result}")
        return "\n\n".join(parts)

    return run_query(raw_sql, owner, repo)


# ── Tool handler ──────────────────────────────────────────────────────────────

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        if name == "run_command":
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                _run_command,
                arguments["command"],
                arguments["owner"],
                arguments["repo"],
            )
        elif name == "coral_sql":
            owner = arguments.get("owner", "withcoral")
            repo = arguments.get("repo", "coral")
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                run_query,
                arguments["sql"],
                owner,
                repo,
            )
        elif name == "list_sources":
            source = arguments.get("source", "")
            table = arguments.get("table", "")
            if source and table:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, get_table_columns, source, table
                )
            else:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, get_installed_sources
                )
        else:
            result = f"Unknown tool: {name}"
    except Exception as exc:
        result = f"Error: {type(exc).__name__}: {exc}"

    return [types.TextContent(type="text", text=str(result))]


# ── Entry point ───────────────────────────────────────────────────────────────

def run_mcp_server() -> None:
    """Start the RepoSense MCP server over stdio."""
    async def _main():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
            )
    asyncio.run(_main())
