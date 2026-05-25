-- Feature 10: SO Buzz — Top Stack Overflow questions for this technology
-- Requires: coral source add --file sources/stackoverflow/manifest.yaml
-- Uses the same {hn_query} auto-detection as hn-buzz:
--   1. HN_QUERY env var — always wins
--   2. First topic from github.repo_topics (e.g. django → python)
--   3. Repo name as fallback
-- Sources: stackoverflow (zero auth — Stack Exchange public API)

SELECT
  question_id,
  title,
  score,
  answer_count,
  view_count,
  is_answered,
  asker,
  CAST(created_at AS DATE) as posted_date,
  link
FROM stackoverflow.questions
WHERE tagged  = '{hn_query}'
  AND site    = 'stackoverflow'
  AND sort    = 'votes'
  AND order   = 'desc'
LIMIT 10
