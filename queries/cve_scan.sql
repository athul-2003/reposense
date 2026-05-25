-- Feature 5: CVE / Security Scan — Query A
-- Dependabot alerts: real, confirmed CVEs in this repo's dependencies.
-- Requires Dependabot to be enabled on the repo and PAT scope: security_events.
-- Returns an error gracefully if neither condition is met.
-- Sources: github (Dependabot API)

SELECT
  dependency__package__name as package,
  dependency__package__ecosystem as ecosystem,
  security_advisory__summary as summary,
  security_advisory__severity as severity,
  security_advisory__cve_id as cve_id,
  security_advisory__ghsa_id as ghsa_id,
  state
FROM github.repo_dependabot_alerts
WHERE owner = '{owner}' AND repo = '{repo}'
  AND state = 'open'
ORDER BY alert_number DESC
LIMIT 20

-- ==QUERY_B==

-- Feature 5: CVE / Security Scan — Query B
-- Finds open issues mentioning security-related keywords via search_issues().
-- Keyword match only — disclaimer is shown below the table.
-- Sources: github (PAT)

SELECT number, title, html_url, user_login as author
FROM github.search_issues(
  q => 'repo:{owner}/{repo} is:issue is:open security vulnerability'
)
LIMIT 20

-- ==QUERY_C==

-- Feature 5: CVE / Security Scan — Query B
-- Known CVEs for a dependency package via OSV.
-- Sources: osv (zero auth)
-- Configure via .env: PACKAGE_NAME, PACKAGE_ECOSYSTEM, PACKAGE_VERSION
-- Defaults: requests / PyPI / 2.25.0

SELECT
  o.id as cve_id,
  o.summary as vulnerability_summary,
  o.severity,
  o.published as cve_published
FROM osv.query_by_version o
WHERE o.package_name = '{package_name}'
  AND o.ecosystem = '{package_ecosystem}'
  AND o.version = '{package_version}'
