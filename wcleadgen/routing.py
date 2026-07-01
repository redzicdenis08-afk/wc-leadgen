"""Consult routing: match a qualified lead to a partner audit firm.

Eligibility filters (all must pass):

1. state coverage — firm covers the lead's state, or is nationwide (``US``)
2. capacity — firm has remaining consult slots
3. score floor — lead score meets the firm's ``min_lead_score``

Ranking among eligible firms is deterministic:

1. specialty match (firm lists the lead's industry) beats no match
2. more remaining capacity wins (spreads load)
3. fewer covered states wins (prefer the more local/specialized firm)
4. ``firm_id`` ascending — the final, total tie-break

The full decision trace for every candidate firm is returned so routing
decisions are auditable after the fact.
"""
from __future__ import annotations

from typing import Optional

from .models import Lead, Partner, RoutingResult, ScoreResult


def _industry_matches(lead_industry: Optional[str], specialties: list) -> bool:
    if not lead_industry or not specialties:
        return False
    key = lead_industry.strip().lower()
    return any(s == key or s in key for s in specialties)


def _covers_state(partner: Partner, state: Optional[str]) -> bool:
    if not state:
        return False
    state = state.strip().upper()
    return "US" in partner.states or state in partner.states


def route_lead(lead: Lead, score: ScoreResult, partners: list) -> RoutingResult:
    """Pick the best partner firm for a scored lead. Deterministic.

    Fail-closed here too: a lead with no state can never match (state
    coverage cannot be verified), and an unqualified score routes nowhere.
    """
    if not score.qualified:
        return RoutingResult(
            lead_id=lead.lead_id,
            matched=False,
            reason="lead_not_qualified",
            candidates=[],
        )

    candidates = []
    eligible = []
    for p in sorted(partners, key=lambda x: x.firm_id):
        trace = {"firm_id": p.firm_id, "eligible": False, "reasons": []}
        if not _covers_state(p, lead.state):
            trace["reasons"].append("state_not_covered")
        if p.remaining_capacity <= 0:
            trace["reasons"].append("no_capacity")
        if score.score < p.min_lead_score:
            trace["reasons"].append("below_score_floor")
        if not trace["reasons"]:
            trace["eligible"] = True
            trace["specialty_match"] = _industry_matches(lead.industry, p.specialties)
            trace["remaining_capacity"] = p.remaining_capacity
            eligible.append((p, trace))
        candidates.append(trace)

    if not eligible:
        return RoutingResult(
            lead_id=lead.lead_id,
            matched=False,
            reason="no_eligible_partner",
            candidates=candidates,
        )

    def rank_key(item):
        p, trace = item
        return (
            0 if trace["specialty_match"] else 1,  # specialty match first
            -p.remaining_capacity,                 # then most headroom
            len(p.states),                         # then most specialized coverage
            p.firm_id,                             # total, deterministic tie-break
        )

    best, best_trace = min(eligible, key=rank_key)
    best_trace["selected"] = True
    return RoutingResult(
        lead_id=lead.lead_id,
        matched=True,
        firm_id=best.firm_id,
        firm_name=best.name,
        reason="specialty_match" if best_trace["specialty_match"] else "coverage_match",
        candidates=candidates,
    )
