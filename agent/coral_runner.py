import json
import os
import re
import subprocess
import urllib.request
from datetime import datetime, timedelta, timezone

_SLUG_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}$')
_QUERY_TIMEOUT = 90  # seconds — Coral's own timeout is ~30s; we allow 3× for slow networks


def validate_repo_slug(value: str, label: str = "value") -> str:
    """Raise ValueError if value is not a safe GitHub owner/repo slug."""
    if not _SLUG_RE.match(value):
        raise ValueError(
            f"Invalid {label} '{value}': only letters, digits, hyphens, dots, "
            "underscores allowed; must start with a letter or digit."
        )
    return value


# Manifest files tried in priority order — first match wins.
_MANIFEST_ATTEMPTS = [
    ("requirements.txt", "PyPI"),
    ("pyproject.toml",   "PyPI"),
    ("package.json",     "npm"),
    ("go.mod",           "Go"),
    ("Cargo.toml",       "crates.io"),
    ("Gemfile",          "RubyGems"),
]


def _parse_manifest(filename: str, content: str) -> tuple[str, str] | None:
    """Extract (package_name, version) from a manifest file. Version may be empty."""
    if filename == "requirements.txt":
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-", "git+", "http")):
                continue
            m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._\-]*)", line)
            if m:
                name = m.group(1)
                ver = re.search(r"==([^\s,;]+)", line)
                return (name, ver.group(1) if ver else "")

    elif filename == "pyproject.toml":
        # [project] dependencies = ["pkg>=x.y"] or [tool.poetry.dependencies] pkg = "x"
        in_deps = False
        for line in content.splitlines():
            stripped = line.strip()
            if re.match(r"^\[.*(dependencies|requires).*\]", stripped, re.I):
                in_deps = True
                continue
            if stripped.startswith("[") and in_deps:
                break
            if in_deps:
                # list form: "django>=4.2.0" or "django"
                m = re.match(r'^"?([A-Za-z][A-Za-z0-9_\-\.]+)', stripped.lstrip("-").strip())
                if m:
                    name = m.group(1)
                    if name.lower() not in ("python", "pip", "setuptools", "wheel"):
                        ver = re.search(r"[=~>^]+([0-9][0-9a-zA-Z.\-]*)", stripped)
                        return (name, ver.group(1) if ver else "")
                # key = "version" form (poetry)
                m2 = re.match(r'^([a-zA-Z][a-zA-Z0-9_\-\.]+)\s*=\s*"', stripped)
                if m2:
                    name = m2.group(1)
                    if name.lower() not in ("python", "pip", "setuptools", "wheel"):
                        ver = re.search(r'"([0-9][^"]*)"', stripped)
                        ver_clean = re.sub(r"^[^0-9]*", "", ver.group(1)) if ver else ""
                        return (name, ver_clean)

    elif filename == "package.json":
        try:
            data = json.loads(content)
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            # prefer non-dev
            deps = data.get("dependencies") or deps
            if deps:
                name = next(iter(deps))
                ver = re.sub(r"^[^0-9]*", "", str(deps[name]))
                return (name, ver)
        except Exception:
            pass

    elif filename == "go.mod":
        in_require = False
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("require ("):
                in_require = True
                continue
            if in_require:
                if line == ")":
                    break
                m = re.match(r"^(\S+)\s+v([^\s]+)", line)
                if m and not m.group(1).startswith("//"):
                    name = m.group(1).split("/")[-1]
                    return (name, m.group(2))
            elif line.startswith("require "):
                m = re.match(r"^require\s+(\S+)\s+v([^\s]+)", line)
                if m:
                    return (m.group(1).split("/")[-1], m.group(2))

    elif filename == "Cargo.toml":
        in_deps = False
        for line in content.splitlines():
            stripped = line.strip()
            # Handle both [dependencies] and [workspace.dependencies]
            if stripped in ("[dependencies]", "[workspace.dependencies]"):
                in_deps = True
                continue
            if stripped.startswith("[") and in_deps:
                break
            if in_deps and "=" in stripped and not stripped.startswith("#"):
                m = re.match(r"^([a-zA-Z][a-zA-Z0-9_\-]+)\s*=", stripped)
                if m:
                    name = m.group(1)
                    # skip test-only crates
                    if name in ("assert_cmd", "mockall", "tempfile", "criterion", "proptest"):
                        continue
                    ver = re.search(r'"([0-9][^"]*)"', stripped)
                    return (name, ver.group(1) if ver else "")

    elif filename == "Gemfile":
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("gem "):
                m = re.search(r"""gem\s+['"]([^'"]+)['"](?:,\s*['"]([^'"]*)['"])?""", stripped)
                if m:
                    ver_raw = m.group(2) or ""
                    ver = re.sub(r"^[^0-9]*", "", ver_raw)
                    return (m.group(1), ver)

    return None


def detect_package(owner: str, repo: str) -> tuple[str, str, str]:
    """Return (name, ecosystem, version) for OSV scan.

    Priority: PACKAGE_NAME env var > repo manifest files > empty string.
    Fetches manifest files from raw.githubusercontent.com (public repos, no auth needed).
    """
    if os.getenv("PACKAGE_NAME"):
        return (
            os.getenv("PACKAGE_NAME", ""),
            os.getenv("PACKAGE_ECOSYSTEM", "PyPI"),
            os.getenv("PACKAGE_VERSION", ""),
        )

    for filename, ecosystem in _MANIFEST_ATTEMPTS:
        for branch in ("main", "master"):
            url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filename}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "RepoSense/1.0"})
                with urllib.request.urlopen(req, timeout=4) as resp:
                    if resp.status != 200:
                        continue
                    content = resp.read().decode("utf-8", errors="ignore")
                result = _parse_manifest(filename, content)
                if result:
                    name, version = result
                    if name:
                        return (name, ecosystem, version)
            except Exception:
                continue

    return ("", "", "")


def _token_map(owner: str, repo: str) -> dict[str, str]:
    """Build the substitution map for all SQL tokens."""
    now = datetime.now(timezone.utc)
    return {
        "{owner}":        owner,
        "{repo}":         repo,
        "{30_days_ago}":  (now - timedelta(days=30)).strftime('%Y-%m-%d'),
        "{14_days_ago}":  (now - timedelta(days=14)).strftime('%Y-%m-%d'),
        "{7_days_ago}":   (now - timedelta(days=7)).strftime('%Y-%m-%d'),
        "{hn_query}":     os.getenv("HN_QUERY", repo),
        "{package_name}": os.getenv("PACKAGE_NAME", "requests"),
        "{package_ecosystem}": os.getenv("PACKAGE_ECOSYSTEM", "PyPI"),
        "{package_version}":   os.getenv("PACKAGE_VERSION", "2.25.0"),
    }


def substitute_tokens(sql: str, owner: str, repo: str) -> str:
    """Apply all runtime token substitutions to a SQL string."""
    for token, value in _token_map(owner, repo).items():
        sql = sql.replace(token, value)
    return sql


import hashlib as _hashlib
import json as _json
import time as _time_mod
from pathlib import Path as _Path

# ── Persistent query cache ────────────────────────────────────────────────────
# Results are cached to disk (5-minute TTL) so repeated commands across
# separate invocations return instantly. Matches Coral's own HTTP cache window.
_CACHE_TTL = 300  # seconds
_CACHE_DIR = _Path.home() / ".cache" / "reposense"
_CACHE_FILE = _CACHE_DIR / "query_cache.json"

# Runtime dict: {md5_key: [result_str, unix_timestamp]}
_query_cache: dict[str, list] = {}

# Set by run_query; read by last_was_cached() for footer display.
_last_call_cached: bool = False


def _load_cache() -> None:
    """Load persisted cache from disk on startup."""
    try:
        if _CACHE_FILE.exists():
            data = _json.loads(_CACHE_FILE.read_text())
            now = _time_mod.time()
            # Drop expired entries on load
            _query_cache.update({
                k: v for k, v in data.items()
                if now - v[1] < _CACHE_TTL
            })
    except Exception:
        pass  # corrupt or missing cache — start fresh


def _save_cache() -> None:
    """Persist current cache to disk (only successful, non-expired entries)."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        now = _time_mod.time()
        to_save = {k: v for k, v in _query_cache.items() if now - v[1] < _CACHE_TTL}
        _CACHE_FILE.write_text(_json.dumps(to_save))
    except Exception:
        pass  # cache write failure is non-fatal


_load_cache()  # warm from disk on import


def last_was_cached() -> bool:
    """Return True if the most recent run_query() call was served from cache."""
    return _last_call_cached


def clear_query_cache() -> None:
    """Flush the in-memory and on-disk query cache."""
    _query_cache.clear()
    try:
        _CACHE_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def run_query(sql: str, owner: str = "withcoral", repo: str = "coral") -> str:
    """Run a SQL query via coral sql and return the output as a string.

    Results are cached to disk for 5 minutes (matching Coral's own HTTP cache
    TTL). Repeated identical queries — across invocations — return instantly.
    Only successful (non-error) results are cached.
    """
    global _last_call_cached
    sql = substitute_tokens(sql, owner, repo)
    key = _hashlib.md5(sql.encode()).hexdigest()
    now = _time_mod.time()

    if key in _query_cache:
        cached_result, ts = _query_cache[key]
        if now - ts < _CACHE_TTL:
            _last_call_cached = True
            return cached_result

    _last_call_cached = False
    try:
        result = subprocess.run(
            ["coral", "sql", "--", sql],
            capture_output=True,
            text=True,
            timeout=_QUERY_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return f"Error: Query timed out after {_QUERY_TIMEOUT}s — try a more specific query."
    if result.returncode != 0:
        return f"Error: {result.stderr.strip()}"
    output = result.stdout.strip()
    _query_cache[key] = [output, now]  # only cache successful results
    _save_cache()
    return output


_EXCLUDED_SCHEMAS = frozenset({"information_schema", "datafusion", "coral"})

_schema_cache: str | None = None


def get_installed_sources() -> str:
    """Return a compact summary of installed Coral sources and tables.

    Result is cached for the process lifetime — sources don't change mid-session.
    """
    global _schema_cache
    if _schema_cache is not None:
        return _schema_cache

    sql = (
        "SELECT table_schema, table_name "
        "FROM information_schema.tables "
        "ORDER BY table_schema, table_name"
    )
    raw = run_query(sql)
    rows = parse_table_output(raw)

    by_source: dict[str, list[str]] = {}
    for row in rows:
        schema = row.get("table_schema", "")
        table = row.get("table_name", "")
        if schema in _EXCLUDED_SCHEMAS or not schema:
            continue
        by_source.setdefault(schema, []).append(table)

    if not by_source:
        _schema_cache = "No sources installed."
        return _schema_cache

    _VERBOSE_SOURCES = {"github"}  # too many tables to list inline
    lines = ["Installed Coral sources (live schema):"]
    for source, tables in sorted(by_source.items()):
        if source in _VERBOSE_SOURCES:
            lines.append(f"  {source}: {len(tables)} tables (use coral_schema for details)")
        else:
            lines.append(f"  {source}: {', '.join(tables)}")
    _schema_cache = "\n".join(lines)
    return _schema_cache


def get_table_columns(schema: str, table: str) -> str:
    """Return column names and types for a specific table."""
    sql = (
        f"SELECT column_name, data_type "
        f"FROM information_schema.columns "
        f"WHERE table_schema = '{schema}' AND table_name = '{table}' "
        f"ORDER BY ordinal_position"
    )
    return run_query(sql)


def parse_table_output(raw: str) -> list[dict]:
    """Parse Coral's ASCII +--+--+ table output into a list of dicts."""
    lines = raw.strip().splitlines()
    headers: list[str] = []
    rows: list[dict] = []
    for line in lines:
        if line.startswith('+') or not line.strip():
            continue
        if line.startswith('|'):
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if not headers:
                headers = cells
            elif len(cells) == len(headers):
                rows.append(dict(zip(headers, cells)))
    return rows


if __name__ == "__main__":
    owner = os.getenv("GITHUB_OWNER", "withcoral")
    repo  = os.getenv("GITHUB_REPO",  "coral")
    sql = """SELECT number, title, user_login as author
FROM github.search_issues(
  q => 'repo:{owner}/{repo} is:issue is:open created:<{30_days_ago} sort:comments-asc'
)
LIMIT 5"""
    print(f"Running triage query against {owner}/{repo}...\n")
    print(run_query(sql, owner=owner, repo=repo))
