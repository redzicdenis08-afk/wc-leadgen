"""Scoring tests: explainability, bands, and qualification rules."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wcleadgen import Lead, score_lead  # noqa: E402
from wcleadgen.scoring import QUALIFICATION_THRESHOLD  # noqa: E402


def make_lead(**kwargs) -> Lead:
    base = dict(
        lead_id="lead-t1",
        business_name="Acme Roofing LLC",
        state="TX",
        industry="roofing",
        employee_count=34,
        annual_payroll=2_400_000,
        years_in_business=12,
        wc_policy_active=True,
        years_since_last_audit=None,
        phone="+1-555-010-4477",
        email="owner@acme-roofing.example.com",
    )
    base.update(kwargs)
    return Lead(**base)


def test_prime_lead_scores_high_and_qualifies():
    r = score_lead(make_lead())
    assert r.score >= 90
    assert r.grade == "A"
    assert r.qualified


def test_score_is_bounded_0_to_100():
    r = score_lead(make_lead())
    assert 0 <= r.score <= 100
    empty = score_lead(Lead(lead_id="lead-empty"))
    assert 0 <= empty.score <= 100


def test_every_factor_has_breakdown():
    r = score_lead(make_lead())
    names = {f.name for f in r.factors}
    assert names == {
        "industry_risk", "employee_count", "payroll_band", "audit_history", "years_in_business",
    }
    for f in r.factors:
        assert 0 <= f.points <= f.max_points
        assert f.detail  # every factor explains itself


def test_factor_points_sum_to_score():
    r = score_lead(make_lead())
    assert r.score == sum(f.points for f in r.factors)


def test_no_wc_policy_never_qualifies():
    """No active policy = no premium to audit, no matter how good it looks."""
    r = score_lead(make_lead(wc_policy_active=False))
    assert not r.qualified


def test_unknown_everything_scores_near_zero():
    r = score_lead(Lead(lead_id="lead-mystery"))
    assert r.score < QUALIFICATION_THRESHOLD
    assert not r.qualified
    assert r.grade == "D"


def test_never_audited_beats_recently_audited():
    never = score_lead(make_lead(years_since_last_audit=None))
    recent = score_lead(make_lead(years_since_last_audit=0))
    assert never.score > recent.score


def test_high_risk_industry_beats_office():
    roofing = score_lead(make_lead(industry="roofing"))
    office = score_lead(make_lead(industry="office"))
    assert roofing.score > office.score


def test_industry_substring_matching():
    r = score_lead(make_lead(industry="Roofing Contractor"))
    factor = next(f for f in r.factors if f.name == "industry_risk")
    assert factor.points == 30


def test_unlisted_industry_gets_floor_not_zero():
    r = score_lead(make_lead(industry="alpaca grooming"))
    factor = next(f for f in r.factors if f.name == "industry_risk")
    assert factor.points == 5


def test_employee_sweet_spot():
    tiny = score_lead(make_lead(employee_count=1))
    prime = score_lead(make_lead(employee_count=50))
    enterprise = score_lead(make_lead(employee_count=5000))
    assert prime.score > tiny.score
    assert prime.score > enterprise.score


def test_result_serializes_to_dict():
    d = score_lead(make_lead()).to_dict()
    assert d["lead_id"] == "lead-t1"
    assert isinstance(d["factors"], list)
    assert all("points" in f and "detail" in f for f in d["factors"])
