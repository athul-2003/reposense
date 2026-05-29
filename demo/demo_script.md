# RepoSense — 2 Minute Demo Script

## Preparation
- Terminal font size: 16+
- Terminal width: 120 chars minimum
- Run `./demo/demo.sh withcoral/coral 1` as a dry run first
- Have django/django ready for the live switch moment

---

## 0:00–0:15 — The problem
"Every open source maintainer wastes hours on the same things:
triaging issues, chasing stale PRs, writing release notes,
wondering if anyone on the internet is talking about their bugs.
No single tool answers all of these at once. Until now."

## 0:15–0:30 — Feature 1: Triage
[run: `./run.sh --repo withcoral/coral triage`]
"RepoSense works on any GitHub repo. I'm running it against
the Coral repo itself. Notice the SQL panel — that query
ran live through Coral against GitHub's API. Red rows are
issues aging with no engagement. Green is healthy."

## 0:30–0:50 — Features 4 and 5: The unique ones
[run: `./run.sh --repo withcoral/coral hn-buzz`]
"Here's what makes RepoSense different from every other
GitHub tool. This just searched Hacker News for discussions
related to this repo — two completely different sources,
one Coral query, zero glue code."

[run: `./run.sh --repo withcoral/coral cve-scan`]
"And this cross-referenced open issues with Google's OSV
vulnerability database. Security intelligence built in.
Three sources. One agent."

## 0:50–1:10 — Show the SQL
"Every answer came from a SQL query through Coral. Here's
the actual CVE scan query that just ran."
[point to the show_sql() panel on screen]
"GitHub joined with OSV. Live data. No pipeline. No ETL.
Just Coral doing what it does."

## 1:10–1:30 — The wow moment: switch repos live
"But here's the thing — this works on any public GitHub repo."
[run: `./run.sh --repo django/django triage`]
"django/django. 14,000 open issues. Same agent. Same command.
Instant results. Zero configuration change."

## 1:30–1:50 — Install
"One command to install:"
[type: `uv tool install .`]
[type: `reposense --repo your-org/your-repo`]
"Any repo. Any developer. Works immediately."

## 1:50–2:00 — Close
"RepoSense. 10 commands. 4 sources. Any repo.
Zero glue code. Powered by Coral."

---

## Tips for recording
- Use asciinema for terminal recording:
  ```
  asciinema rec demo/demo.cast
  asciinema play demo/demo.cast
  ```
- Export to GIF for README:
  ```
  agg demo/demo.cast demo/demo.gif
  ```
- Keep pauses natural — let each output breathe before narrating
- The django/django switch at 1:10 is the most important moment
  — pause, let it load, let the audience see it works
