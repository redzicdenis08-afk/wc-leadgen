"""Routing tests: coverage, capacity, specialty, deterministic tie-breaks."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wcleadgen import Lead, Partner, route_lead, score_lead  # noqa: E402
from wcleadgen.models import ScoreResult  # noqa: E402


def make_lead(**kwargs) -> Lead:
    base = dict(
        lead_id="lead-r1",
        business_name="Acme Roofing LLC",
        state="TX",
        industry="roofing",
        employee_count=34,
        annual_payroll=2_400_000,
        years_in_business=12,
        wc_policy_active=True,
    )
    base.update(kwargs)
    return Lead(**base)


def make_partner(firm_id="firm-a", **kwargs) -> Partner:
    base = dict(
        firm_id=firm_id,
        name=firm_id.title(),
        states=["TX"],
        specialties=[],
        capacity=5,
        current_load=0,
        min_lead_score=0,
    )
    base.update(kwargs)
    return Partner(**base)


def qualified_score(lead: Lead) -> ScoreResult:
    score = score_lead(lead)
    assert score.qualified, "test fixture must be a qualified lead"
    return score


def test_routes_to_state_covered_partner():
    lead = make_lead()
    r = route_lead(lead, qualified_score(lead), [make_partner("firm-a", states=["TX"])])
    assert r.matched and r.firm_id == "firm-a"


def test_nationwide_wildcard_covers_any_state():
    lead = make_lead(state="NH")
    r = route_lead(lead, qualified_score(lead), [make_partner("firm-us", states=["US"])])
    assert r.matched and r.firm_id == "firm-us"


def test_unqualified_lead_never_routes():
    lead = make_lead(wc_policy_active=False)
    score = score_lead(lead)
    r = route_lead(lead, score, [make_partner()])
    assert not r.matched
    assert r.reason == "lead_not_qualified"


def test_no_state_never_routes():
    lead = make_lead(state=None)
    r = route_lead(lead, qualified_score(lead), [make_partner(states=["TX", "US"])])
    # "US" wildcard still requires a known lead state — coverage is unprovable.
    assert not r.matched


def test_full_capacity_partner_skipped():
    lead = make_lead()
    full = make_partner("firm-full", capacity=3, current_load=3)
    open_firm = make_partner("firm-open", capacity=3, current_load=0)
    r = route_lead(lead, qualified_score(lead), [full, open_firm])
    assert r.firm_id == "firm-open"
    full_trace = next(c for c in r.candidates if c["firm_id"] == "firm-full")
    assert "no_capacity" in full_trace["reasons"]


def test_score_floor_respected():
    lead = make_lead()
    score = qualified_score(lead)
    picky = make_partner("firm-picky", min_lead_score=score.score + 1)
    r = route_lead(lead, score, [picky])
    assert not r.matched
    assert r.reason == "no_eligible_partner"


def test_specialty_match_beats_more_capacity():
    lead = make_lead(industry="roofing")
    generalist = make_partner("firm-big", capacity=100, current_load=0)
    specialist = make_partner("firm-roof", capacity=2, current_load=0, specialties=["roofing"])
    r = route_lead(lead, qualified_score(lead), [generalist, specialist])
    assert r.firm_id == "firm-roof"
    assert r.reason == "specialty_match"


def test_capacity_breaks_ties_between_equals():
    lead = make_lead()
    a = make_partner("firm-a", capacity=5, current_load=4)  # 1 slot left
    b = make_partner("firm-b", capacity=5, current_load=1)  # 4 slots left
    r = route_lead(lead, qualified_score(lead), [a, b])
    assert r.firm_id == "firm-b"


def test_firm_id_is_final_deterministic_tiebreak():
    lead = make_lead()
    twins = [
        make_partner("firm-zeta"),
        make_partner("firm-alpha"),
    ]
    r1 = route_lead(lead, qualified_score(lead), twins)
    r2 = route_lead(lead, qualified_score(lead), list(reversed(twins)))
    assert r1.firm_id == r2.firm_id == "firm-alpha"


def test_candidate_trace_covers_every_partner():
    lead = make_lead()
    partners = [make_partner("firm-a"), make_partner("firm-b", states=["CA"])]
    r = route_lead(lead, qualified_score(lead), partners)
    assert {c["firm_id"] for c in r.candidates} == {"firm-a", "firm-b"}
    losing = next(c for c in r.candidates if c["firm_id"] == "firm-b")
    assert "state_not_covered" in losing["reasons"]
