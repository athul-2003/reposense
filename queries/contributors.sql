-- Feature 6: Contributor Activity Summary
-- Uses github.search_issues() for server-side filtering.
-- Fast on any repo regardless of size. Sources: github (PAT)
--
-- Design decisions:
-- 1. search_issues() not github.issues/github.pulls — REST-paginated
--    tables apply LIMIT locally after fetching all pages.
--    On large repos (django/django: 14k+ items) this hits the 30s
--    Coral timeout regardless of LIMIT value.
--    search_issues() delegates filtering to GitHub Search API.
--
-- 2. LIMIT 100 on the subquery caps pagination at ~3-4 API pages.
--    Top contributors in last 30 days always appear in first 100
--    most recently created items. Accurate for a top-10 leaderboard.
--
-- 3. No is:issue / is:pr qualifier — is:issue is unsupported in
--    Coral search_issues() on large repos. Single query counts
--    all authored items (issues + PRs combined).
--
-- 4. github.comments removed — tracked commit comments only,
--    not issue/PR review comments. Always returned 0. Removed.

SELECT user_login as actor, COUNT(*) as total
FROM (
  SELECT user_login
  FROM github.search_issues(
    q => 'repo:{owner}/{repo} created:>{30_days_ago}'
  )
  LIMIT 100
) sub
GROUP BY user_login
ORDER BY total DESC
LIMIT 10
