"""Pipeline tests: gate ordering, audit trail, batch capacity accounting."""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wcleadgen import Lead, Partner, SuppressionList, run_batch, run_pipeline  # noqa: E402

SAFE_WHEN = datetime(2026, 7, 8, 18, 0, tzinfo=timezone.utc)  # Wed 13:00 CDT
EMPTY = SuppressionList()


def make_lead(lead_id="lead-p1", **kwargs) -> Lead:
    base = dict(
        lead_id=lead_id,
        business_name="Acme Roofing LLC",
        state="TX",
        industry="roofing",
        employee_count=34,
        annual_payroll=2_400_000,
        years_in_business=12,
        wc_policy_active=True,
        phone="+1-555-010-4477",
        email="owner@acme-roofing.example.com",
    )
    base.update(kwargs)
    return Lead(**base)


def make_partner(**kwargs) -> Partner:
    base = dict(
        firm_id="firm-a", name="Alpha Audit", states=["TX"], specialties=["roofing"],
        capacity=5, current_load=0, min_lead_score=0,
    )
    base.update(kwargs)
    return Partner(**base)


def test_good_lead_routes_end_to_end():
    r = run_pipeline(make_lead(), [make_partner()], when=SAFE_WHEN, suppression=EMPTY)
    assert r.status == "routed"
    assert r.routing.firm_id == "firm-a"
    assert [e.stage for e in r.audit_trail] == ["score", "compliance", "route"]


def test_low_score_lead_stops_before_compliance():
    weak = make_lead(industry="office", employee_count=1, annual_payroll=50_000,
                     years_in_business=0, years_since_last_audit=0)
    r = run_pipeline(weak, [make_partner()], when=SAFE_WHEN, suppression=EMPTY)
    assert r.status == "rejected_low_score"
    assert r.compliance is None  # never reached the gate
    assert [e.stage for e in r.audit_trail] == ["score"]


def test_compliance_block_stops_before_routing():
    dnc = SuppressionList(phones={"+1-555-010-4477"})
    r = run_pipeline(make_lead(), [make_partner()], when=SAFE_WHEN, suppression=dnc)
    assert r.status == "blocked_compliance"
    assert "dnc_listed" in r.compliance.blocked_reasons
    assert r.routing is None
    assert [e.stage for e in r.audit_trail] == ["score", "compliance"]


def test_no_partner_status_when_nothing_matches():
    r = run_pipeline(make_lead(), [make_partner(states=["CA"])], when=SAFE_WHEN, suppression=EMPTY)
    assert r.status == "no_partner"
    assert not r.routing.matched


def test_audit_trail_records_decisions_and_data():
    r = run_pipeline(make_lead(), [make_partner()], when=SAFE_WHEN, suppression=EMPTY)
    score_event = r.audit_trail[0]
    assert score_event.decision == "qualified"
    assert score_event.data["score"] == r.score.score
    route_event = r.audit_trail[-1]
    assert route_event.data["firm_id"] == "firm-a"


def test_batch_consumes_partner_capacity():
    partner = make_partner(capacity=2, current_load=0)
    leads = [make_lead(f"lead-{i}") for i in range(3)]
    results = run_batch(leads, [partner], when=SAFE_WHEN, suppression=EMPTY)
    statuses = [r.status for r in results]
    assert statuses == ["routed", "routed", "no_partner"]
    assert partner.current_load == 2


def test_pipeline_result_serializes():
    r = run_pipeline(make_lead(), [make_partner()], when=SAFE_WHEN, suppression=EMPTY)
    d = r.to_dict()
    assert d["status"] == "routed"
    assert len(d["audit_trail"]) == 3
    assert d["score"]["qualified"] is True
