# Contributing to wcleadgen

Thanks for considering a contribution. This project aims to stay small, readable, and dependency-free at its core.

## Development setup

```bash
git clone https://github.com/redzicdenis08-afk/wc-leadgen
cd wc-leadgen
pip install -e ".[dev]"
```

## Running tests

```bash
python -m pytest tests/ -q
```

## Guidelines

- Keep the core dependency-free (standard library only). Optional features go behind extras.
- **Never weaken the fail-closed contract.** Any new compliance check must block on missing or ambiguous input, and every block must carry a machine-readable reason code. A PR that makes an unknown input pass a gate will be rejected.
- Routing must stay deterministic: same inputs, same partner, every time. If you add a ranking signal, it needs a total tie-break at the end.
- Add a test for every new factor, check, or routing rule — including at least one fail-closed edge case.
- All example data must be clearly synthetic: `example.com` addresses, `+1-555` phone numbers, fictional business names.
- Run `ruff check .` before opening a PR.
- One focused change per PR. Describe the before/after behavior in the description.

## Adding a compliance check

1. Write a `check_<name>` function in `wcleadgen/compliance.py` that returns a `ComplianceCheck` and never raises.
2. Wire it into the channel plan inside `check_compliance`.
3. Add tests proving both the pass path and the fail-closed path (missing input → blocked with a specific reason code).

## Tuning the scoring model

Scoring weights live in small tables at the top of `wcleadgen/scoring.py`. If you adjust a band or weight, update the factor-budget comment in the module docstring so the documented budget still sums to 100.
