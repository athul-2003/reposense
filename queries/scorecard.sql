-- Feature 12: Scorecard — OpenSSF security health checks for this repository
-- Requires: coral source add --file sources/scorecard/manifest.yaml
-- Works for any public GitHub repository tracked by OpenSSF Scorecard.
-- Data is updated weekly. No API key required.
--
-- Sort order: lowest scores first (most improvement needed), N/A (-1) last.

SELECT
  check_name,
  score,
  reason
FROM scorecard.checks
WHERE owner = '{owner}'
  AND repo  = '{repo}'
ORDER BY
  CASE WHEN score = -1 THEN 999 ELSE score END ASC
