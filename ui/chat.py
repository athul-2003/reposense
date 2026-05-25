from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.spinner import Spinner
from rich.syntax import Syntax
from rich.text import Text

console = Console()


class show_thinking:
    """Context manager that shows a spinner while a block of code runs.

    Usage:
        with show_thinking("Querying Coral..."):
            result = run_query(sql)

    Also callable as a plain display call (shows then immediately hides):
        show_thinking("Starting up...").start()
    """

    def __init__(self, message: str) -> None:
        self.message = message
        self._live = Live(
            Spinner("dots", text=Text(f" {message}", style="cyan")),
            console=console,
            transient=True,
        )

    def __enter__(self):
        self._live.__enter__()
        return self

    def __exit__(self, *args):
        self._live.__exit__(*args)


def show_command_header(command: str, owner: str, repo: str, source_label: str) -> None:
    console.print(Rule(
        title=f"RepoSense · {owner}/{repo} · {command} · {source_label}",
        style="dim green",
    ))


def show_command_footer(rows_returned: int, elapsed: float, unit: str = "rows", cached: bool = False) -> None:
    cache_tag = " ⚡ cached" if cached else ""
    console.print(Rule(
        title=f"{rows_returned} {unit} · {elapsed:.1f}s · powered by Coral{cache_tag}",
        style="dim",
    ))
    console.print()


def _strip_sql_comments(sql: str) -> str:
    """Remove -- comment lines; keep the executable SQL clean for display."""
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    stripped = "\n".join(lines).strip()
    return stripped


def show_sql(sql: str, source_label: str) -> None:
    """Display syntax-highlighted SQL in a panel before query execution."""
    syntax = Syntax(_strip_sql_comments(sql), "sql", theme="monokai", word_wrap=True)
    console.print(
        Panel(
            syntax,
            title=f"📋 Coral SQL — {source_label}",
            border_style="dim green",
            padding=(1, 2),
        )
    )


def show_answer(title: str, content: str) -> None:
    """Display a Markdown-rendered answer in a styled panel."""
    console.print(
        Panel(
            Markdown(content),
            title=Text(title, style="bold green"),
            border_style="green",
            padding=(1, 2),
        )
    )


def show_error(message: str) -> None:
    """Display an error message in a red panel."""
    console.print(
        Panel(
            Text(message, style="red"),
            title="❌ Error",
            border_style="red",
            padding=(0, 2),
        )
    )
