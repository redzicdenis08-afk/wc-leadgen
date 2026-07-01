"""Explainable lead scoring for workers'-comp premium-audit fit.

Every score decomposes into named factors so an operator (or a partner firm)
can see exactly *why* a lead scored what it did. The whole model is a small
table of weights — deliberately simple enough to read, audit, and tune.

Factor budget (sums to 100):

    industry_risk       0-30   high-mod industries misclassify most often
    employee_count      0-25   the 5-100 employee band is the sweet spot
    payroll_band        0-20   bigger payroll = bigger potential premium error
    audit_history       0-15   never/rarely audited = most recoverable premium
    years_in_business   0-10   established firms have history worth auditing
"""
from __future__ import annotations

from typing import Optional

from .models import Lead, ScoreFactor, ScoreResult

# Industries where workers'-comp class-code misclassification is common and
# experience-mod errors are expensive. Points reflect premium-audit upside.
INDUSTRY_RISK_POINTS = {
    "roofing": 30,
    "construction": 30,
    "framing": 30,
    "demolition": 30,
    "trucking": 28,
    "logging": 28,
    "excavation": 28,
    "hvac": 25,
    "plumbing": 25,
    "electrical": 25,
    "landscaping": 25,
    "manufacturing": 22,
    "staffing": 22,
    "concrete": 22,
    "painting": 20,
    "restaurant": 15,
    "janitorial": 15,
    "warehousing": 15,
    "auto repair": 12,
    "retail": 8,
    "office": 4,
}

QUALIFICATION_THRESHOLD = 60


def _score_industry(industry: Optional[str]) -> ScoreFactor:
    if not industry:
        return ScoreFactor("industry_risk", 0, 30, "industry unknown — no points")
    key = industry.strip().lower()
    points = INDUSTRY_RISK_POINTS.get(key)
    if points is None:
        # Substring fallback: "roofing contractor" still counts as roofing.
        for name, pts in INDUSTRY_RISK_POINTS.items():
            if name in key:
                points = pts
                key = name
                break
    if points is None:
        return ScoreFactor("industry_risk", 5, 30, f"'{industry}' not in risk table — floor score")
    return ScoreFactor("industry_risk", points, 30, f"'{key}' risk class = {points} pts")


def _score_employees(count: Optional[int]) -> ScoreFactor:
    if count is None:
        return ScoreFactor("employee_count", 0, 25, "employee count unknown — no points")
    if count < 3:
        return ScoreFactor("employee_count", 2, 25, f"{count} employees — too small to audit")
    if count <= 4:
        return ScoreFactor("employee_count", 8, 25, f"{count} employees — marginal")
    if count <= 20:
        return ScoreFactor("employee_count", 20, 25, f"{count} employees — solid audit target")
    if count <= 100:
        return ScoreFactor("employee_count", 25, 25, f"{count} employees — prime band (5-100)")
    if count <= 500:
        return ScoreFactor("employee_count", 15, 25, f"{count} employees — likely has a broker")
    return ScoreFactor("employee_count", 5, 25, f"{count} employees — enterprise, wrong motion")


def _score_payroll(payroll: Optional[int]) -> ScoreFactor:
    if payroll is None:
        return ScoreFactor("payroll_band", 0, 20, "annual payroll unknown — no points")
    if payroll < 100_000:
        return ScoreFactor("payroll_band", 2, 20, f"${payroll:,} payroll — premium too small")
    if payroll < 500_000:
        return ScoreFactor("payroll_band", 10, 20, f"${payroll:,} payroll — modest premium")
    if payroll < 5_000_000:
        return ScoreFactor("payroll_band", 20, 20, f"${payroll:,} payroll — meaningful premium")
    return ScoreFactor("payroll_band", 15, 20, f"${payroll:,} payroll — large, longer sales cycle")


def _score_audit_history(lead: Lead) -> ScoreFactor:
    if lead.wc_policy_active is False:
        return ScoreFactor("audit_history", 0, 15, "no active WC policy — nothing to audit")
    if lead.wc_policy_active is None:
        return ScoreFactor("audit_history", 0, 15, "WC policy status unknown — no points")
    years = lead.years_since_last_audit
    if years is None:
        return ScoreFactor("audit_history", 15, 15, "never audited — max recoverable premium")
    if years >= 3:
        return ScoreFactor("audit_history", 12, 15, f"last audit {years}y ago — likely drift")
    if years >= 1:
        return ScoreFactor("audit_history", 6, 15, f"last audit {years}y ago — some drift")
    return ScoreFactor("audit_history", 2, 15, "audited within the last year — little upside")


def _score_tenure(years: Optional[int]) -> ScoreFactor:
    if years is None:
        return ScoreFactor("years_in_business", 0, 10, "tenure unknown — no points")
    if years < 1:
        return ScoreFactor("years_in_business", 0, 10, "under 1 year — no premium history")
    if years < 3:
        return ScoreFactor("years_in_business", 4, 10, f"{years}y in business — thin history")
    if years < 10:
        return ScoreFactor("years_in_business", 8, 10, f"{years}y in business — solid history")
    return ScoreFactor("years_in_business", 10, 10, f"{years}y in business — deep history")


def _grade(score: int) -> str:
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    return "D"


def score_lead(lead: Lead) -> ScoreResult:
    """Score a lead 0-100 for premium-audit fit, with a factor breakdown.

    A lead only *qualifies* when it clears :data:`QUALIFICATION_THRESHOLD`
    **and** is not known to lack an active WC policy — no policy means there
    is no premium to audit, regardless of how attractive the business looks.
    """
    factors = [
        _score_industry(lead.industry),
        _score_employees(lead.employee_count),
        _score_payroll(lead.annual_payroll),
        _score_audit_history(lead),
        _score_tenure(lead.years_in_business),
    ]
    total = sum(f.points for f in factors)
    score = max(0, min(100, total))
    qualified = score >= QUALIFICATION_THRESHOLD and lead.wc_policy_active is not False
    return ScoreResult(
        lead_id=lead.lead_id,
        score=score,
        grade=_grade(score),
        qualified=qualified,
        factors=factors,
    )
