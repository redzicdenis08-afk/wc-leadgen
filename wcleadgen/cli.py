"""Command-line interface.

    wcleadgen score  leads.csv                 # score leads, factor breakdown
    wcleadgen check  leads.json --channel call --when 2026-07-06T18:30:00+00:00
    wcleadgen route  leads.csv --partners partners.json
    wcleadgen run    leads.csv --partners partners.json --dnc dnc.txt

Input is JSON (a list of lead objects, or one object) or CSV with a header
row. Add ``--json`` to any subcommand for machine-readable output.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

from .compliance import SuppressionList, check_compliance
from .models import Lead, Partner
from .pipeline import run_batch
from .routing import route_lead
from .scoring import score_lead


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------
def load_leads(path: str) -> list:
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"error: input file not found: {path}")
    if p.suffix.lower() == ".csv":
        with p.open(newline="", encoding="utf-8-sig") as fh:
            return [Lead.from_dict(row) for row in csv.DictReader(fh)]
    data = json.loads(p.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else [data]
    return [Lead.from_dict(row) for row in rows]


def load_partners(path: str) -> list:
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"error: partners file not found: {path}")
    data = json.loads(p.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else [data]
    return [Partner.from_dict(row) for row in rows]


def load_suppression(path: str) -> SuppressionList:
    """One entry per line; emails and phones auto-detected by '@'."""
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"error: suppression file not found: {path}")
    phones, emails = set(), set()
    for line in p.read_text(encoding="utf-8").splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        (emails if "@" in entry else phones).add(entry)
    return SuppressionList(phones=phones, emails=emails)


def parse_when(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise SystemExit(f"error: --when must be ISO 8601 (got {value!r})")


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------
def cmd_score(args: argparse.Namespace) -> int:
    leads = load_leads(args.input)
    results = [score_lead(lead) for lead in leads]
    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
        return 0
    print(f"{'LEAD':<14} {'SCORE':>5}  {'GRADE':<5} {'QUALIFIED':<9}  TOP FACTORS")
    print("-" * 78)
    for r in results:
        top = sorted(r.factors, key=lambda f: -f.points)[:2]
        factors = ", ".join(f"{f.name}={f.points}" for f in top)
        print(f"{r.lead_id:<14} {r.score:>5}  {r.grade:<5} {str(r.qualified).lower():<9}  {factors}")
    qualified = sum(1 for r in results if r.qualified)
    print("-" * 78)
    print(f"{len(results)} lead(s) | {qualified} qualified")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    leads = load_leads(args.input)
    suppression = load_suppression(args.dnc) if args.dnc else SuppressionList()
    when = parse_when(args.when) if args.when else None
    email_meta = json.loads(Path(args.email_meta).read_text(encoding="utf-8")) if args.email_meta else None
    results = [
        check_compliance(lead, args.channel, when=when, suppression=suppression, email_meta=email_meta)
        for lead in leads
    ]
    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        print(f"{'LEAD':<14} {'CHANNEL':<8} {'VERDICT':<8} REASONS")
        print("-" * 70)
        for r in results:
            verdict = "ALLOWED" if r.allowed else "BLOCKED"
            reasons = ", ".join(r.blocked_reasons) or "-"
            print(f"{r.lead_id:<14} {r.channel:<8} {verdict:<8} {reasons}")
        blocked = sum(1 for r in results if not r.allowed)
        print("-" * 70)
        print(f"{len(results)} lead(s) | {blocked} blocked (fail-closed)")
    return 0 if all(r.allowed for r in results) else 1


def cmd_route(args: argparse.Namespace) -> int:
    leads = load_leads(args.input)
    partners = load_partners(args.partners)
    results = [route_lead(lead, score_lead(lead), partners) for lead in leads]
    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
        return 0
    print(f"{'LEAD':<14} {'MATCHED':<8} {'FIRM':<22} REASON")
    print("-" * 70)
    for r in results:
        firm = r.firm_name or "-"
        print(f"{r.lead_id:<14} {str(r.matched).lower():<8} {firm:<22} {r.reason}")
    matched = sum(1 for r in results if r.matched)
    print("-" * 70)
    print(f"{len(results)} lead(s) | {matched} routed")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    leads = load_leads(args.input)
    partners = load_partners(args.partners)
    suppression = load_suppression(args.dnc) if args.dnc else SuppressionList()
    when = parse_when(args.when) if args.when else None
    email_meta = json.loads(Path(args.email_meta).read_text(encoding="utf-8")) if args.email_meta else None
    results = run_batch(
        leads, partners, channel=args.channel, when=when,
        suppression=suppression, email_meta=email_meta,
    )
    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
        return 0
    print(f"{'LEAD':<14} {'SCORE':>5}  {'STATUS':<20} DETAIL")
    print("-" * 74)
    for r in results:
        score = r.score.score if r.score else "-"
        if r.status == "routed":
            detail = f"-> {r.routing.firm_name}"
        elif r.status == "blocked_compliance":
            detail = ", ".join(r.compliance.blocked_reasons)
        elif r.status == "no_partner":
            detail = r.routing.reason
        else:
            detail = f"not qualified (score {r.score.score}, grade {r.score.grade})"
        print(f"{r.lead_id:<14} {score:>5}  {r.status:<20} {detail}")
    routed = sum(1 for r in results if r.status == "routed")
    blocked = sum(1 for r in results if r.status == "blocked_compliance")
    print("-" * 74)
    print(f"{len(results)} lead(s) | {routed} routed | {blocked} blocked by compliance")
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wcleadgen",
        description="Score, compliance-gate, and route workers'-comp premium-audit leads.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("input", help="leads file (.json or .csv)")
        p.add_argument("--json", action="store_true", help="machine-readable JSON output")

    p_score = sub.add_parser("score", help="score leads for premium-audit fit")
    add_common(p_score)
    p_score.set_defaults(func=cmd_score)

    p_check = sub.add_parser("check", help="run the fail-closed compliance gate")
    add_common(p_check)
    p_check.add_argument("--channel", default="call", choices=["call", "sms", "email"])
    p_check.add_argument("--when", help="outreach time, ISO 8601 with timezone")
    p_check.add_argument("--dnc", help="suppression file (one phone/email per line)")
    p_check.add_argument("--email-meta", help="JSON file with CAN-SPAM fields for email channel")
    p_check.set_defaults(func=cmd_check)

    p_route = sub.add_parser("route", help="match qualified leads to partner firms")
    add_common(p_route)
    p_route.add_argument("--partners", required=True, help="partner firms JSON file")
    p_route.set_defaults(func=cmd_route)

    p_run = sub.add_parser("run", help="full pipeline: score -> compliance -> route")
    add_common(p_run)
    p_run.add_argument("--partners", required=True, help="partner firms JSON file")
    p_run.add_argument("--channel", default="call", choices=["call", "sms", "email"])
    p_run.add_argument("--when", help="outreach time, ISO 8601 with timezone")
    p_run.add_argument("--dnc", help="suppression file (one phone/email per line)")
    p_run.add_argument("--email-meta", help="JSON file with CAN-SPAM fields for email channel")
    p_run.set_defaults(func=cmd_run)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
