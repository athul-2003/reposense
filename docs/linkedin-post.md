# LinkedIn Post

---

I participated in the **Pirates of the Coral-bean Hackathon** by WeMakeDevs × Coral this week — and here's what I built and submitted as my project.

**RepoSense** — a GitHub intelligence CLI that answers the question: *what actually needs attention in this repo right now?* In under 10 seconds, for any public GitHub repo.

You point it at any repo and get:

- The oldest unattended issues (triage)
- Stale PRs blocking your team
- What shipped in the last 2 weeks
- What Hacker News is saying about the project
- Known CVEs for your dependencies (Dependabot + OSV)
- Who's contributing most right now
- Likely duplicate issues (similarity-filtered, not just all pairs)
- A live repo health score (0–100)
- What the tech community is discussing alongside your open issues (cross-source SQL JOIN)
- Top Stack Overflow questions for this project's technology

And if none of those fit — you just ask in plain English. The built-in Claude agent writes the SQL and runs it live.

It also runs as an **MCP server** — `reposense --mcp` — so Claude Desktop can call all 12 commands directly. Results are cached to disk for 5 minutes (matching Coral's own HTTP cache window), so repeated queries return instantly with a `⚡ cached` indicator.

**The interesting part: every command is a SQL query hitting live APIs.**

GitHub becomes `github.search_issues()`. Hacker News becomes `hn.search`. CVE data becomes `osv.query_by_version`. Stack Overflow becomes `stackoverflow.questions`. No database. No ETL. No stale cache. Just SQL against live data — powered by Coral.

The boldest query is `pulse` — a single SQL statement that CROSS JOINs live HN posts against live GitHub issues across two separate Coral sources. This is what Coral is actually built for: real relational operations between live APIs in one query.

The hardest engineering problem wasn't writing the queries — it was making them work on repos of wildly different sizes. `LIMIT 15` on `django/django` (14,000+ issues) timed out with a naive approach because the REST-paginated table fetches all pages before applying `LIMIT` locally. The fix: `github.search_issues()` pushes filters to GitHub Search API server-side. Same query, any repo size, under 2 seconds.

I also wrote a custom Coral source spec for Stack Overflow (Stack Exchange API, zero auth) — shipped as `sources/stackoverflow/manifest.yaml`.

I documented every trade-off in an engineering decisions log — 12 real constraints found by testing 40 commands across 4 repos of very different scales.

The entire project was built and submitted within the hackathon week — from idea to working CLI — as my entry for the **Pirates of the Coral-bean Hackathon** (WeMakeDevs × Coral, May 2026).

**Try it:**
```
git clone https://github.com/athulkrishnan-h/reposense
cd reposense && bash setup.sh
reposense --repo your-org/your-repo triage
```

Full write-up → [link to blog post]

#OpenSource #SQL #GitHub #DeveloperTools #Hackathon #Coral #ClaudeAI #Python #CLI

---

## First comment (post immediately after — boosts reach)

Full blog post on how I built this, the SQL patterns, and the 12 engineering decisions from testing on 14,000-issue repos: [link to blog post]

---

## Notes before posting

- Add 1-2 terminal screenshots (health score bar + triage table) — images get 3-5x more reach on LinkedIn
- Tag Coral's LinkedIn page and WeMakeDevs if they have one
- Post before May 31 so judges see it
- Best time: 10am–12pm your timezone on a weekday
