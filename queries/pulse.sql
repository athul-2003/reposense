-- Feature 9: Community Pulse — cross-source SQL JOIN (GitHub + HN)
-- CROSS JOIN between top HN posts and top open GitHub issues.
-- Demonstrates a real cross-source SQL JOIN across two Coral sources
-- (github PAT + hn zero-auth) in a single statement.
-- Sources: github (PAT) + hn (zero auth)
--
-- {hn_query} resolves at runtime:
--   1. HN_QUERY env var — always wins
--   2. First topic from github.repo_topics (e.g. django → python)
--   3. Repo name as fallback

SELECT
  h.title  AS hn_post,
  h.points AS hn_score,
  g.number AS github_issue,
  g.title  AS github_issue_title,
  g.user_login AS github_author
FROM hn.search h
CROSS JOIN (
  SELECT number, title, user_login
  FROM github.search_issues(
    q => 'repo:{owner}/{repo} is:open sort:comments-desc'
  )
  LIMIT 5
) g
WHERE h.query = '{hn_query}'
  AND h.points > 20
ORDER BY h.points DESC
LIMIT 25
