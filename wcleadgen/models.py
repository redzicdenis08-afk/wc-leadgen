"""Core data models for wcleadgen.

Everything is a plain dataclass with a ``to_dict`` for JSON output and a
forgiving ``from_dict`` for ingesting CSV/JSON rows. No runtime dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


def _opt_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _opt_bool(value: Any) -> Optional[bool]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "y", "t"):
        return True
    if text in ("0", "false", "no", "n", "f"):
        return False
    return None


def _opt_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass
class Lead:
    """A small business considered for a workers'-comp premium-audit consult.

    Every field except ``lead_id`` is optional on purpose: real lead data is
    always incomplete, and the compliance engine treats missing data as a
    reason to block, never a reason to guess.
    """

    lead_id: str
    business_name: Optional[str] = None
    state: Optional[str] = None
    industry: Optional[str] = None
    employee_count: Optional[int] = None
    annual_payroll: Optional[int] = None
    years_in_business: Optional[int] = None
    wc_policy_active: Optional[bool] = None
    years_since_last_audit: Optional[int] = None  # None = never audited / unknown
    phone: Optional[str] = None
    email: Optional[str] = None
    sms_consent: Optional[bool] = None

    @classmethod
    def from_dict(cls, row: dict) -> "Lead":
        lead_id = _opt_str(row.get("lead_id") or row.get("id"))
        if not lead_id:
            raise ValueError("lead row is missing 'lead_id'")
        return cls(
            lead_id=lead_id,
            business_name=_opt_str(row.get("business_name") or row.get("company")),
            state=_opt_str(row.get("state")),
            industry=_opt_str(row.get("industry")),
            employee_count=_opt_int(row.get("employee_count") or row.get("employees")),
            annual_payroll=_opt_int(row.get("annual_payroll") or row.get("payroll")),
            years_in_business=_opt_int(row.get("years_in_business")),
            wc_policy_active=_opt_bool(row.get("wc_policy_active")),
            years_since_last_audit=_opt_int(row.get("years_since_last_audit")),
            phone=_opt_str(row.get("phone")),
            email=_opt_str(row.get("email")),
            sms_consent=_opt_bool(row.get("sms_consent")),
        )

    def to_dict(self) -> dict:
        return {
            "lead_id": self.lead_id,
            "business_name": self.business_name,
            "state": self.state,
            "industry": self.industry,
            "employee_count": self.employee_count,
            "annual_payroll": self.annual_payroll,
            "years_in_business": self.years_in_business,
            "wc_policy_active": self.wc_policy_active,
            "years_since_last_audit": self.years_since_last_audit,
            "phone": self.phone,
            "email": self.email,
            "sms_consent": self.sms_consent,
        }


@dataclass
class ScoreFactor:
    """One explainable component of a lead score."""

    name: str
    points: int
    max_points: int
    detail: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "points": self.points,
            "max_points": self.max_points,
            "detail": self.detail,
        }


@dataclass
class ScoreResult:
    lead_id: str
    score: int  # 0-100
    grade: str  # A / B / C / D
    qualified: bool
    factors: list = field(default_factory=list)  # list[ScoreFactor]

    def to_dict(self) -> dict:
        return {
            "lead_id": self.lead_id,
            "score": self.score,
            "grade": self.grade,
            "qualified": self.qualified,
            "factors": [f.to_dict() for f in self.factors],
        }


@dataclass
class ComplianceCheck:
    """One compliance gate. ``passed=False`` always carries a machine-readable
    ``reason`` code plus a human ``detail``."""

    name: str
    passed: bool
    reason: str  # "ok" when passed, machine-readable code otherwise
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "reason": self.reason,
            "detail": self.detail,
        }


@dataclass
class ComplianceResult:
    lead_id: str
    channel: str
    allowed: bool
    blocked_reasons: list = field(default_factory=list)  # list[str] reason codes
    checks: list = field(default_factory=list)  # list[ComplianceCheck]

    def to_dict(self) -> dict:
        return {
            "lead_id": self.lead_id,
            "channel": self.channel,
            "allowed": self.allowed,
            "blocked_reasons": list(self.blocked_reasons),
            "checks": [c.to_dict() for c in self.checks],
        }


@dataclass
class Partner:
    """An audit firm that receives qualified consults."""

    firm_id: str
    name: str
    states: list = field(default_factory=list)  # ["TX", "OK"] or ["US"] for nationwide
    specialties: list = field(default_factory=list)  # industries, lowercase
    capacity: int = 0  # max concurrent consults
    current_load: int = 0
    min_lead_score: int = 0

    @classmethod
    def from_dict(cls, row: dict) -> "Partner":
        firm_id = _opt_str(row.get("firm_id") or row.get("id"))
        if not firm_id:
            raise ValueError("partner row is missing 'firm_id'")
        return cls(
            firm_id=firm_id,
            name=_opt_str(row.get("name")) or firm_id,
            states=[str(s).strip().upper() for s in (row.get("states") or []) if str(s).strip()],
            specialties=[
                str(s).strip().lower() for s in (row.get("specialties") or []) if str(s).strip()
            ],
            capacity=_opt_int(row.get("capacity")) or 0,
            current_load=_opt_int(row.get("current_load")) or 0,
            min_lead_score=_opt_int(row.get("min_lead_score")) or 0,
        )

    @property
    def remaining_capacity(self) -> int:
        return max(0, self.capacity - self.current_load)

    def to_dict(self) -> dict:
        return {
            "firm_id": self.firm_id,
            "name": self.name,
            "states": list(self.states),
            "specialties": list(self.specialties),
            "capacity": self.capacity,
            "current_load": self.current_load,
            "min_lead_score": self.min_lead_score,
        }


@dataclass
class RoutingResult:
    lead_id: str
    matched: bool
    firm_id: Optional[str] = None
    firm_name: Optional[str] = None
    reason: str = ""
    candidates: list = field(default_factory=list)  # per-firm decision trace dicts

    def to_dict(self) -> dict:
        return {
            "lead_id": self.lead_id,
            "matched": self.matched,
            "firm_id": self.firm_id,
            "firm_name": self.firm_name,
            "reason": self.reason,
            "candidates": list(self.candidates),
        }


@dataclass
class AuditEvent:
    """One line in a pipeline's decision trail."""

    stage: str  # "score" | "compliance" | "route"
    decision: str  # e.g. "qualified", "blocked", "matched"
    detail: str = ""
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "decision": self.decision,
            "detail": self.detail,
            "data": dict(self.data),
        }


@dataclass
class PipelineResult:
    lead_id: str
    status: str  # "routed" | "rejected_low_score" | "blocked_compliance" | "no_partner"
    score: Optional[ScoreResult] = None
    compliance: Optional[ComplianceResult] = None
    routing: Optional[RoutingResult] = None
    audit_trail: list = field(default_factory=list)  # list[AuditEvent]

    def to_dict(self) -> dict:
        return {
            "lead_id": self.lead_id,
            "status": self.status,
            "score": self.score.to_dict() if self.score else None,
            "compliance": self.compliance.to_dict() if self.compliance else None,
            "routing": self.routing.to_dict() if self.routing else None,
            "audit_trail": [e.to_dict() for e in self.audit_trail],
        }
