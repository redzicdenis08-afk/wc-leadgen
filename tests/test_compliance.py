"""Compliance tests — the fail-closed contract is the whole point."""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wcleadgen import Lead, SuppressionList, check_compliance  # noqa: E402
from wcleadgen.compliance import local_time_for_state, normalize_phone  # noqa: E402

# A safe weekday afternoon: Wed 2026-07-08 18:00 UTC = 13:00 CDT in Texas.
SAFE_WHEN = datetime(2026, 7, 8, 18, 0, tzinfo=timezone.utc)
EMPTY_SUPPRESSION = SuppressionList()

GOOD_META = {
    "from_address": "audits@example.com",
    "postal_address": "100 Example Plaza, Austin, TX 78701",
    "unsubscribe_url": "https://example.com/unsubscribe",
    "subject": "Premium audit review",
}


def make_lead(**kwargs) -> Lead:
    base = dict(
        lead_id="lead-c1",
        business_name="Acme Roofing LLC",
        state="TX",
        industry="roofing",
        phone="+1-555-010-4477",
        email="owner@acme-roofing.example.com",
        sms_consent=True,
    )
    base.update(kwargs)
    return Lead(**base)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------
def test_clean_lead_allowed_to_call():
    r = check_compliance(make_lead(), "call", when=SAFE_WHEN, suppression=EMPTY_SUPPRESSION)
    assert r.allowed
    assert r.blocked_reasons == []
    assert all(c.passed for c in r.checks)


def test_email_allowed_with_full_canspam_meta():
    r = check_compliance(
        make_lead(), "email", suppression=EMPTY_SUPPRESSION, email_meta=GOOD_META
    )
    assert r.allowed


# ---------------------------------------------------------------------------
# Fail-closed: missing data always blocks
# ---------------------------------------------------------------------------
def test_missing_state_blocks():
    r = check_compliance(make_lead(state=None), "call", when=SAFE_WHEN, suppression=EMPTY_SUPPRESSION)
    assert not r.allowed
    assert "missing_state" in r.blocked_reasons


def test_unknown_state_blocks():
    r = check_compliance(make_lead(state="ZZ"), "call", when=SAFE_WHEN, suppression=EMPTY_SUPPRESSION)
    assert not r.allowed
    assert "unknown_state" in r.blocked_reasons


def test_monopolistic_state_blocks():
    r = check_compliance(make_lead(state="OH"), "call", when=SAFE_WHEN, suppression=EMPTY_SUPPRESSION)
    assert not r.allowed
    assert "state_monopolistic" in r.blocked_reasons


def test_no_suppression_list_blocks():
    """No DNC list means we cannot prove the lead is callable."""
    r = check_compliance(make_lead(), "call", when=SAFE_WHEN, suppression=None)
    assert not r.allowed
    assert "no_suppression_list" in r.blocked_reasons


def test_missing_phone_blocks_call():
    r = check_compliance(make_lead(phone=None), "call", when=SAFE_WHEN, suppression=EMPTY_SUPPRESSION)
    assert not r.allowed
    assert "missing_phone" in r.blocked_reasons


def test_missing_timestamp_blocks_call():
    r = check_compliance(make_lead(), "call", when=None, suppression=EMPTY_SUPPRESSION)
    assert not r.allowed
    assert "missing_timestamp" in r.blocked_reasons


def test_naive_timestamp_blocks_call():
    naive = datetime(2026, 7, 8, 13, 0)  # no tzinfo
    r = check_compliance(make_lead(), "call", when=naive, suppression=EMPTY_SUPPRESSION)
    assert not r.allowed
    assert "naive_timestamp" in r.blocked_reasons


def test_unknown_channel_blocks():
    r = check_compliance(make_lead(), "carrier_pigeon", when=SAFE_WHEN, suppression=EMPTY_SUPPRESSION)
    assert not r.allowed
    assert "unknown_channel" in r.blocked_reasons


def test_email_without_meta_blocks():
    r = check_compliance(make_lead(), "email", suppression=EMPTY_SUPPRESSION, email_meta=None)
    assert not r.allowed
    assert "missing_email_metadata" in r.blocked_reasons


def test_canspam_missing_fields_block():
    meta = dict(GOOD_META)
    meta.pop("postal_address")
    meta["unsubscribe_url"] = "  "
    r = check_compliance(make_lead(), "email", suppression=EMPTY_SUPPRESSION, email_meta=meta)
    assert not r.allowed
    check = next(c for c in r.checks if c.name == "can_spam")
    assert "postal_address" in check.detail
    assert "unsubscribe_url" in check.detail


def test_sms_without_consent_record_blocks():
    r = check_compliance(
        make_lead(sms_consent=None), "sms", when=SAFE_WHEN, suppression=EMPTY_SUPPRESSION
    )
    assert not r.allowed
    assert "no_consent_record" in r.blocked_reasons


def test_sms_with_revoked_consent_blocks():
    r = check_compliance(
        make_lead(sms_consent=False), "sms", when=SAFE_WHEN, suppression=EMPTY_SUPPRESSION
    )
    assert not r.allowed
    assert "consent_revoked" in r.blocked_reasons


# ---------------------------------------------------------------------------
# DNC / suppression
# ---------------------------------------------------------------------------
def test_dnc_phone_blocks_regardless_of_format():
    suppression = SuppressionList(phones={"+1 (555) 010-4477"})
    r = check_compliance(make_lead(phone="15550104477"), "call", when=SAFE_WHEN, suppression=suppression)
    assert not r.allowed
    assert "dnc_listed" in r.blocked_reasons


def test_suppressed_email_blocks():
    suppression = SuppressionList(emails={"OWNER@acme-roofing.example.com"})
    r = check_compliance(make_lead(), "email", suppression=suppression, email_meta=GOOD_META)
    assert not r.allowed
    assert "email_suppressed" in r.blocked_reasons


def test_normalize_phone():
    assert normalize_phone("+1 (555) 010-4477") == "5550104477"
    assert normalize_phone("555-010-4477") == "5550104477"
    assert normalize_phone(None) == ""


# ---------------------------------------------------------------------------
# Calling windows: quiet hours, Sundays, holidays, timezones
# ---------------------------------------------------------------------------
def test_too_early_blocks():
    when = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)  # 07:00 CDT in TX
    r = check_compliance(make_lead(), "call", when=when, suppression=EMPTY_SUPPRESSION)
    assert not r.allowed
    assert "too_early" in r.blocked_reasons


def test_too_late_blocks():
    when = datetime(2026, 7, 9, 2, 0, tzinfo=timezone.utc)  # 21:00 CDT Jul 8 in TX
    r = check_compliance(make_lead(), "call", when=when, suppression=EMPTY_SUPPRESSION)
    assert not r.allowed
    assert "too_late" in r.blocked_reasons


def test_texas_sunday_ban():
    sunday = datetime(2026, 7, 12, 18, 0, tzinfo=timezone.utc)  # Sunday 13:00 CDT
    r = check_compliance(make_lead(state="TX"), "call", when=sunday, suppression=EMPTY_SUPPRESSION)
    assert not r.allowed
    assert "state_no_sunday" in r.blocked_reasons


def test_california_sunday_allowed():
    sunday = datetime(2026, 7, 12, 20, 0, tzinfo=timezone.utc)  # Sunday 13:00 PDT
    r = check_compliance(make_lead(state="CA"), "call", when=sunday, suppression=EMPTY_SUPPRESSION)
    assert r.allowed


def test_federal_holiday_blocks():
    christmas = datetime(2026, 12, 25, 18, 0, tzinfo=timezone.utc)
    r = check_compliance(make_lead(), "call", when=christmas, suppression=EMPTY_SUPPRESSION)
    assert not r.allowed
    assert "federal_holiday" in r.blocked_reasons


def test_kentucky_late_start_enforced():
    """KY bans solicitation calls before 10:00 local; NY follows the default."""
    when = datetime(2026, 7, 8, 13, 30, tzinfo=timezone.utc)  # 09:30 EDT
    ky = check_compliance(make_lead(state="KY"), "call", when=when, suppression=EMPTY_SUPPRESSION)
    ny = check_compliance(make_lead(state="NY"), "call", when=when, suppression=EMPTY_SUPPRESSION)
    assert not ky.allowed and "too_early" in ky.blocked_reasons
    assert ny.allowed


def test_dst_awareness():
    """CA is UTC-7 in July (PDT) and UTC-8 in January (PST)."""
    july = local_time_for_state("CA", datetime(2026, 7, 8, 18, 0, tzinfo=timezone.utc))
    january = local_time_for_state("CA", datetime(2026, 1, 7, 18, 0, tzinfo=timezone.utc))
    assert july.hour == 11
    assert january.hour == 10


def test_arizona_ignores_dst():
    july = local_time_for_state("AZ", datetime(2026, 7, 8, 18, 0, tzinfo=timezone.utc))
    january = local_time_for_state("AZ", datetime(2026, 1, 7, 18, 0, tzinfo=timezone.utc))
    assert july.hour == january.hour == 11


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def test_all_violations_reported_not_just_first():
    lead = make_lead(state=None, phone=None)
    r = check_compliance(lead, "call", when=None, suppression=None)
    assert not r.allowed
    assert "missing_state" in r.blocked_reasons
    assert "no_suppression_list" in r.blocked_reasons
    assert "missing_timestamp" in r.blocked_reasons


def test_result_serializes_to_dict():
    r = check_compliance(make_lead(), "call", when=SAFE_WHEN, suppression=EMPTY_SUPPRESSION)
    d = r.to_dict()
    assert d["allowed"] is True
    assert all({"name", "passed", "reason", "detail"} <= set(c) for c in d["checks"])
