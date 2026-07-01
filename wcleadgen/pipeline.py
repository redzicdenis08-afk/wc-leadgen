"""End-to-end pipeline: lead -> score -> compliance gate -> route.

Every stage appends an :class:`~wcleadgen.models.AuditEvent`, so a
:class:`~wcleadgen.models.PipelineResult` carries a complete, replayable
record of why each lead ended up where it did. The gate order is
deliberate: a lead that fails scoring never even reaches the compliance
engine, and a compliance block always halts before routing.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from .compliance import SuppressionList, check_compliance
from .models import AuditEvent, Lead, PipelineResult
from .routing import route_lead
from .scoring import score_lead

STATUS_ROUTED = "routed"
STATUS_REJECTED = "rejected_low_score"
STATUS_BLOCKED = "blocked_compliance"
STATUS_NO_PARTNER = "no_partner"


def run_pipeline(
    lead: Lead,
    partners: list,
    *,
    channel: str = "call",
    when: Optional[datetime] = None,
    suppression: Optional[SuppressionList] = None,
    email_meta: Optional[dict] = None,
) -> PipelineResult:
    """Process one lead through score -> compliance -> route."""
    trail = []

    # Stage 1: score
    score = score_lead(lead)
    trail.append(AuditEvent(
        stage="score",
        decision="qualified" if score.qualified else "rejected",
        detail=f"score={score.score} grade={score.grade}",
        data={"score": score.score, "grade": score.grade},
    ))
    if not score.qualified:
        return PipelineResult(lead.lead_id, STATUS_REJECTED, score=score, audit_trail=trail)

    # Stage 2: compliance gate (fail-closed)
    compliance = check_compliance(
        lead, channel, when=when, suppression=suppression, email_meta=email_meta
    )
    trail.append(AuditEvent(
        stage="compliance",
        decision="allowed" if compliance.allowed else "blocked",
        detail=", ".join(compliance.blocked_reasons) or "all checks passed",
        data={"channel": channel, "blocked_reasons": list(compliance.blocked_reasons)},
    ))
    if not compliance.allowed:
        return PipelineResult(
            lead.lead_id, STATUS_BLOCKED, score=score, compliance=compliance, audit_trail=trail
        )

    # Stage 3: route
    routing = route_lead(lead, score, partners)
    trail.append(AuditEvent(
        stage="route",
        decision="matched" if routing.matched else "unmatched",
        detail=routing.firm_id or routing.reason,
        data={"firm_id": routing.firm_id, "reason": routing.reason},
    ))
    status = STATUS_ROUTED if routing.matched else STATUS_NO_PARTNER
    return PipelineResult(
        lead.lead_id, status, score=score, compliance=compliance, routing=routing,
        audit_trail=trail,
    )


def run_batch(
    leads: list,
    partners: list,
    *,
    channel: str = "call",
    when: Optional[datetime] = None,
    suppression: Optional[SuppressionList] = None,
    email_meta: Optional[dict] = None,
    update_load: bool = True,
) -> list:
    """Run a batch of leads through the pipeline in order.

    When ``update_load`` is true, each successful match increments the
    partner's ``current_load`` so capacity is respected across the batch.
    """
    by_id = {p.firm_id: p for p in partners}
    results = []
    for lead in leads:
        result = run_pipeline(
            lead, partners, channel=channel, when=when,
            suppression=suppression, email_meta=email_meta,
        )
        if update_load and result.routing and result.routing.matched:
            matched = by_id.get(result.routing.firm_id)
            if matched is not None:
                matched.current_load += 1
        results.append(result)
    return results
