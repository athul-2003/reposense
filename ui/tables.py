import html
import json
import re
from datetime import date, datetime

from rich.table import Table
from rich.text import Text


def _truncate(value: str, max_len: int) -> str:
    s = str(value)
    return s if len(s) <= max_len else s[: max_len - 1] + "…"


def _days_ago(date_str: str) -> int:
    try:
        opened = datetime.strptime(str(date_str)[:10], "%Y-%m-%d").date()
        return (date.today() - opened).days
    except Exception:
        return 0


def render_issue_table(rows: list[dict], title: str = "🔍 Open Items — Triage Report") -> Table:
    # Column widths sum to 80: 1+8+1+45+1+15+1+7+1 = 80 (border+pad included)
    table = Table(title=title, show_lines=False)
    table.add_column("#", style="bold", width=6, no_wrap=True)
    table.add_column("Title", max_width=43, no_wrap=True)
    table.add_column("Author", width=13, no_wrap=True)
    table.add_column("Type", width=5, no_wrap=True)

    for row in rows:
        url = str(row.get("html_url", ""))
        # user_login may be aliased as author in the SQL
        author = row.get("user_login") or row.get("author", "")
        if "/issues/" in url:
            item_type = "issue"
            style = "green"
        elif "/pull/" in url:
            item_type = "PR"
            style = "yellow"
        else:
            item_type = "?"
            style = ""

        table.add_row(
            str(row.get("number", "")),
            _truncate(row.get("title", ""), 43),
            _truncate(author, 13),
            item_type,
            style=style,
        )

    return table


def render_pr_table(rows: list[dict]) -> Table:
    table = Table(title="⏰ Stale Pull Requests (>7 days)", show_lines=False)
    table.add_column("#", style="bold", width=6)
    table.add_column("Title", max_width=55, no_wrap=True)
    table.add_column("Author", width=18)
    table.add_column("Opened On", width=12)
    table.add_column("Target Branch", width=20)

    for row in rows:
        table.add_row(
            str(row.get("number", "")),
            _truncate(row.get("title", ""), 55),
            str(row.get("author", "")),
            str(row.get("opened_on", ""))[:10],
            str(row.get("target_branch", "")),
            style="yellow",
        )

    return table


def render_stale_prs_table(rows: list[dict]) -> Table:
    table = Table(title="⏰ Stale Pull Requests — open >7 days, non-draft", show_lines=False)
    table.add_column("#", style="bold", width=5, no_wrap=True)
    table.add_column("Title", width=44, no_wrap=True)
    table.add_column("Author", width=14, no_wrap=True)
    table.add_column("Age", width=4, no_wrap=True)

    for row in rows:
        table.add_row(
            str(row.get("number", "")),
            _truncate(str(row.get("title", "")), 44),
            _truncate(str(row.get("author", "")), 14),
            ">7d",
            style="yellow",
        )

    return table


def render_contributor_table(rows: list[dict]) -> Table:
    # Widths: 4+20+8 = 32 content + 6 pad + 4 borders = 42 chars total
    table = Table(title="👥 Contributor Activity — Last 30 Days", show_lines=False)
    table.add_column("Rank", justify="right", width=4)
    table.add_column("Author", width=20, no_wrap=True)
    table.add_column("Items", justify="right", width=8)

    for i, row in enumerate(rows, start=1):
        style = "bold green" if i == 1 else ""
        table.add_row(
            str(i),
            _truncate(str(row.get("actor", "")), 20),
            str(row.get("total", 0)),
            style=style,
        )

    return table


def render_duplicates_table(rows: list[dict]) -> Table:
    table = Table(title="🔁 Potential Duplicate Issues", show_lines=True)
    table.add_column("#A", style="bold", width=5, no_wrap=True)
    table.add_column("Issue A", width=22, no_wrap=True)
    table.add_column("#B", style="bold", width=5, no_wrap=True)
    table.add_column("Issue B", width=22, no_wrap=True)
    table.add_column("Matched Keywords", width=20, no_wrap=True)

    for row in rows:
        strength = int(row.get("match_strength", 0))
        if strength >= 4:
            row_style = "bold yellow"
        elif strength >= 3:
            row_style = "yellow"
        else:
            row_style = "dim yellow"
        table.add_row(
            str(row.get("issue_a", "")),
            _truncate(str(row.get("title_a", "")), 22),
            str(row.get("issue_b", "")),
            _truncate(str(row.get("title_b", "")), 22),
            _truncate(str(row.get("shared_terms", "")), 20),
            style=row_style,
        )

    return table


def _parse_cvss_severity(severity_raw: str) -> tuple[str, str]:
    """Extract HIGH/MEDIUM/LOW label from raw CVSS JSON severity field."""
    try:
        entries = json.loads(severity_raw)
        for entry in entries:
            score = entry.get("score", "")
            c = re.search(r"/C:([HML])", score)
            i = re.search(r"/I:([HML])", score)
            a = re.search(r"/A:([HML])", score)
            impacts = [x.group(1) for x in [c, i, a] if x]
            if "H" in impacts:
                return "HIGH", "bold red"
            elif "M" in impacts:
                return "MEDIUM", "yellow"
            else:
                return "LOW", "green"
    except Exception:
        pass
    return "?", "dim"


def render_cve_table(rows: list[dict]) -> Table:
    table = Table(title="🔐 CVE Vulnerabilities", show_lines=True)
    table.add_column("CVE ID", width=20, no_wrap=True)
    table.add_column("Summary", max_width=25, no_wrap=True)
    table.add_column("Severity", width=10, justify="center", no_wrap=True)
    table.add_column("Published", width=12, no_wrap=True)

    for row in rows:
        label, style = _parse_cvss_severity(str(row.get("severity", "")))
        table.add_row(
            _truncate(str(row.get("cve_id", "")), 22),
            _truncate(str(row.get("vulnerability_summary", "")), 38),
            Text(label, style=style),
            str(row.get("cve_published", ""))[:10],
        )

    return table


def render_dependabot_table(rows: list[dict]) -> Table:
    """Render Dependabot alerts — real confirmed CVEs in repo dependencies."""
    table = Table(title="🤖 Dependabot Alerts — Confirmed CVEs", show_lines=True)
    table.add_column("Package", width=18, no_wrap=True)
    table.add_column("Ecosystem", width=10, no_wrap=True)
    table.add_column("Summary", max_width=27, no_wrap=True)
    table.add_column("Severity", width=10, justify="center", no_wrap=True)
    table.add_column("CVE / GHSA", width=22, no_wrap=True)

    _SEV_STYLE = {
        "critical": ("CRITICAL", "bold red"),
        "high":     ("HIGH",     "red"),
        "medium":   ("MEDIUM",   "yellow"),
        "low":      ("LOW",      "green"),
    }

    for row in rows:
        sev_raw = str(row.get("severity", "")).lower()
        label, style = _SEV_STYLE.get(sev_raw, (sev_raw.upper() or "?", "dim"))
        cve_id = str(row.get("cve_id", "")).strip()
        ghsa_id = str(row.get("ghsa_id", "")).strip()
        identifier = cve_id if cve_id and cve_id != "None" else ghsa_id
        table.add_row(
            _truncate(str(row.get("package", "")), 18),
            _truncate(str(row.get("ecosystem", "")), 10),
            _truncate(str(row.get("summary", "")), 27),
            Text(label, style=style),
            _truncate(identifier, 22),
        )

    return table


def render_pulse_table(rows: list[dict]) -> Table:
    # Target 80-char terminal: fixed 6+6+11=23 + overhead ~16 + 2×max_width=2×20=40 → 79
    table = Table(title="📡 Pulse — GitHub × HN (Cross-Source SQL JOIN)", show_lines=True)
    table.add_column("Score", justify="right", width=6, no_wrap=True)
    table.add_column("HN Trending Post", max_width=20, no_wrap=True)
    table.add_column("Issue", style="bold", width=6, no_wrap=True)
    table.add_column("Top Open GitHub Issue", max_width=20, no_wrap=True)
    table.add_column("Author", width=11, no_wrap=True)

    for row in rows:
        score = int(row.get("hn_score") or 0)
        if score > 500:
            style = "bold yellow"
        elif score > 100:
            style = "yellow"
        else:
            style = "dim yellow"
        table.add_row(
            str(score),
            _truncate(str(row.get("hn_post", "")), 20),
            str(row.get("github_issue", "")),
            _truncate(str(row.get("github_issue_title", "")), 20),
            _truncate(str(row.get("github_author", "")), 11),
            style=style,
        )

    return table


def render_so_table(rows: list[dict]) -> Table:
    # Target 80-char: fixed 6+7+7+2+10=32 + overhead 17 + max_width 31 = 80
    table = Table(title="📚 Stack Overflow — Top Questions", show_lines=False)
    table.add_column("Title", max_width=31, no_wrap=True)
    table.add_column("Score", justify="right", width=6, no_wrap=True)
    table.add_column("Answers", justify="right", width=7, no_wrap=True)
    table.add_column("Views", justify="right", width=7, no_wrap=True)
    table.add_column("✓", width=2, justify="center", no_wrap=True)
    table.add_column("Asked", width=10, no_wrap=True)

    for row in rows:
        score = int(row.get("score") or 0)
        is_answered = str(row.get("is_answered", "")).lower() in ("true", "1", "yes")
        title = html.unescape(str(row.get("title", "")))
        if score > 500:
            style = "bold green"
        elif score > 100:
            style = "green"
        elif score > 20:
            style = "yellow"
        else:
            style = ""
        table.add_row(
            _truncate(title, 31),
            str(score),
            str(row.get("answer_count") or 0),
            str(row.get("view_count") or 0),
            "✓" if is_answered else "·",
            str(row.get("posted_date", ""))[:10],
            style=style,
        )

    return table


def render_dev_table(rows: list[dict]) -> Table:
    # Target 80-char: fixed 7+7+12+10=36 + overhead 16 + max_width 28 = 80
    table = Table(title="💻 Dev.to — Trending Articles", show_lines=False)
    table.add_column("Title", max_width=28, no_wrap=True)
    table.add_column("♥", justify="right", width=7, no_wrap=True)
    table.add_column("💬", justify="right", width=7, no_wrap=True)
    table.add_column("Author", width=12, no_wrap=True)
    table.add_column("Published", width=10, no_wrap=True)

    for row in rows:
        reactions = int(row.get("reactions") or 0)
        if reactions > 100:
            style = "bold green"
        elif reactions >= 20:
            style = "yellow"
        else:
            style = ""
        table.add_row(
            _truncate(str(row.get("title", "")), 28),
            str(reactions),
            str(row.get("comments_count") or 0),
            _truncate(str(row.get("author", "")), 12),
            str(row.get("published_date", ""))[:10],
            style=style,
        )

    return table


def render_hn_table(rows: list[dict]) -> Table:
    # 5-col fixed widths summing to 64: 64 + 3*5 + 1 = 80
    table = Table(title="🔥 Hacker News Buzz", show_lines=False)
    table.add_column("Title", width=28, no_wrap=True)
    table.add_column("Upvotes", justify="right", width=7, no_wrap=True)
    table.add_column("Comments", justify="right", width=8, no_wrap=True)
    table.add_column("Author", width=11, no_wrap=True)
    table.add_column("Date", width=10, no_wrap=True)

    for row in rows:
        upvotes = int(row.get("hn_upvotes") or 0)

        if upvotes > 100:
            style = "bold green"
        elif upvotes >= 50:
            style = "yellow"
        else:
            style = ""

        table.add_row(
            _truncate(str(row.get("hn_post_title", "")), 28),
            str(upvotes),
            str(row.get("hn_comments") or 0),
            _truncate(str(row.get("author", "")), 11),
            str(row.get("posted_date", ""))[:10],
            style=style,
        )

    return table


def render_scorecard_table(rows: list[dict], owner: str = "", repo: str = "") -> Table:
    title = f"🔐 OpenSSF Scorecard{f' — {owner}/{repo}' if owner and repo else ''}"
    table = Table(title=title, show_lines=False)
    table.add_column("Check", width=22, no_wrap=True)
    table.add_column("Score", justify="right", width=5, no_wrap=True)
    table.add_column("Reason", width=43, no_wrap=True)

    for row in rows:
        raw_score = row.get("score")
        try:
            score_val = int(raw_score) if raw_score not in (None, "", "None") else None
        except (ValueError, TypeError):
            score_val = None

        if score_val is None:
            score_str = "—"
            style = "dim"
        elif score_val == -1:
            score_str = "N/A"
            style = "dim"
        elif score_val >= 8:
            score_str = f"{score_val}/10"
            style = "green"
        elif score_val >= 5:
            score_str = f"{score_val}/10"
            style = "yellow"
        else:
            score_str = f"{score_val}/10"
            style = "bold red"

        table.add_row(
            str(row.get("check_name", "")),
            score_str,
            _truncate(str(row.get("reason") or ""), 50),
            style=style,
        )

    return table
