# RepoSense — Claude Code Instructions

## Skills

The following project skills are available as slash commands and should be applied automatically when the context matches:

| Skill | When to apply |
|-------|--------------|
| `/reposense-commit-push` | Committing work, pushing to GitHub, creating a PR, merging a branch |
| `/coral` | Querying GitHub, Jira, Slack, Linear, Datadog, Sentry, or any connected external source |
| `/coral-create-source-spec` | Authoring or editing a Coral source spec YAML |
| `/coral-review-source-spec` | Reviewing a Coral source manifest or a PR that adds/changes a Coral source |

Skill definitions live in `.agents/skills/<name>/SKILL.md`. Read the relevant skill file before acting on tasks that match its trigger.

## Git rules (always apply)

- Never commit directly to `main` — always use a feature branch + PR
- Never `git add -A` or `git add .` — stage files by name
- Follow conventional commits: `<type>(<scope>): <summary>`
- Co-author line: `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`
