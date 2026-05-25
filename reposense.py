import os
import time
import click
from dotenv import load_dotenv
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Search CWD upward, then fall back to ~/.env so the command works from any directory
load_dotenv()
load_dotenv(Path.home() / ".env", override=False)

from agent.claude_agent import run_agent
from agent.coral_runner import run_query, parse_table_output, substitute_tokens, validate_repo_slug, detect_package, last_was_cached
from ui.chat import (
    show_sql, show_answer, show_error, show_thinking,
    show_command_header, show_command_footer,
)
from ui.tables import (
    render_issue_table, render_contributor_table,
    render_hn_table, render_duplicates_table, render_cve_table,
    render_dependabot_table, render_pulse_table, render_so_table,
    render_stale_prs_table, render_dev_table, render_scorecard_table,
)
from ui.splash import show_splash, show_splash_logo

console = Console()

DEFAULT_OWNER = os.getenv("GITHUB_OWNER", "withcoral")
DEFAULT_REPO = os.getenv("GITHUB_REPO", "coral")


def _read_sql(filename: str) -> str:
    path = os.path.join(os.path.dirname(__file__), "queries", filename)
    with open(path) as f:
        return f.read()


def _resolve_repo(repo_flag: str | None) -> tuple[str, str]:
    """Parse owner/repo from --repo flag, env vars, or hardcoded default."""
    if repo_flag:
        parts = repo_flag.split("/", 1)
        if len(parts) == 2:
            try:
                validate_repo_slug(parts[0], "owner")
                validate_repo_slug(parts[1], "repo")
            except ValueError as e:
                raise click.BadParameter(str(e), param_hint="'--repo'")
            return parts[0], parts[1]
        raise click.BadParameter("--repo must be in owner/repo format", param_hint="'--repo'")
    return DEFAULT_OWNER, DEFAULT_REPO


def _prompt_repo() -> tuple[str, str]:
    """Interactively ask the user which repo to analyse. Re-prompts on bad input."""
    console.print(
        Panel(
            "\n".join([
                "[bold white]🔍 Which repo do you want to analyse?[/bold white]",
                "",
                "  Enter as [green]owner/repo[/green]",
                "  Examples: [dim]vercel/next.js · django/django[/dim]",
                f"  Press Enter for default: [dim cyan]{DEFAULT_OWNER}/{DEFAULT_REPO}[/dim cyan]",
            ]),
            border_style="cyan",
            padding=(0, 2),
        )
    )
    while True:
        try:
            raw = console.input("\n[bold cyan]repo >[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            return DEFAULT_OWNER, DEFAULT_REPO
        if not raw:
            return DEFAULT_OWNER, DEFAULT_REPO
        parts = raw.split("/", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            console.print("[red]  ✗ Must be owner/repo format — e.g. django/django[/red]")
            continue
        try:
            validate_repo_slug(parts[0], "owner")
            validate_repo_slug(parts[1], "repo")
        except ValueError as e:
            console.print(f"[red]  ✗ {e}[/red]")
            continue
        return parts[0], parts[1]


def _run_and_display(
    sql: str, title: str, owner: str, repo: str,
    border: str = "green", footer: str = "",
) -> None:
    with show_thinking(f"Querying Coral · {title}…"):
        result = run_query(sql, owner=owner, repo=repo)
    if result.startswith("Error:"):
        show_error(result)
        return
    body = Text(result)
    panel = Panel(body, title=title, border_style=border, padding=(0, 1))
    console.print(panel)
    if footer:
        console.print(Text(f"  {footer}", style="dim cyan"))
    console.print()


def _show_help() -> None:
    console.print(
        Panel(
            "\n".join([
                "[bold cyan]Commands:[/bold cyan]",
                "",
                "  [green]triage[/green]        — Open issues needing attention",
                "  [green]stale-prs[/green]     — PRs open > 7 days",
                "  [green]contributors[/green]  — Activity rollup (last 30 days)",
                "  [green]health[/green]        — Repo health score (4 live signals)",
                "  [green]hn-buzz[/green]       — Hacker News posts about this project ★",
                "  [green]cve-scan[/green]      — Known CVEs for project dependencies ★",
                "  [green]release-notes[/green] — Merged PRs for release notes",
                "  [green]duplicates[/green]    — Similar open issues (CROSS JOIN) ★",
                "  [green]pulse[/green]         — HN × GitHub (cross-source SQL JOIN) ★",
                "  [green]so-buzz[/green]       — Stack Overflow questions about this tech ★",
                "  [green]dev-buzz[/green]      — Dev.to articles trending about this tech ★",
                "  [green]scorecard[/green]    — OpenSSF security posture (18 checks, zero config) ★★",
                "",
                "[bold cyan]Or ask anything in plain English:[/bold cyan]",
                "",
                "  [dim]Which issues have the most comments?[/dim]",
                "  [dim]Who opened the most PRs this month?[/dim]",
                "  [dim]Are there any open bugs labelled critical?[/dim]",
                "  [dim]How many issues were opened vs closed this month?[/dim]",
                "",
                "  [dim]Or directly: [bold]reposense --repo owner/repo ask \"question\"[/bold][/dim]",
                "  [dim]Type [bold]quit[/bold] to exit · needs an API key for agent mode[/dim]",
                "  [dim](ANTHROPIC_API_KEY / GROQ_API_KEY / OPENAI_API_KEY)[/dim]",
            ]),
            title="🪸 RepoSense",
            border_style="cyan",
            padding=(0, 2),
        )
    )


_EXACT_COMMANDS = {
    "triage", "stale-prs", "stale_prs",
    "contributors", "contributor",
    "hn-buzz", "hn_buzz", "hn",
    "cve-scan", "cve_scan", "cve",
    "release-notes", "release_notes", "release",
    "duplicates", "duplicate",
    "health", "score",
    "pulse",
    "so-buzz", "so_buzz", "so",
    "dev-buzz", "dev_buzz", "dev",
    "scorecard", "security", "ossf",
}

def _match_command(text: str) -> str | None:
    """Match only if the user typed an exact command name (single word/token).
    Natural language questions go to the agent — do not fuzzy-match them."""
    t = text.lower().strip()
    if t not in _EXACT_COMMANDS:
        return None
    if t in ("triage",):
        return "triage"
    if t in ("stale-prs", "stale_prs"):
        return "stale-prs"
    if t in ("contributors", "contributor"):
        return "contributors"
    if t in ("hn-buzz", "hn_buzz", "hn"):
        return "hn-buzz"
    if t in ("cve-scan", "cve_scan", "cve"):
        return "cve-scan"
    if t in ("release-notes", "release_notes", "release"):
        return "release-notes"
    if t in ("duplicates", "duplicate"):
        return "duplicates"
    if t in ("health", "score"):
        return "health"
    if t in ("pulse",):
        return "pulse"
    if t in ("so-buzz", "so_buzz", "so"):
        return "so-buzz"
    if t in ("dev-buzz", "dev_buzz", "dev"):
        return "dev-buzz"
    if t in ("scorecard", "security", "ossf"):
        return "scorecard"
    return None


# ── commands ──────────────────────────────────────────────────────────────────

def cmd_triage(owner: str, repo: str) -> None:
    sql = _read_sql("triage.sql")
    show_command_header("triage", owner, repo, "github")
    show_sql(substitute_tokens(sql, owner, repo), "github")
    start = time.time()
    with show_thinking("Querying Coral · Triage…"):
        result = run_query(sql, owner=owner, repo=repo)
    elapsed = time.time() - start
    if result.startswith("Error:"):
        show_error(result)
        return
    rows = parse_table_output(result)
    if not rows:
        console.print("[dim]  No items found.[/dim]")
        return
    console.print(render_issue_table(rows))
    show_command_footer(len(rows), elapsed, cached=last_was_cached())


def cmd_stale_prs(owner: str, repo: str) -> None:
    sql = _read_sql("stale_prs.sql")
    show_command_header("stale-prs", owner, repo, "github")
    show_sql(substitute_tokens(sql, owner, repo), "github")
    start = time.time()
    with show_thinking("Querying Coral · Stale PRs…"):
        result = run_query(sql, owner=owner, repo=repo)
    elapsed = time.time() - start
    if result.startswith("Error:"):
        show_error(result)
        return
    rows = parse_table_output(result)
    if not rows:
        console.print("[dim]  No stale PRs found.[/dim]")
        show_command_footer(0, elapsed, cached=last_was_cached())
        return
    console.print(render_stale_prs_table(rows))
    show_command_footer(len(rows), elapsed, cached=last_was_cached())


def cmd_contributors(owner: str, repo: str) -> None:
    sql = _read_sql("contributors.sql")
    show_command_header("contributors", owner, repo, "github")
    show_sql(substitute_tokens(sql, owner, repo), "github")
    start = time.time()
    with show_thinking("Querying Coral · Contributors…"):
        result = run_query(sql, owner=owner, repo=repo)
    elapsed = time.time() - start
    if result.startswith("Error:"):
        show_error(result)
        return
    rows = parse_table_output(result)
    if not rows:
        console.print("[dim]  No contributor data found.[/dim]")
        return
    console.print(render_contributor_table(rows))
    console.print(Text("  Top 10 contributors · last 30 days ·", style="dim cyan"))
    console.print(Text("  items authored (issues + PRs combined)", style="dim cyan"))
    show_command_footer(len(rows), elapsed, cached=last_was_cached())


def _detect_hn_query(owner: str, repo: str) -> str:
    """Auto-detect HN search term: env override > first repo topic > repo name."""
    if env_val := os.getenv("HN_QUERY"):
        return env_val
    try:
        import json as _json
        topics_sql = "SELECT names FROM github.repo_topics WHERE owner = '{owner}' AND repo = '{repo}'"
        result = run_query(topics_sql, owner=owner, repo=repo)
        rows = parse_table_output(result)
        if rows:
            topics = _json.loads(rows[0].get("names", "[]"))
            if topics:
                return topics[0]
    except Exception:
        pass
    return repo


def cmd_hn_buzz(owner: str, repo: str) -> None:
    hn_query = _detect_hn_query(owner, repo)
    os.environ["HN_QUERY"] = hn_query
    sql = _read_sql("hn_buzz.sql")
    show_command_header("hn-buzz", owner, repo, "github + hn (zero auth)")
    show_sql(substitute_tokens(sql, owner, repo), "github + hn (zero auth)")
    start = time.time()
    with show_thinking("Querying Coral · HN Buzz…"):
        result = run_query(sql, owner=owner, repo=repo)
    elapsed = time.time() - start
    if result.startswith("Error:"):
        show_error(result)
        return
    rows = parse_table_output(result)
    if not rows:
        console.print("[dim]  No HN posts found.[/dim]")
        show_command_footer(0, elapsed, cached=last_was_cached())
        return
    console.print(render_hn_table(rows))
    console.print(Text(f"  Searching HN for: '{os.getenv('HN_QUERY', repo)}' — override: export HN_QUERY=\"your topic\"", style="dim cyan"))
    show_command_footer(len(rows), elapsed, cached=last_was_cached())


def cmd_cve_scan(owner: str, repo: str) -> None:
    show_command_header("cve-scan", owner, repo, "github + osv (zero auth)")

    with show_thinking("Detecting package ecosystem…"):
        pkg, eco, ver = detect_package(owner, repo)

    auto_label = " · auto-detected" if pkg and not os.getenv("PACKAGE_NAME") else ""
    if pkg:
        ver_str = f" v{ver}" if ver else " (version unknown)"
        console.print(
            Panel(
                Text(f"⚠ SECURITY SCAN · {owner}/{repo} · {pkg}{ver_str} ({eco}){auto_label}", style="bold yellow"),
                border_style="red",
                padding=(0, 2),
            )
        )
        # Make detected values available to SQL token substitution
        os.environ["PACKAGE_NAME"] = pkg
        os.environ["PACKAGE_ECOSYSTEM"] = eco
        if ver:
            os.environ["PACKAGE_VERSION"] = ver
    else:
        console.print(
            Panel(
                Text(f"⚠ SECURITY SCAN · {owner}/{repo} · no package manifest detected", style="bold yellow"),
                border_style="yellow",
                padding=(0, 2),
            )
        )
    full_sql = _read_sql("cve_scan.sql")
    # Three sections: A = Dependabot, B = keyword issues, C = OSV
    parts = full_sql.split("-- ==QUERY_B==")
    sql_a = parts[0].strip()
    rest = parts[1] if len(parts) > 1 else ""
    parts_bc = rest.split("-- ==QUERY_C==")
    sql_b = parts_bc[0].strip() if parts_bc else ""
    sql_c = parts_bc[1].strip() if len(parts_bc) > 1 else ""

    total_rows = 0
    start = time.time()

    # — Section 1: Dependabot alerts (real confirmed CVEs) —
    show_sql(substitute_tokens(sql_a, owner, repo), "github (Dependabot alerts)")
    with show_thinking("Querying Coral · Dependabot Alerts…"):
        result_a = run_query(sql_a, owner=owner, repo=repo)
    if result_a.startswith("Error:"):
        console.print(Text(
            "  ℹ  Dependabot not enabled on this repo, or PAT missing 'security_events' scope.",
            style="dim",
        ))
    else:
        rows_a = parse_table_output(result_a)
        total_rows += len(rows_a)
        if rows_a:
            console.print(render_dependabot_table(rows_a))
        else:
            console.print("[dim]  No open Dependabot alerts.[/dim]")

    # — Section 2: Keyword security issues —
    if sql_b:
        show_sql(substitute_tokens(sql_b, owner, repo), "github (search_issues)")
        with show_thinking("Querying Coral · Security Issues…"):
            result_b = run_query(sql_b, owner=owner, repo=repo)
        if result_b.startswith("Error:"):
            show_error(result_b)
        else:
            rows_b = parse_table_output(result_b)
            total_rows += len(rows_b)
            if rows_b:
                console.print(render_issue_table(rows_b, "🔍 Security-Related Issues"))
                console.print(Text(
                    "  Keyword match — review titles; may include tangential results",
                    style="dim yellow",
                ))
            else:
                console.print("[dim]  No open security issues found.[/dim]")

    # — Section 3: OSV package CVEs —
    if sql_c and pkg and ver:
        show_sql(substitute_tokens(sql_c, owner, repo), "osv (query_by_version)")
        with show_thinking("Querying Coral · CVE Data…"):
            result_c = run_query(sql_c, owner=owner, repo=repo)
        if result_c.startswith("Error:"):
            show_error(result_c)
        else:
            rows_c = parse_table_output(result_c)
            total_rows += len(rows_c)
            if rows_c:
                console.print(render_cve_table(rows_c))
            else:
                console.print("[dim]  No known CVEs found for this package/version.[/dim]")
    elif sql_c and pkg and not ver:
        console.print(Text(
            f"  OSV lookup skipped — could not detect pinned version for '{pkg}'.\n"
            f"  Set PACKAGE_VERSION=x.y.z in .env to enable.",
            style="dim",
        ))
    elif sql_c and not pkg:
        console.print(Text(
            "  OSV lookup skipped — no package manifest found in this repo.\n"
            "  Set PACKAGE_NAME, PACKAGE_ECOSYSTEM, PACKAGE_VERSION in .env to enable.",
            style="dim",
        ))

    elapsed = time.time() - start
    show_command_footer(total_rows, elapsed, cached=last_was_cached())


def cmd_release_notes(owner: str, repo: str) -> None:
    sql = _read_sql("release_notes.sql")
    show_command_header("release-notes", owner, repo, "github")
    show_sql(substitute_tokens(sql, owner, repo), "github")
    start = time.time()
    with show_thinking("Querying Coral · Release Notes…"):
        result = run_query(sql, owner=owner, repo=repo)
    elapsed = time.time() - start
    if result.startswith("Error:"):
        show_error(result)
        return
    rows = parse_table_output(result)
    if not rows:
        console.print("[dim]  No merged PRs found in last 14 days.[/dim]")
        show_command_footer(0, elapsed, cached=last_was_cached())
        return
    console.print(render_issue_table(rows, "📝 Release Notes — Merged PRs (last 14 days)"))
    console.print(Text("  Paste this into Claude Code for formatted Markdown release notes", style="dim cyan"))
    show_command_footer(len(rows), elapsed, cached=last_was_cached())


_STOPWORDS = {
    # articles / conjunctions / prepositions
    'the', 'a', 'an', 'and', 'or', 'is', 'in', 'to', 'for', 'of', 'with',
    'on', 'at', 'by', 'from', 'as', 'be', 'this', 'that', 'are', 'was',
    'not', 'when', 'it', 'its', 'if', 'all', 'can', 'has', 'have', 'been',
    # conventional commit prefixes (base + past tense)
    'add', 'added', 'feat', 'fix', 'fixed', 'docs', 'chore', 'refactor',
    'test', 'style', 'perf', 'ci', 'build', 'new', 'update', 'updated',
    'create', 'make', 'made', 'use', 'used', 'using', 'avoid', 'avoided',
    'improve', 'improved', 'remove', 'removed', 'change', 'changed',
    'allow', 'allowed', 'ensure', 'ensured', 'handle', 'handled',
    # project-agnostic noise
    'source', 'sources', 'community', 'support', 'implement', 'implemented',
    'move', 'moved', 'rename', 'renamed', 'replace', 'replaced',
    'deprecate', 'deprecated', 'cleanup', 'set', 'get',
}


def _title_similarity(title_a: str, title_b: str) -> tuple[int, set[str]]:
    import re as _re
    def sig_words(t: str) -> set[str]:
        return {w for w in _re.split(r'[\W_]+', t.lower())
                if len(w) > 2 and w not in _STOPWORDS}
    w_a, w_b = sig_words(title_a), sig_words(title_b)
    shared = w_a & w_b
    return len(shared), shared


def cmd_duplicates(owner: str, repo: str) -> None:
    sql = _read_sql("duplicates.sql")
    show_command_header("duplicates", owner, repo, "github (CROSS JOIN)")
    show_sql(substitute_tokens(sql, owner, repo), "github (CROSS JOIN)")
    start = time.time()
    with show_thinking("Querying Coral · Duplicates…"):
        result = run_query(sql, owner=owner, repo=repo)
    elapsed = time.time() - start
    if result.startswith("Error:"):
        show_error(result)
        return
    rows = parse_table_output(result)
    similar: list[dict] = []
    for row in rows:
        count, shared = _title_similarity(
            str(row.get("title_a", "")), str(row.get("title_b", ""))
        )
        if count >= 2:
            row["shared_terms"] = ", ".join(sorted(shared)[:4])
            row["match_strength"] = count
            similar.append(row)
    if similar:
        console.print(render_duplicates_table(similar))
        console.print(Text(
            f"  {len(similar)} potential duplicate pair(s) from {len(rows)} pairs scanned"
            f" · threshold: 2+ shared keywords",
            style="dim cyan",
        ))
    else:
        console.print("[dim]  No duplicate candidates found — all recent issues appear distinct.[/dim]")
        console.print(Text(
            f"  Scanned {len(rows)} pairs · threshold: 2+ shared keywords",
            style="dim",
        ))
    show_command_footer(len(similar), elapsed, cached=last_was_cached())


def cmd_health(owner: str, repo: str) -> None:
    from ui.splash import calculate_health_score, _health_color
    from rich.progress import Progress, BarColumn, TextColumn, TaskProgressColumn
    show_command_header("health", owner, repo, "github (4 signals · concurrent)")
    start = time.time()
    with show_thinking("Calculating repo health score…"):
        score, summary = calculate_health_score(owner, repo)
    elapsed = time.time() - start
    color = _health_color(score)
    with Progress(
        TextColumn("  [bold]Repo Health Score[/bold]"),
        BarColumn(bar_width=40, style=color, complete_style=color),
        TaskProgressColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("", total=100)
        progress.update(task, completed=score)
    console.print(f"  [{color}]{summary}[/{color}]")
    show_command_footer(4, elapsed, unit="signals", cached=last_was_cached())


def cmd_pulse(owner: str, repo: str) -> None:
    hn_query = _detect_hn_query(owner, repo)
    os.environ["HN_QUERY"] = hn_query
    sql = _read_sql("pulse.sql")
    show_command_header("pulse", owner, repo, "github + hn (cross-source SQL JOIN)")
    show_sql(substitute_tokens(sql, owner, repo), "github + hn (cross-source SQL JOIN)")
    start = time.time()
    with show_thinking("Querying Coral · Community Pulse…"):
        result = run_query(sql, owner=owner, repo=repo)
    elapsed = time.time() - start
    if result.startswith("Error:"):
        show_error(result)
        return
    rows = parse_table_output(result)
    if not rows:
        console.print("[dim]  No pulse data found — try setting HN_QUERY in .env[/dim]")
        show_command_footer(0, elapsed, cached=last_was_cached())
        return

    # CROSS JOIN produces N×M rows — deduplicate into parallel lists then zip.
    # Preserves order: HN rows ordered by score DESC, GitHub rows by comments DESC.
    hn_seen: list[dict] = []
    hn_set: set[str] = set()
    gh_seen: list[dict] = []
    gh_set: set[str] = set()
    for row in rows:
        hn_key = str(row.get("hn_post", ""))
        gh_key = str(row.get("github_issue", ""))
        if hn_key and hn_key not in hn_set:
            hn_seen.append(row)
            hn_set.add(hn_key)
        if gh_key and gh_key not in gh_set:
            gh_seen.append({
                "github_issue": row.get("github_issue"),
                "github_issue_title": row.get("github_issue_title"),
                "github_author": row.get("github_author"),
            })
            gh_set.add(gh_key)

    display_rows = []
    for i in range(max(len(hn_seen), len(gh_seen))):
        hn = hn_seen[i] if i < len(hn_seen) else {}
        gh = gh_seen[i] if i < len(gh_seen) else {}
        display_rows.append({
            "hn_score": hn.get("hn_score", ""),
            "hn_post": hn.get("hn_post", ""),
            "github_issue": gh.get("github_issue", ""),
            "github_issue_title": gh.get("github_issue_title", ""),
            "github_author": gh.get("github_author", ""),
        })

    console.print(render_pulse_table(display_rows))
    console.print(Text(
        f"  Top HN '{hn_query}' posts alongside top open issues — cross-source SQL JOIN",
        style="dim cyan",
    ))
    show_command_footer(len(display_rows), elapsed, cached=last_was_cached())


def cmd_so_buzz(owner: str, repo: str) -> None:
    hn_query = _detect_hn_query(owner, repo)
    os.environ["HN_QUERY"] = hn_query
    sql = _read_sql("so_buzz.sql")
    show_command_header("so-buzz", owner, repo, "stackoverflow (zero auth)")
    show_sql(substitute_tokens(sql, owner, repo), "stackoverflow (zero auth)")
    start = time.time()
    with show_thinking("Querying Coral · Stack Overflow…"):
        result = run_query(sql, owner=owner, repo=repo)
    elapsed = time.time() - start
    if result.startswith("Error:"):
        if "not found" in result or "not currently registered" in result:
            console.print(Panel(
                Text(
                    "  Stack Overflow source not installed.\n"
                    "  Run: coral source add --file sources/stackoverflow/manifest.yaml",
                    style="yellow",
                ),
                border_style="yellow",
                padding=(0, 2),
            ))
        else:
            show_error(result)
        return
    rows = parse_table_output(result)
    if not rows:
        console.print(f"[dim]  No Stack Overflow questions found for '{hn_query}'.[/dim]")
        show_command_footer(0, elapsed, cached=last_was_cached())
        return
    console.print(render_so_table(rows))
    console.print(Text(f"  Top SO questions tagged '{hn_query}'", style="dim cyan"))
    show_command_footer(len(rows), elapsed, cached=last_was_cached())


def cmd_dev_buzz(owner: str, repo: str) -> None:
    hn_query = _detect_hn_query(owner, repo)
    os.environ["HN_QUERY"] = hn_query
    sql = _read_sql("dev_buzz.sql")
    show_command_header("dev-buzz", owner, repo, "devto (zero auth)")
    show_sql(substitute_tokens(sql, owner, repo), "devto (zero auth)")
    start = time.time()
    with show_thinking("Querying Coral · Dev.to…"):
        result = run_query(sql, owner=owner, repo=repo)
    elapsed = time.time() - start
    if result.startswith("Error:"):
        if "not found" in result or "not currently registered" in result:
            console.print(Panel(
                Text(
                    "  Dev.to source not installed.\n"
                    "  Run: coral source add --file sources/devto/manifest.yaml",
                    style="yellow",
                ),
                border_style="yellow",
                padding=(0, 2),
            ))
        else:
            show_error(result)
        return
    rows = parse_table_output(result)
    if not rows:
        console.print(f"[dim]  No Dev.to articles found for '{hn_query}'.[/dim]")
        show_command_footer(0, elapsed, cached=last_was_cached())
        return
    console.print(render_dev_table(rows))
    console.print(Text(f"  Trending Dev.to articles tagged '{hn_query}'", style="dim cyan"))
    show_command_footer(len(rows), elapsed, cached=last_was_cached())


def cmd_scorecard(owner: str, repo: str) -> None:
    sql = _read_sql("scorecard.sql")
    show_command_header("scorecard", owner, repo, "OpenSSF Scorecard (zero auth)")
    show_sql(substitute_tokens(sql, owner, repo), "OpenSSF Scorecard")
    start = time.time()
    with show_thinking("Querying OpenSSF Scorecard…"):
        result = run_query(sql, owner=owner, repo=repo)
    elapsed = time.time() - start
    if result.startswith("Error:"):
        if "not currently registered" in result:
            console.print(Panel(
                Text(
                    "  Scorecard source not installed.\n"
                    "  Run: coral source add --file sources/scorecard/manifest.yaml",
                    style="yellow",
                ),
                border_style="yellow",
                padding=(0, 2),
            ))
        elif "404" in result or "Source resource was not found" in result:
            console.print(Panel(
                Text(
                    f"  No OpenSSF Scorecard data found for {owner}/{repo}.\n"
                    "  Scorecard covers public GitHub repos with CI/CD history.\n"
                    "  Check manually: https://scorecard.dev",
                    style="yellow",
                ),
                border_style="yellow",
                padding=(0, 2),
            ))
        else:
            show_error(result)
        return
    rows = parse_table_output(result)
    if not rows:
        console.print(f"[dim]  No scorecard data found for {owner}/{repo}.[/dim]")
        show_command_footer(0, elapsed, cached=last_was_cached())
        return
    console.print(render_scorecard_table(rows, owner, repo))
    passing = sum(1 for r in rows if r.get("score") not in (None, "", "-1", "None") and int(r.get("score", -2)) >= 8)
    na_count = sum(1 for r in rows if str(r.get("score", "")).strip() in ("-1",))
    scored = len(rows) - na_count
    console.print(Text(
        f"  {passing}/{scored} checks passing (≥8) · {na_count} N/A · powered by OpenSSF Scorecard",
        style="dim cyan",
    ))
    show_command_footer(len(rows), elapsed, cached=last_was_cached())


_COMMAND_MAP = {
    "triage": cmd_triage,
    "stale-prs": cmd_stale_prs,
    "contributors": cmd_contributors,
    "hn-buzz": cmd_hn_buzz,
    "cve-scan": cmd_cve_scan,
    "release-notes": cmd_release_notes,
    "duplicates": cmd_duplicates,
    "health": cmd_health,
    "pulse": cmd_pulse,
    "so-buzz": cmd_so_buzz,
    "dev-buzz": cmd_dev_buzz,
    "scorecard": cmd_scorecard,
}


# ── click CLI ─────────────────────────────────────────────────────────────────

@click.group(invoke_without_command=True)
@click.option("--repo", default=None, help="GitHub repo to analyse (format: owner/repo)")
@click.option("--mcp", is_flag=True, default=False, help="Start RepoSense as an MCP server (stdio transport).")
@click.pass_context
def cli(ctx: click.Context, repo: str | None, mcp: bool) -> None:
    """RepoSense — AI-powered GitHub repo intelligence via Coral."""
    ctx.ensure_object(dict)

    if mcp:
        from agent.mcp_server import run_mcp_server
        run_mcp_server()
        return

    if ctx.invoked_subcommand is None and repo is None:
        # Interactive mode with no --repo flag: show logo then prompt for repo
        show_splash_logo()
        owner, repo_name = _prompt_repo()
    else:
        owner, repo_name = _resolve_repo(repo)

    ctx.obj["owner"] = owner
    ctx.obj["repo"] = repo_name

    if ctx.invoked_subcommand is None:
        show_splash(owner, repo_name)
        _show_help()
        while True:
            try:
                question = console.input("\n[bold cyan]>[/bold cyan] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Goodbye! ⚓[/dim]")
                break
            if not question:
                continue
            if question.lower() in ("quit", "exit", "q"):
                console.print("[dim]Goodbye! ⚓[/dim]")
                break
            cmd = _match_command(question)
            if cmd:
                _COMMAND_MAP[cmd](owner, repo_name)
            else:
                # Free-form question — hand off to Claude agent with Coral tool use
                run_agent(question, owner, repo_name)


@cli.command()
@click.pass_context
def triage(ctx: click.Context) -> None:
    """Open issues with no linked PR, sorted by engagement."""
    owner, repo = ctx.obj["owner"], ctx.obj["repo"]
    cmd_triage(owner, repo)


@cli.command("stale-prs")
@click.pass_context
def stale_prs(ctx: click.Context) -> None:
    """PRs open longer than 7 days."""
    owner, repo = ctx.obj["owner"], ctx.obj["repo"]
    cmd_stale_prs(owner, repo)


@cli.command()
@click.pass_context
def contributors(ctx: click.Context) -> None:
    """Contributor activity rollup for the last 30 days."""
    owner, repo = ctx.obj["owner"], ctx.obj["repo"]
    cmd_contributors(owner, repo)


@cli.command("hn-buzz")
@click.pass_context
def hn_buzz(ctx: click.Context) -> None:
    """Hacker News posts related to this project."""
    owner, repo = ctx.obj["owner"], ctx.obj["repo"]
    cmd_hn_buzz(owner, repo)


@cli.command("cve-scan")
@click.pass_context
def cve_scan(ctx: click.Context) -> None:
    """Known CVEs for project dependencies via OSV."""
    owner, repo = ctx.obj["owner"], ctx.obj["repo"]
    cmd_cve_scan(owner, repo)


@cli.command("release-notes")
@click.pass_context
def release_notes(ctx: click.Context) -> None:
    """Merged PRs in the last 14 days for release notes."""
    owner, repo = ctx.obj["owner"], ctx.obj["repo"]
    cmd_release_notes(owner, repo)


@cli.command()
@click.pass_context
def duplicates(ctx: click.Context) -> None:
    """Similar open issues detected via CROSS JOIN."""
    owner, repo = ctx.obj["owner"], ctx.obj["repo"]
    cmd_duplicates(owner, repo)


@cli.command()
@click.pass_context
def health(ctx: click.Context) -> None:
    """Repo health score — 4 live signals via github.search_issues()."""
    owner, repo = ctx.obj["owner"], ctx.obj["repo"]
    cmd_health(owner, repo)


@cli.command()
@click.pass_context
def pulse(ctx: click.Context) -> None:
    """HN trending posts × top open GitHub issues — cross-source SQL JOIN."""
    owner, repo = ctx.obj["owner"], ctx.obj["repo"]
    cmd_pulse(owner, repo)


@cli.command("so-buzz")
@click.pass_context
def so_buzz(ctx: click.Context) -> None:
    """Top Stack Overflow questions for this project's technology."""
    owner, repo = ctx.obj["owner"], ctx.obj["repo"]
    cmd_so_buzz(owner, repo)


@cli.command("dev-buzz")
@click.pass_context
def dev_buzz(ctx: click.Context) -> None:
    """Trending Dev.to articles for this project's technology."""
    owner, repo = ctx.obj["owner"], ctx.obj["repo"]
    cmd_dev_buzz(owner, repo)


@cli.command()
@click.pass_context
def scorecard(ctx: click.Context) -> None:
    """OpenSSF security posture — 18 checks, zero config, any public GitHub repo."""
    owner, repo = ctx.obj["owner"], ctx.obj["repo"]
    cmd_scorecard(owner, repo)


@cli.command()
@click.argument("question", nargs=-1, required=True)
@click.pass_context
def ask(ctx: click.Context, question: tuple) -> None:
    """Ask anything in plain English — agent writes and runs the SQL."""
    owner, repo = ctx.obj["owner"], ctx.obj["repo"]
    run_agent(" ".join(question), owner, repo)


if __name__ == "__main__":
    cli()
