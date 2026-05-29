---
name: reposense-commit-push
description: Full Git flow for the RepoSense project — feature branch → commit → PR → merge into main. Use when committing changes, creating a PR, or pushing work to GitHub.
---

# Skill: reposense-commit-push

Full Git flow for the RepoSense project — feature branch → commit → PR → squash merge into main.

## Repository details

- Remote: git@github.com:athul-2003/reposense.git
- Default branch: `main` (protected — never commit directly)
- Auth: SSH key (ed25519, already registered on athul-2003 GitHub account)
- PR/merge tool: `gh` CLI authenticated as `athul-2003`

## Prerequisites (one-time setup — already done on this machine)

```bash
# Install gh CLI (requires sudo)
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update && sudo apt install gh -y

# Authenticate (choose SSH + athul-2003 account)
gh auth login

# Verify
gh auth status   # should show: Logged in as athul-2003
```

---

## Branch naming convention

Format: `<type>/<short-description>`

| Type | When to use |
|------|-------------|
| `feat/` | New feature or capability |
| `fix/` | Bug fix |
| `chore/` | Setup, config, scaffolding, dependencies |
| `docs/` | README, blog post, SRS, comments |
| `refactor/` | Code restructure with no behaviour change |
| `test/` | Query tests, unit tests |

Rules:
- Lowercase and hyphens only — no spaces, underscores, or CamelCase
- 3–5 words max
- One feature per branch — never mix unrelated changes

Examples:
```
feat/day2-hn-osv-sources
feat/day3-terminal-ui
feat/day4-demo-polish
fix/coral-runner-timeout
chore/day1-env-setup
docs/readme-and-demo
```

---

## Full workflow — step by step

### Step 1 — Start from a fresh main

Always pull the latest main before creating a new branch:

```bash
git checkout main
git pull origin main
```

### Step 2 — Create the feature branch

```bash
git checkout -b feat/your-branch-name
```

Verify you are on the right branch:

```bash
git branch
```

### Step 3 — Do the work, then stage specific files

Never use `git add -A` or `git add .` — always add files by name:

```bash
git add path/to/file1 path/to/file2
```

Review exactly what is staged before committing:

```bash
git status
git diff --staged
```

### Step 4 — Commit with conventional commit message

Format: `<type>(<scope>): <short summary in imperative mood>`

```bash
git commit -m "$(cat <<'EOF'
<type>(<scope>): <short summary — max 50 chars, imperative mood>

- Bullet point describing what changed and why
- Another bullet if needed
- Keep each line under 72 chars

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

Commit message rules:
- Imperative mood: "add" not "added" / "adds"
- Summary ≤ 50 characters
- Body bullets explain WHY, not just what
- One logical change per commit (atomic)

Examples:
```
feat(day2): add HN and OSV community sources to Coral
fix(coral-runner): handle empty result set from coral sql
chore(day1): add .gitignore and commit-push skill
docs(readme): add demo GIF and SQL query showcase section
```

### Step 5 — Push the feature branch

```bash
git push origin feat/your-branch-name
```

If you rebased locally and need to update the remote feature branch (never do this on main):

```bash
git push --force-with-lease origin feat/your-branch-name
```

### Step 6 — Create a Pull Request

Use the GitHub CLI:

```bash
gh pr create \
  --title "<type>(<scope>): <same as commit summary>" \
  --body "$(cat <<'EOF'
## What does this PR do?
Brief description of the feature or fix.

## Why?
Context and motivation — what problem does this solve?

## Changes
- File/module A: what changed
- File/module B: what changed

## How to test
Step-by-step instructions to verify the change works.

## Checklist
- [ ] All changed files are intentional (no accidental files)
- [ ] Commit messages follow conventional commits format
- [ ] No secrets or .env files included

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)" \
  --base main \
  --head feat/your-branch-name
```

### Step 7 — Merge the PR (merge commit — preserves branch in graph)

Use a regular merge commit so the feature branch is visible in the git graph:

```bash
gh pr merge <PR-number> --merge --delete-branch
```

The `--delete-branch` flag removes the remote feature branch automatically after merge.

**Why `--merge` not `--squash`:**
- `--squash` flattens all branch commits into one on main → graph is a flat straight line, branch history invisible
- `--merge` creates a merge commit on main → graph shows the branch diverging and merging back in → clean, readable history
- Use `--squash` only for noisy WIP branches with many "fix typo" commits you want to hide

### Step 8 — Sync local main

```bash
git checkout main
git pull origin main
git branch  # confirm feature branch is gone locally too
```

If the local feature branch still exists after the remote was deleted:

```bash
git branch -d feat/your-branch-name
```

---

## Rules — never break these

| Rule | Why |
|------|-----|
| Never commit directly to `main` | main is the source of truth — all changes go through PRs |
| Never `git push --force` on `main` | Destroys history for everyone |
| Never `git add -A` or `git add .` | Risks committing .env, secrets, or junk files |
| Never skip `git pull origin main` before branching | Avoids conflicts and diverged branches |
| Always delete branch after merge | Keeps the branch list clean and readable |
| Always squash merge into main | Keeps main history linear — one commit per feature |
| Use `--force-with-lease` not `--force` on feature branches | Safer: fails if remote changed since last fetch |

---

## Quick reference — full flow in one block

```bash
# Start
git checkout main && git pull origin main

# Branch
git checkout -b feat/your-feature-name

# Work, stage, commit
git add file1 file2
git diff --staged
git commit -m "feat(scope): summary"

# Push
git push origin feat/your-feature-name

# PR
gh pr create --title "feat(scope): summary" --body "..." --base main

# Merge (merge commit) + delete branch
gh pr merge <PR-number> --merge --delete-branch

# Sync main
git checkout main && git pull origin main
```
