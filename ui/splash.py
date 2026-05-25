import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, TaskProgressColumn
from rich.spinner import Spinner
from rich.text import Text

from agent.coral_runner import run_query

console = Console()

LOGO = """██████╗ ███████╗██████╗  ██████╗ ███████╗███████╗███╗   ██╗███████╗███████╗
██╔══██╗██╔════╝██╔══██╗██╔═══██╗██╔════╝██╔════╝████╗  ██║██╔════╝██╔════╝
██████╔╝█████╗  ██████╔╝██║   ██║███████╗█████╗  ██╔██╗ ██║███████╗█████╗
██╔══██╗██╔══╝  ██╔═══╝ ██║   ██║╚════██║██╔══╝  ██║╚██╗██║╚════██║██╔══╝
██║  ██║███████╗██║     ╚██████╔╝███████║███████╗██║ ╚████║███████║███████╗
╚═╝  ╚═╝╚══════╝╚═╝      ╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═══╝╚══════╝╚══════╝"""

_SQL_STALE_ISSUES = """SELECT COUNT(*) as count FROM (
  SELECT 1 FROM github.search_issues(
    q => 'repo:{owner}/{repo} is:issue is:open created:<{14_days_ago} comments:<2'
  ) LIMIT 50
) sub"""

_SQL_STALE_PRS = """SELECT COUNT(*) as count FROM (
  SELECT 1 FROM github.search_issues(
    q => 'repo:{owner}/{repo} is:pr is:open draft:false created:<{7_days_ago}'
  ) LIMIT 50
) sub"""

_SQL_MERGED_PRS = """SELECT COUNT(*) as count FROM (
  SELECT 1 FROM github.search_issues(
    q => 'repo:{owner}/{repo} is:pr is:merged merged:>{7_days_ago}'
  ) LIMIT 50
) sub"""

_SQL_CLOSED_ISSUES = """SELECT COUNT(*) as count FROM (
  SELECT 1 FROM github.search_issues(
    q => 'repo:{owner}/{repo} is:issue is:closed closed:>{7_days_ago}'
  ) LIMIT 50
) sub"""


def _health_color(score: int) -> str:
    if score > 70:
        return "green"
    if score >= 40:
        return "yellow"
    return "red"


def _parse_count(result: str) -> int:
    for line in result.splitlines():
        m = re.search(r'\|\s*(\d+)\s*\|', line)
        if m:
            return int(m.group(1))
    return 0


def calculate_health_score(owner: str, repo: str) -> tuple[int, str]:
    signals = {
        "stale_issues":  _SQL_STALE_ISSUES,
        "stale_prs":     _SQL_STALE_PRS,
        "merged_prs":    _SQL_MERGED_PRS,
        "closed_issues": _SQL_CLOSED_ISSUES,
    }
    counts: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(run_query, sql, owner, repo): key
            for key, sql in signals.items()
        }
        for fut in as_completed(futures):
            counts[futures[fut]] = _parse_count(fut.result())

    stale_issues  = counts["stale_issues"]
    stale_prs     = counts["stale_prs"]
    merged_prs    = counts["merged_prs"]
    closed_issues = counts["closed_issues"]

    score = 100
    score -= min(stale_issues * 3, 40)
    score -= min(stale_prs    * 2, 30)
    score += min(merged_prs   * 2, 20)
    score += min(closed_issues * 1, 10)
    score = max(0, min(100, score))

    merged_label = f"{merged_prs}+" if merged_prs >= 50 else str(merged_prs)
    if score > 70:
        summary = f"Healthy — {merged_label} PRs merged this week"
    elif score >= 40:
        summary = f"{stale_prs} stale PRs and {stale_issues} aging issues need attention"
    else:
        summary = f"Needs attention — {stale_issues} issues ignored for 14+ days"

    return score, summary


def show_splash_logo() -> None:
    """Show logo and subtitle only — used before the repo is known."""
    console.clear()
    console.print(Align.center(Text(LOGO, style="bold green")))
    console.print(
        Align.center(
            Text("AI-powered repo intelligence · powered by Coral", style="dim cyan")
        )
    )
    console.print()


def show_splash(owner: str, repo: str) -> None:
    console.clear()

    console.print(Align.center(Text(LOGO, style="bold green")))
    console.print(
        Align.center(
            Text("AI-powered repo intelligence · powered by Coral", style="dim cyan")
        )
    )
    console.print()

    panel_text = Text("Analysing: ", style="white")
    panel_text.append(f"{owner}/{repo}", style="bold white")
    console.print(Panel(Align.center(panel_text), border_style="green", padding=(0, 4)))

    console.print(
        Align.center(Text("github · hacker news · osv · stackoverflow · dev.to · openssf scorecard · 12 features · powered by Coral", style="dim white"))
    )
    console.print()

    with Live(
        Spinner("dots", text="  Calculating repo health..."),
        console=console,
        transient=True,
    ):
        health_score, summary = calculate_health_score(owner, repo)

    color = _health_color(health_score)
    with Progress(
        TextColumn("  [bold]Repo Health Score[/bold]"),
        BarColumn(bar_width=40, style=color, complete_style=color),
        TaskProgressColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("", total=100)
        progress.update(task, completed=health_score)

    console.print(Text(f"  {summary}", style=f"dim {color}"))
    console.print()
