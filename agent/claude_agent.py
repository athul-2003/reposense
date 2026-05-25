import json
import os
import time

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule

from agent.coral_runner import run_query, get_installed_sources, get_table_columns
from agent.prompts import SYSTEM_PROMPT
from ui.chat import show_sql, show_thinking, show_error

console = Console()

_CLAUDE_TOOL_QUERY = {
    "name": "coral_query",
    "description": (
        "Execute a SQL query against Coral (GitHub, Hacker News, OSV, and other installed sources). "
        "Returns ASCII table output or an error string."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "The complete SQL SELECT statement to run."}
        },
        "required": ["sql"],
    },
}

_CLAUDE_TOOL_SCHEMA = {
    "name": "coral_schema",
    "description": (
        "Inspect the live Coral schema — discover installed sources, tables, and columns. "
        "Call with no arguments to list all sources and tables. "
        "Pass source and table to get column details for that table."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "Source name (e.g. 'github', 'scorecard'). Optional."},
            "table":  {"type": "string", "description": "Table name within the source. Required if source is given."},
        },
        "required": [],
    },
}

_OPENAI_TOOL_QUERY = {
    "type": "function",
    "function": {
        "name": "coral_query",
        "description": (
            "Execute a SQL query against Coral (GitHub, Hacker News, OSV, and other installed sources). "
            "Returns ASCII table output or an error string."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "The complete SQL SELECT statement to run."}
            },
            "required": ["sql"],
        },
    },
}

_OPENAI_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "coral_schema",
        "description": (
            "Inspect the live Coral schema — discover installed sources, tables, and columns. "
            "Call with no arguments to list all sources and tables. "
            "Pass source and table to get column details for that table."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Source name (e.g. 'github', 'scorecard'). Optional."},
                "table":  {"type": "string", "description": "Table name within the source. Required if source is given."},
            },
            "required": [],
        },
    },
}

# Backward-compat aliases (used in tool dispatch below)
_CLAUDE_TOOL = _CLAUDE_TOOL_QUERY
_OPENAI_TOOL = _OPENAI_TOOL_QUERY


class _ClaudeBackend:
    def __init__(self, api_key: str) -> None:
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = os.getenv("ANTHROPIC_MODEL") or os.getenv("REPOSENSE_MODEL", "claude-sonnet-4-6")
        self.messages: list = []

    def add_user(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def call(self):
        return self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=[_CLAUDE_TOOL_QUERY, _CLAUDE_TOOL_SCHEMA],
            messages=self.messages,
        )

    def is_final(self, response) -> bool:
        return response.stop_reason == "end_turn"

    def get_text(self, response) -> str:
        for block in response.content:
            if hasattr(block, "text") and block.text.strip():
                return block.text
        return ""

    def get_tool_calls(self, response) -> list[dict]:
        calls = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == "coral_schema":
                calls.append({
                    "id": block.id,
                    "tool": "coral_schema",
                    "source": block.input.get("source", ""),
                    "table": block.input.get("table", ""),
                    "sql": "",
                })
            else:
                calls.append({
                    "id": block.id,
                    "tool": "coral_query",
                    "sql": block.input.get("sql", ""),
                })
        return calls

    def append_assistant(self, response) -> None:
        self.messages.append({"role": "assistant", "content": response.content})

    def append_tool_results(self, results: list[dict]) -> None:
        self.messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": r["id"], "content": r["content"]}
            for r in results
        ]})

    @property
    def label(self) -> str:
        return f"Claude ({self.model})"


class _OpenAIBackend:
    def __init__(self, api_key: str, base_url: str | None = None, default_model: str = "gpt-4o-mini") -> None:
        import openai
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url)
        self.model = os.getenv("OPENAI_MODEL") or os.getenv("REPOSENSE_MODEL", default_model)
        self.messages: list = [{"role": "system", "content": SYSTEM_PROMPT}]

    def add_user(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def call(self):
        return self.client.chat.completions.create(
            model=self.model,
            max_tokens=4096,
            tools=[_OPENAI_TOOL_QUERY, _OPENAI_TOOL_SCHEMA],
            messages=self.messages,
        )

    def is_final(self, response) -> bool:
        return response.choices[0].finish_reason == "stop"

    def get_text(self, response) -> str:
        return response.choices[0].message.content or ""

    def get_tool_calls(self, response) -> list[dict]:
        raw_calls = response.choices[0].message.tool_calls or []
        result = []
        for c in raw_calls:
            args = json.loads(c.function.arguments)
            if c.function.name == "coral_schema":
                result.append({
                    "id": c.id,
                    "tool": "coral_schema",
                    "source": args.get("source", ""),
                    "table": args.get("table", ""),
                    "sql": "",
                })
            else:
                result.append({
                    "id": c.id,
                    "tool": "coral_query",
                    "sql": args.get("sql", ""),
                })
        return result

    def append_assistant(self, response) -> None:
        msg = response.choices[0].message
        self.messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": msg.tool_calls,
        })

    def append_tool_results(self, results: list[dict]) -> None:
        for r in results:
            self.messages.append({
                "role": "tool",
                "tool_call_id": r["id"],
                "content": r["content"],
            })

    @property
    def label(self) -> str:
        return f"OpenAI ({self.model})"


class _GroqBackend(_OpenAIBackend):
    def __init__(self, api_key: str) -> None:
        super().__init__(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
            default_model="llama-3.3-70b-versatile",
        )
        if groq_model := os.getenv("GROQ_MODEL"):
            self.model = groq_model

    @property
    def label(self) -> str:
        return f"Groq ({self.model})"


MAX_AGENT_TURNS = 10  # safety cap — prevents runaway loops burning API credits


def _get_backend() -> _ClaudeBackend | _OpenAIBackend | _GroqBackend | None:
    if key := os.getenv("ANTHROPIC_API_KEY"):
        return _ClaudeBackend(key)
    if key := os.getenv("GROQ_API_KEY"):
        return _GroqBackend(key)
    if key := os.getenv("OPENAI_API_KEY"):
        return _OpenAIBackend(key)
    return None


def run_agent(question: str, owner: str, repo: str) -> None:
    """Agentic loop: chosen LLM decides which Coral queries to run, interprets results."""
    backend = _get_backend()
    if backend is None:
        console.print(
            Panel(
                "[yellow]No API key found — free-form questions need one.[/yellow]\n\n"
                "Set any one of:\n"
                "  [bold]ANTHROPIC_API_KEY=sk-ant-...[/bold]  (Claude — recommended)\n"
                "  [bold]GROQ_API_KEY=gsk_...[/bold]          (Llama 3.3 via Groq — free)\n"
                "  [bold]OPENAI_API_KEY=sk-...[/bold]         (GPT-4o)\n\n"
                "[dim]All 12 commands work without an API key:\n"
                "triage · stale-prs · contributors · hn-buzz · cve-scan · release-notes\n"
                "duplicates · health · pulse · so-buzz · dev-buzz · scorecard[/dim]",
                title="💡 Agent mode unavailable",
                border_style="yellow",
                padding=(0, 2),
            )
        )
        return

    with show_thinking("Loading Coral schema…"):
        schema_context = get_installed_sources()

    backend.add_user(
        f"Repo: {owner}/{repo}\n\n"
        f"{schema_context}\n\n"
        f"Question: {question}"
    )

    start = time.time()
    query_count = 0
    turn = 0

    console.print(Rule(
        title=f"RepoSense Agent · {owner}/{repo}",
        style="dim cyan",
    ))

    while turn < MAX_AGENT_TURNS:
        turn += 1
        try:
            with show_thinking("Agent thinking…"):
                response = backend.call()
        except Exception as exc:
            err_msg = str(exc)
            if "Connection" in type(exc).__name__ or "connect" in err_msg.lower() or "name resolution" in err_msg.lower():
                console.print(Panel(
                    "[yellow]Could not reach the AI API — check your internet connection.[/yellow]\n\n"
                    f"[dim]Error: {err_msg[:120]}[/dim]",
                    title="🔌 Connection error",
                    border_style="yellow",
                    padding=(0, 2),
                ))
            else:
                console.print(Panel(
                    f"[red]{type(exc).__name__}: {err_msg[:200]}[/red]",
                    title="❌ Agent error",
                    border_style="red",
                    padding=(0, 2),
                ))
            return

        if backend.is_final(response):
            text = backend.get_text(response)
            if text:
                console.print(Panel(
                    Markdown(text),
                    title="🪸 RepoSense",
                    border_style="cyan",
                    padding=(1, 2),
                ))
            elapsed = time.time() - start
            console.print(Rule(
                title=f"{query_count} queries · {elapsed:.1f}s · powered by Coral + {backend.label}",
                style="dim",
            ))
            console.print()
            break

        else:
            backend.append_assistant(response)
            tool_calls = backend.get_tool_calls(response)
            results = []
            for call in tool_calls:
                if call["tool"] == "coral_schema":
                    src = call.get("source", "")
                    tbl = call.get("table", "")
                    if src and tbl:
                        show_sql(
                            f"SELECT column_name, data_type FROM information_schema.columns "
                            f"WHERE table_schema='{src}' AND table_name='{tbl}'",
                            "Schema lookup",
                        )
                        with show_thinking("Inspecting schema…"):
                            result = get_table_columns(src, tbl)
                    else:
                        show_sql(
                            "SELECT table_schema, table_name FROM information_schema.tables",
                            "Schema discovery",
                        )
                        with show_thinking("Discovering sources…"):
                            result = get_installed_sources()
                else:
                    query_count += 1
                    show_sql(call["sql"], f"Coral query {query_count}")
                    with show_thinking(f"Running query {query_count}…"):
                        result = run_query(call["sql"], owner, repo)
                    if result.startswith("Error:"):
                        show_error(result)
                results.append({"id": call["id"], "content": result})
            backend.append_tool_results(results)

    else:
        console.print(Panel(
            f"[yellow]Agent stopped after {MAX_AGENT_TURNS} turns without a final answer.[/yellow]\n"
            "[dim]Try a more specific question or run a direct command instead.[/dim]",
            title="⚠ Agent turn limit reached",
            border_style="yellow",
            padding=(0, 2),
        ))
