-- Feature 4: HN Buzz Detector
-- Surfaces Hacker News posts about topics related to this repo's open issues.
-- Sources: github (PAT) + hn (zero auth)
--
-- Design note: h.query = i.title (JOIN on issue title) returns 0 rows because
-- GitHub issue titles are too specific to match HN full-text search.
-- Correct approach: run two parallel queries —
--   Query A (this file): search HN for the project/technology name
--   Query B: fetch open github.issues
-- Claude reads both results together and surfaces thematic connections.

-- Query A: HN posts about this project/technology
-- {hn_query} is resolved at runtime in priority order:
--   1. HN_QUERY env var (set in .env) — always wins
--   2. First topic from github.repo_topics (e.g. django→python, express→javascript)
--   3. Repo name as fallback
SELECT
  h.title as hn_post_title,
  h.points as hn_upvotes,
  h.num_comments as hn_comments,
  h.url as hn_link,
  h.author,
  CAST(h.created_at AS DATE) as posted_date
FROM hn.search h
WHERE h.query = '{hn_query}'
  AND h.points > 5
ORDER BY h.points DESC
LIMIT 10
