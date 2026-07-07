# Repository Health

**Project:** WC Lead-Gen
**Last Verified:** July 2026

**Type:** Python workers-comp lead decision engine

## Public boundary

Open scoring, compliance, and routing engine only. Real SMB records, partner lists, prompts, call logs, and production credentials stay private.

## Local verification

Run these before opening a PR or publishing a release:

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q
ruff check .
```

## Release checklist

- Tests pass from a clean clone.
- Examples use synthetic names, numbers, domains, and records.
- No `.env`, credentials, real transcripts, customer data, private URLs, or production exports are included.
- README examples still match the CLI and library API.
- Any side-effecting workflow stays dry-run or explicitly gated by default.

## GitHub hygiene added

- Bug report and feature request templates.
- Pull request checklist focused on tests and data safety.
- Weekly Dependabot checks for GitHub Actions.
- Security policy when the repo did not already have one.