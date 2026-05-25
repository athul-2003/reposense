-- Feature 7: Duplicate Issue Detector
-- CROSS JOIN bounded to 50 most recent open issues per side.
-- Maximum 1225 pairs from 50 issues; Python filters for title similarity.
-- Sources: github (PAT)
-- Note: covers the 50 most recently opened issues only.

SELECT
  a.number as issue_a,
  a.title as title_a,
  b.number as issue_b,
  b.title as title_b
FROM (
  SELECT number, title
  FROM github.issues
  WHERE owner = '{owner}' AND repo = '{repo}'
    AND state = 'open'
  ORDER BY created_at DESC
  LIMIT 50
) a
CROSS JOIN (
  SELECT number, title
  FROM github.issues
  WHERE owner = '{owner}' AND repo = '{repo}'
    AND state = 'open'
  ORDER BY created_at DESC
  LIMIT 50
) b
WHERE a.number < b.number
ORDER BY a.number, b.number
LIMIT 2000
