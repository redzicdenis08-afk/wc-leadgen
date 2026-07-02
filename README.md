# WC Lead-Gen

**Reference implementation of a workers'-comp premium-audit lead-gen pipeline: explainable lead scoring, a fail-closed compliance engine, and deterministic consult routing.** Feed it structured business data; get back who to contact, whether you're *allowed* to contact them, and which partner audit firm should take the consult — with a full audit trail for every decision.

[![CI](https://github.com/redzicdenis08-afk/wc-leadgen/actions/workflows/ci.yml/badge.svg)](https://github.com/redzicdenis08-afk/wc-leadgen/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

> This repo is the open **reference implementation** of a production system that finds qualifying small businesses, qualifies them with an AI voice agent, recruits audit-firm partners, and routes consults between them. The production code, prompts, and data stay private; the decision logic that makes it safe to operate — scoring, compliance gating, routing — is reimplemented here in clean, dependency-free Python. All example data is synthetic.

## Why this exists

Workers'-comp premiums are calculated from payroll, class codes, and experience mods — and they're wrong surprisingly often. Businesses in high-mod industries (roofing, trucking, staffing) routinely overpay for years. A premium-audit consult finds that money. But cold outreach to small businesses is a legal minefield: TCPA quiet hours vary by state, some states ban Sunday calls, four states don't even have a private WC market, and one call to a DNC-listed number can cost more than a month of won consults.

The core lesson from running this in production: **the compliance gate cannot be an afterthought bolted onto the dialer.** It has to sit in the middle of the pipeline, it has to be able to say "no", and — critically — it has to say "no" when it *doesn't know*. That is the fail-closed philosophy, and it's the signature piece of this repo.

Zero runtime dependencies. Pure standard library. Every decision explainable and reproducible.

## The fail-closed philosophy

Most outreach systems fail *open*: missing state? Call anyway. No suppression list loaded? Probably fine. That works right up until it doesn't. `wcleadgen` inverts the default — **any missing, unknown, or ambiguous input blocks the lead, with a machine-readable reason code:**

| Situation | Fail-open system | `wcleadgen` |
|---|---|---|
| Lead has no state | calls anyway | `missing_state` — blocked |
| State not in eligibility table | calls anyway | `unknown_state` — blocked |
| Suppression list failed to load | calls anyway | `no_suppression_list` — blocked |
| Timestamp missing or naive | assumes server time | `missing_timestamp` / `naive_timestamp` — blocked |
| No SMS consent record | texts anyway | `no_consent_record` — blocked |
| A check throws an exception | crashes or skips | `check_error` — blocked |

Every check runs even after the first failure, so a blocked lead reports *all* of its violations, not just the first one. `allowed` is true only when every gate passes.

## Architecture

```
                 ┌─────────────────────────────────────────────────────┐
                 │                     PIPELINE                        │
                 │                                                     │
  leads          │  ┌─────────┐    ┌────────────────┐    ┌─────────┐   │   partner
  (CSV/JSON) ───▶│  │ SCORING │───▶│ COMPLIANCE GATE│───▶│ ROUTING │   │──▶ firm
                 │  └────┬────┘    └───────┬────────┘    └────┬────┘   │
                 │       │                 │                  │        │
                 │   0-100 score      fail-closed:        deterministic│
                 │   5 factors,       state eligibility   state ∙ cap  │
                 │   each explained   DNC / suppression   ∙ specialty  │
                 │       │            calling windows     ∙ tie-break  │
                 │       ▼            quiet hours             │        │
                 │  rejected if       CAN-SPAM fields         ▼        │
                 │  score < 60        SMS consent         no_partner   │
                 │                        │               if unmatched │
                 │                        ▼                            │
                 │                  blocked w/ reason                  │
                 │                  codes if ANY gate                  │
                 │                  fails or is unsure                 │
                 │                                                     │
                 │        every stage appends to the AUDIT TRAIL       │
                 └─────────────────────────────────────────────────────┘
```

Gate order is deliberate: a weak lead never touches the compliance engine, and a compliance block always halts before routing. Each stage appends an `AuditEvent`, so every `PipelineResult` carries a replayable record of why the lead ended up where it did.

## Install

```bash
pip install -e .        # from source; zero runtime dependencies
```

## Quickstart

### CLI

Score the bundled synthetic leads:

```bash
wcleadgen score examples/leads.csv
```

```
LEAD           SCORE  GRADE QUALIFIED  TOP FACTORS
------------------------------------------------------------------------------
lead-001         100  A     true       industry_risk=30, employee_count=25
lead-002          93  A     true       industry_risk=28, employee_count=25
lead-003          55  C     false      employee_count=20, industry_risk=15
lead-004          77  B     true       industry_risk=22, employee_count=15
lead-005          89  A     true       employee_count=25, industry_risk=22
lead-006           6  D     false      industry_risk=4, employee_count=2
lead-007          88  A     true       industry_risk=25, employee_count=20
lead-008          78  B     false      industry_risk=25, employee_count=25
------------------------------------------------------------------------------
8 lead(s) | 5 qualified
```

Run the compliance gate (exit code 1 if anything is blocked — CI-friendly):

```bash
wcleadgen check examples/leads.csv --channel call \
    --when 2026-07-08T18:00:00+00:00 --dnc examples/dnc.txt
```

```
LEAD           CHANNEL  VERDICT  REASONS
----------------------------------------------------------------------
lead-001       call     ALLOWED  -
lead-002       call     ALLOWED  -
lead-003       call     BLOCKED  dnc_listed
lead-004       call     ALLOWED  -
lead-005       call     BLOCKED  state_monopolistic, dnc_listed
lead-006       call     BLOCKED  missing_state, missing_phone
lead-007       call     ALLOWED  -
lead-008       call     ALLOWED  -
----------------------------------------------------------------------
8 lead(s) | 3 blocked (fail-closed)
```

Full pipeline — score, gate, route:

```bash
wcleadgen run examples/leads.csv --partners examples/partners.json \
    --when 2026-07-08T18:00:00+00:00 --dnc examples/dnc.txt
```

```
LEAD           SCORE  STATUS               DETAIL
--------------------------------------------------------------------------
lead-001         100  routed               -> Alpha Premium Audit Group
lead-002          93  routed               -> Beta Comp Consultants
lead-003          55  rejected_low_score   not qualified (score 55, grade C)
lead-004          77  routed               -> Gamma Risk Advisors
lead-005          89  blocked_compliance   state_monopolistic, dnc_listed
lead-006           6  rejected_low_score   not qualified (score 6, grade D)
lead-007          88  routed               -> Delta Audit Partners
lead-008          78  rejected_low_score   not qualified (score 78, grade B)
--------------------------------------------------------------------------
8 lead(s) | 4 routed | 1 blocked by compliance
```

Note lead-008: an otherwise excellent B-grade lead that never routes, because it has no active WC policy — no premium to audit. And lead-005 scores 89 but is blocked twice over (Ohio is a monopolistic WC state, and the number is DNC-listed). Score never overrides compliance.

Add `--json` to any subcommand for machine-readable output.

### Library

```python
from datetime import datetime, timezone
from wcleadgen import Lead, SuppressionList, check_compliance, score_lead

lead = Lead.from_dict({
    "lead_id": "lead-001",
    "business_name": "Acme Roofing LLC",
    "state": "TX",
    "industry": "roofing",
    "employee_count": 34,
    "annual_payroll": 2_400_000,
    "years_in_business": 12,
    "wc_policy_active": True,
    "phone": "+1-555-010-4477",
})

score = score_lead(lead)
score.score        # 100
score.qualified    # True
score.factors      # 5 ScoreFactors, each with points, max_points, and a detail string

verdict = check_compliance(
    lead, "call",
    when=datetime(2026, 7, 8, 18, 0, tzinfo=timezone.utc),
    suppression=SuppressionList(phones={"+1-555-010-3390"}),
)
verdict.allowed          # True
verdict.blocked_reasons  # []
```

A blocked verdict is fully machine-readable:

```json
{
  "lead_id": "lead-005",
  "channel": "call",
  "allowed": false,
  "blocked_reasons": ["state_monopolistic", "dnc_listed"],
  "checks": [
    {"name": "state_eligibility", "passed": false, "reason": "state_monopolistic",
     "detail": "OH is a monopolistic WC state — out of scope"},
    {"name": "suppression", "passed": false, "reason": "dnc_listed",
     "detail": "phone is on the DNC/suppression list"},
    {"name": "calling_window", "passed": true, "reason": "ok",
     "detail": "local time 14:00 inside window"}
  ]
}
```

## What each stage does

### 1. Scoring (`wcleadgen/scoring.py`)

Five factors, each returning its points and a one-line explanation. The budget sums to 100:

| Factor | Max | Signal |
|---|---|---|
| `industry_risk` | 30 | high-mod industries (roofing, trucking, staffing…) misclassify most often |
| `employee_count` | 25 | the 5–100 employee band is the sweet spot |
| `payroll_band` | 20 | bigger payroll = bigger potential premium error |
| `audit_history` | 15 | never-audited businesses have the most recoverable premium |
| `years_in_business` | 10 | established firms have premium history worth auditing |

Qualification requires score ≥ 60 **and** no known-inactive WC policy. Missing data earns zero points — a lead can't score its way up on unknowns.

### 2. Compliance gate (`wcleadgen/compliance.py`)

Per-channel checks, all fail-closed:

- **State eligibility** — monopolistic WC states (ND, OH, WA, WY) are out of scope; unknown states blocked.
- **DNC / suppression** — phone numbers normalized before matching (`+1 (555) 010-4477` ≡ `5550104477`); a missing suppression list blocks everything, because "we couldn't check" is not "clear".
- **Calling windows** — per-state quiet hours over the federal TCPA 8am–9pm baseline (KY starts at 10am; TX, AL, LA, and others ban Sunday calls), plus an internal 9am–8pm safety buffer, federal-holiday skips, and pure-stdlib DST-aware timezone math per state.
- **CAN-SPAM** (email) — from address, physical postal address, unsubscribe mechanism, and subject must all be present.
- **SMS consent** — no record of prior express consent means no text.

### 3. Routing (`wcleadgen/routing.py`)

Filters partner firms by state coverage (or `US` nationwide), remaining capacity, and score floor, then ranks: specialty match → most remaining capacity → most specialized coverage → `firm_id`. The last tie-break is total, so routing is fully deterministic — same inputs, same partner, every time. The result includes a per-firm decision trace explaining why every candidate won or lost.

### 4. Pipeline (`wcleadgen/pipeline.py`)

`run_pipeline` wires the stages together; `run_batch` additionally decrements partner capacity as consults are assigned, so a firm can't be over-routed within a batch.

## Design principles

1. **Fail closed, always.** Unknown ⇒ blocked. The absence of a "no" is not a "yes".
2. **Machine-readable reasons.** Every block is a stable code (`dnc_listed`, `too_early`, `state_no_sunday`), not prose — downstream systems can retry, requeue, or escalate on it.
3. **Explainability over cleverness.** Scores decompose into factors; routing returns its candidate trace; the whole scoring model is a small table you can read in one sitting.
4. **Determinism.** No randomness anywhere. Same inputs, same outputs — which makes the audit trail actually replayable.
5. **Zero dependencies.** Pure standard library, including the timezone/DST math. Nothing to install, nothing to break.

## Examples

- [`examples/leads.csv`](examples/leads.csv), [`examples/leads.json`](examples/leads.json) — synthetic businesses covering the happy path and every failure mode
- [`examples/partners.json`](examples/partners.json) — four fictional audit firms with different coverage, capacity, and specialties
- [`examples/dnc.txt`](examples/dnc.txt) — suppression list (phones and emails, one per line)
- [`examples/email_meta.json`](examples/email_meta.json) — CAN-SPAM fields for the email channel

## Testing

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q
```

64 tests, heavy on the fail-closed edge cases: missing states, naive timestamps, absent suppression lists, Sunday bans, DST boundaries, capacity exhaustion, tie-break stability.

## Contributing

Issues and PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). The one hard rule: never weaken the fail-closed contract.

## Demo script

A short demo plan for launch screenshots and GIFs lives in [docs/DEMO.md](docs/DEMO.md).

## Star this repo if

- You build in this niche and want a small reference engine instead of a black-box demo.
- You want synthetic examples that run locally.
- You care about readable implementation details, not just screenshots.

Launch notes and topic suggestions live in [docs/LAUNCH_PACK.md](docs/LAUNCH_PACK.md).

## Repository health

This repo now includes GitHub issue templates, a PR checklist, Dependabot checks for GitHub Actions, and a public boundary checklist in [docs/REPO_HEALTH.md](docs/REPO_HEALTH.md).

## License

[MIT](LICENSE) © Denis Redzic
