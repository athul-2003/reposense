# Submitting the Stack Overflow Source Spec to the Coral Community Repo

## What this achieves

Submitting `sources/stackoverflow/manifest.yaml` as a pull request to `withcoral/coral` directly:
- Qualifies more explicitly for the **$100 custom source spec bounty** (judges see the PR in the coral repo, not just our repo)
- Demonstrates community participation — visible to hackathon judges who look at the coral repo activity
- The manifest is already written, tested, and working — no new work needed

---

## Prerequisites

You need:
- A GitHub account (`athulkrishnan-h`)
- Git configured with your SSH key (already done on this machine)
- The `gh` CLI authenticated (already done: `gh auth status` should show `athulkrishnan-h`)

---

## Step-by-step

### 1. Fork the coral repo

Go to https://github.com/withcoral/coral and click **Fork** → Create fork under `athulkrishnan-h`.

Or via CLI:
```bash
gh repo fork withcoral/coral --clone=false
```

### 2. Clone your fork locally

```bash
cd /tmp
git clone git@github.com:athulkrishnan-h/coral.git coral-fork
cd coral-fork
```

### 3. Find where community sources live

```bash
ls sources/community/
# Look for existing examples: hn/, osv/, remotive/, etc.
# Your manifest goes alongside those.
```

### 4. Create the branch and copy the manifest

```bash
git checkout -b feat/sources/community/stackoverflow
mkdir -p sources/community/stackoverflow
cp /home/sayone-198/reposense/sources/stackoverflow/manifest.yaml sources/community/stackoverflow/manifest.yaml
cp /home/sayone-198/reposense/sources/stackoverflow/README.md sources/community/stackoverflow/README.md
```

### 5. Check what other community source READMEs look like

```bash
cat sources/community/hn/README.md   # or remotive/README.md
# Match their format if different from ours
```

### 6. Stage and commit

```bash
git add sources/community/stackoverflow/
git status   # verify only these two files are staged
git commit -m "feat(sources/community/stackoverflow): add Stack Overflow source spec

Adds a community Coral source for Stack Overflow questions via the
Stack Exchange API. Zero-auth for public data (300 req/day); optional
STACK_EXCHANGE_KEY raises this to 10,000 req/day.

Exposes: stackoverflow.questions
Required filters: tagged = '<tag>' AND site = 'stackoverflow'
Returns: question_id, title, score, answer_count, view_count,
         is_answered, tags, asker, created_at, link

Tested against: python, javascript, django, sql tags."
```

### 7. Push to your fork

```bash
git push origin feat/sources/community/stackoverflow
```

### 8. Create the pull request

```bash
gh pr create \
  --repo withcoral/coral \
  --title "feat(sources/community/stackoverflow): add Stack Overflow source spec" \
  --body "$(cat <<'EOF'
## Summary

Adds a community Coral source for Stack Overflow questions via the Stack Exchange API.

## Source details

- **Table**: `stackoverflow.questions`
- **Auth**: Zero-auth for public data (300 req/day). Optional `STACK_EXCHANGE_KEY` env var for 10,000 req/day.
- **Required filters**: `tagged = '<tag>'` AND `site = 'stackoverflow'`
- **DSL version**: 3

## Example query

\`\`\`sql
SELECT title, score, answer_count, is_answered, asker
FROM stackoverflow.questions
WHERE tagged = 'python' AND site = 'stackoverflow'
ORDER BY score DESC
LIMIT 10
\`\`\`

## Columns returned

| Column | Type | Description |
|---|---|---|
| question_id | Int64 | Unique SO question ID |
| title | Utf8 | Question title |
| score | Int64 | Net vote score |
| answer_count | Int64 | Number of answers posted |
| view_count | Int64 | Total views |
| is_answered | Boolean | True if accepted answer exists |
| tags | Utf8 | Comma-joined tag list |
| asker | Utf8 | Display name of the question author |
| created_at | Timestamp | When the question was posted (UTC) |
| link | Utf8 | Direct URL to the question |

## Testing

Tested against tags: `python`, `javascript`, `django`, `sql`, `express`.

Built and used in [RepoSense](https://github.com/athulkrishnan-h/reposense) as part of the Pirates of the Coral-bean Hackathon (WeMakeDevs × Coral, May 2026).

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)" \
  --base main \
  --head athulkrishnan-h:feat/sources/community/stackoverflow
```

### 9. Share the PR link

Once created, note the PR URL (e.g. `https://github.com/withcoral/coral/pull/XXX`) and:
- Include it in your hackathon submission form
- Mention it in your Discord post
- Add it to your LinkedIn post as evidence of community contribution

---

## If the coral repo has a contribution guide

Check `CONTRIBUTING.md` in the coral repo before submitting. If they have a required format for source spec PRs, match it. Look at recent merged PRs for community sources (like Akash's Terraform Cloud PR #756) to see what reviewers expect.

---

## Time estimate

~20 minutes from fork to PR open, assuming the manifest format matches what coral expects.
