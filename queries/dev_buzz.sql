-- Feature 11: Dev Buzz — Top Dev.to articles for this technology
-- Requires: coral source add --file sources/devto/manifest.yaml
-- Uses the same {hn_query} auto-detection as hn-buzz and so-buzz:
--   1. HN_QUERY env var — always wins
--   2. First topic from github.repo_topics (e.g. django → python)
--   3. Repo name as fallback
-- Sources: devto (zero auth — Dev.to public API)

SELECT
  article_id,
  title,
  reactions,
  comments_count,
  reading_time_minutes,
  author,
  SUBSTR(published_at, 1, 10) AS published_date,
  url
FROM devto.articles
WHERE tag = '{hn_query}'
LIMIT 10
