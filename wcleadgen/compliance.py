"""Fail-closed outreach compliance engine.

The single most important property of this module: **when in doubt, block.**
Missing state, unknown state, missing phone number, naive timestamp, absent
suppression list — every ambiguous input resolves to "not allowed" with a
machine-readable reason code. A compliance engine that guesses is a lawsuit
generator; this one refuses to guess.

Checks per channel
------------------
call    state eligibility, DNC/suppression, per-state calling window
        (quiet hours, no-Sunday states, federal holidays)
sms     everything ``call`` checks, plus prior express consent
email   state eligibility, suppression, CAN-SPAM required fields

All checks always run, so a blocked result reports *every* violated rule,
not just the first one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from .models import ComplianceCheck, ComplianceResult, Lead

CHANNELS = ("call", "sms", "email")

# ---------------------------------------------------------------------------
# State eligibility.
#
# ND, OH, WA, WY are monopolistic workers'-comp states: employers buy coverage
# from a state fund, so private premium-audit consulting works differently and
# is out of scope for this reference pipeline. Anything not in either table is
# unknown and therefore blocked (fail-closed).
# ---------------------------------------------------------------------------
MONOPOLISTIC_STATES = {"ND", "OH", "WA", "WY"}

ELIGIBLE_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
    "TX", "UT", "VT", "VA", "WV", "WI", "DC",
}

# ---------------------------------------------------------------------------
# Timezones — pure stdlib. Each state maps to (standard UTC offset, observes
# DST). Mixed-zone states use the majority zone. US DST: second Sunday of
# March 02:00 to first Sunday of November 02:00.
# ---------------------------------------------------------------------------
STATE_UTC = {
    "CT": (-5, True), "DE": (-5, True), "FL": (-5, True), "GA": (-5, True),
    "IN": (-5, True), "KY": (-5, True), "ME": (-5, True), "MD": (-5, True),
    "MA": (-5, True), "MI": (-5, True), "NH": (-5, True), "NJ": (-5, True),
    "NY": (-5, True), "NC": (-5, True), "OH": (-5, True), "PA": (-5, True),
    "RI": (-5, True), "SC": (-5, True), "VT": (-5, True), "VA": (-5, True),
    "WV": (-5, True), "DC": (-5, True),
    "AL": (-6, True), "AR": (-6, True), "IL": (-6, True), "IA": (-6, True),
    "KS": (-6, True), "LA": (-6, True), "MN": (-6, True), "MS": (-6, True),
    "MO": (-6, True), "NE": (-6, True), "ND": (-6, True), "OK": (-6, True),
    "SD": (-6, True), "TN": (-6, True), "TX": (-6, True), "WI": (-6, True),
    "CO": (-7, True), "ID": (-7, True), "MT": (-7, True), "NM": (-7, True),
    "UT": (-7, True), "WY": (-7, True),
    "AZ": (-7, False),  # no DST
    "CA": (-8, True), "NV": (-8, True), "OR": (-8, True), "WA": (-8, True),
    "AK": (-9, True),
    "HI": (-10, False),  # no DST
}

# ---------------------------------------------------------------------------
# Calling windows. Federal TCPA allows 8:00-21:00 local; several states are
# stricter. Format: (start_hour, end_hour, no_sunday). We additionally apply
# an internal safety buffer so the effective window is the *tighter* of the
# state rule and (SAFETY_START, SAFETY_END).
# ---------------------------------------------------------------------------
FEDERAL_WINDOW = (8, 21, False)

STATE_CALL_RULES = {
    "AL": (8, 20, True),
    "FL": (8, 20, False),
    "IN": (8, 21, True),
    "KY": (10, 21, False),
    "LA": (8, 21, True),
    "MA": (8, 20, False),
    "MD": (8, 20, False),
    "MS": (8, 20, False),
    "NV": (8, 20, False),
    "OK": (8, 21, True),
    "RI": (9, 20, False),
    "SC": (8, 20, True),
    "TX": (9, 21, True),
    "UT": (8, 21, True),
}

SAFETY_START_HOUR = 9  # never dial before 9am local, even where 8am is legal
SAFETY_END_HOUR = 20  # never dial after 8pm local, even where 9pm is legal

CANSPAM_REQUIRED_FIELDS = ("from_address", "postal_address", "unsubscribe_url", "subject")


@dataclass
class SuppressionList:
    """DNC phones and suppressed emails. Normalizes on the way in and out."""

    phones: set = field(default_factory=set)
    emails: set = field(default_factory=set)

    def __post_init__(self) -> None:
        self.phones = {normalize_phone(p) for p in self.phones if normalize_phone(p)}
        self.emails = {str(e).strip().lower() for e in self.emails if str(e).strip()}

    def has_phone(self, phone: Optional[str]) -> bool:
        norm = normalize_phone(phone)
        return bool(norm) and norm in self.phones

    def has_email(self, email: Optional[str]) -> bool:
        return bool(email) and str(email).strip().lower() in self.emails


def normalize_phone(phone: Optional[str]) -> str:
    """Digits-only, with US country code stripped: '+1 (555) 010-4477' -> '5550104477'."""
    if not phone:
        return ""
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


# ---------------------------------------------------------------------------
# Holidays + DST math (stdlib only)
# ---------------------------------------------------------------------------
def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    nxt = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    last = nxt - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def federal_holidays(year: int) -> set:
    """US federal holidays, including Sat->Fri / Sun->Mon observed shifts."""
    days = {
        date(year, 1, 1),
        _nth_weekday(year, 1, 0, 3),   # MLK Day
        _nth_weekday(year, 2, 0, 3),   # Presidents Day
        _last_weekday(year, 5, 0),     # Memorial Day
        date(year, 6, 19),             # Juneteenth
        date(year, 7, 4),              # Independence Day
        _nth_weekday(year, 9, 0, 1),   # Labor Day
        _nth_weekday(year, 10, 0, 2),  # Columbus Day
        date(year, 11, 11),            # Veterans Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving
        date(year, 12, 25),            # Christmas
    }
    observed = set()
    for d in days:
        if d.weekday() == 5:
            observed.add(d - timedelta(days=1))
        elif d.weekday() == 6:
            observed.add(d + timedelta(days=1))
    return days | observed


def _us_dst_active(local_naive: datetime) -> bool:
    """True when US daylight saving time is in effect at the given local time."""
    year = local_naive.year
    start = datetime.combine(_nth_weekday(year, 3, 6, 2), datetime.min.time()).replace(hour=2)
    end = datetime.combine(_nth_weekday(year, 11, 6, 1), datetime.min.time()).replace(hour=2)
    return start <= local_naive < end


def local_time_for_state(state: str, when_utc: datetime) -> Optional[datetime]:
    """Convert an aware UTC datetime to naive local time for a US state.

    Returns ``None`` for unknown states — callers must treat that as a block.
    """
    info = STATE_UTC.get(state)
    if info is None:
        return None
    std_offset, observes_dst = info
    base = when_utc.astimezone(timezone.utc).replace(tzinfo=None)
    local = base + timedelta(hours=std_offset)
    if observes_dst and _us_dst_active(local):
        local += timedelta(hours=1)
    return local


# ---------------------------------------------------------------------------
# Individual checks — each returns a ComplianceCheck and never raises.
# ---------------------------------------------------------------------------
def check_state_eligibility(lead: Lead) -> ComplianceCheck:
    name = "state_eligibility"
    if not lead.state:
        return ComplianceCheck(name, False, "missing_state", "lead has no state — fail closed")
    state = lead.state.strip().upper()
    if state in MONOPOLISTIC_STATES:
        return ComplianceCheck(
            name, False, "state_monopolistic",
            f"{state} is a monopolistic WC state — out of scope",
        )
    if state not in ELIGIBLE_STATES:
        return ComplianceCheck(
            name, False, "unknown_state",
            f"'{lead.state}' not in eligibility table — fail closed",
        )
    return ComplianceCheck(name, True, "ok", f"{state} is eligible")


def check_suppression(lead: Lead, channel: str, suppression: Optional[SuppressionList]) -> ComplianceCheck:
    name = "suppression"
    if suppression is None:
        return ComplianceCheck(
            name, False, "no_suppression_list",
            "suppression list unavailable — cannot prove lead is not on DNC, fail closed",
        )
    if channel in ("call", "sms"):
        if not lead.phone:
            return ComplianceCheck(name, False, "missing_phone", "no phone on lead — fail closed")
        if suppression.has_phone(lead.phone):
            return ComplianceCheck(name, False, "dnc_listed", "phone is on the DNC/suppression list")
    else:  # email
        if not lead.email:
            return ComplianceCheck(name, False, "missing_email", "no email on lead — fail closed")
        if suppression.has_email(lead.email):
            return ComplianceCheck(name, False, "email_suppressed", "email is suppressed")
    return ComplianceCheck(name, True, "ok", "not on any suppression list")


def check_calling_window(lead: Lead, when: Optional[datetime]) -> ComplianceCheck:
    name = "calling_window"
    if when is None:
        return ComplianceCheck(name, False, "missing_timestamp", "no send time given — fail closed")
    if when.tzinfo is None:
        return ComplianceCheck(
            name, False, "naive_timestamp",
            "timestamp has no timezone — cannot compute local time, fail closed",
        )
    if not lead.state:
        return ComplianceCheck(name, False, "missing_state", "no state — cannot compute local time")
    state = lead.state.strip().upper()
    local = local_time_for_state(state, when)
    if local is None:
        return ComplianceCheck(name, False, "unknown_timezone", f"no timezone mapping for '{state}'")

    if local.date() in federal_holidays(local.year):
        return ComplianceCheck(name, False, "federal_holiday", f"{local.date()} is a federal holiday")

    start, end, no_sunday = STATE_CALL_RULES.get(state, FEDERAL_WINDOW)
    if local.weekday() == 6 and no_sunday:
        return ComplianceCheck(name, False, "state_no_sunday", f"{state} bans Sunday solicitation calls")

    eff_start = max(start, SAFETY_START_HOUR)
    eff_end = min(end, SAFETY_END_HOUR)
    minutes = local.hour * 60 + local.minute
    if minutes < eff_start * 60:
        return ComplianceCheck(
            name, False, "too_early",
            f"local time {local.strftime('%H:%M')} is before {eff_start:02d}:00 window open",
        )
    if minutes >= eff_end * 60:
        return ComplianceCheck(
            name, False, "too_late",
            f"local time {local.strftime('%H:%M')} is past {eff_end:02d}:00 window close",
        )
    return ComplianceCheck(name, True, "ok", f"local time {local.strftime('%H:%M')} inside window")


def check_sms_consent(lead: Lead) -> ComplianceCheck:
    name = "sms_consent"
    if lead.sms_consent is True:
        return ComplianceCheck(name, True, "ok", "prior express consent on file")
    if lead.sms_consent is False:
        return ComplianceCheck(name, False, "consent_revoked", "SMS consent explicitly revoked")
    return ComplianceCheck(
        name, False, "no_consent_record",
        "no record of prior express consent — fail closed",
    )


def check_canspam(email_meta: Optional[dict]) -> ComplianceCheck:
    name = "can_spam"
    if email_meta is None:
        return ComplianceCheck(
            name, False, "missing_email_metadata",
            "no email metadata supplied — cannot verify CAN-SPAM fields, fail closed",
        )
    missing = [f for f in CANSPAM_REQUIRED_FIELDS if not str(email_meta.get(f) or "").strip()]
    if missing:
        return ComplianceCheck(
            name, False, "canspam_missing_fields",
            "missing required CAN-SPAM fields: " + ", ".join(sorted(missing)),
        )
    return ComplianceCheck(name, True, "ok", "all CAN-SPAM required fields present")


# ---------------------------------------------------------------------------
# Main API
# ---------------------------------------------------------------------------
def check_compliance(
    lead: Lead,
    channel: str,
    *,
    when: Optional[datetime] = None,
    suppression: Optional[SuppressionList] = None,
    email_meta: Optional[dict] = None,
) -> ComplianceResult:
    """Run every compliance gate for ``channel`` and return the full verdict.

    Fail-closed contract:

    * unknown channel -> blocked (``unknown_channel``)
    * any missing input a check needs -> that check fails with a specific code
    * an unexpected exception inside a check -> blocked (``check_error``)
    * ``allowed`` is True only when *every* check passed
    """
    if channel not in CHANNELS:
        check = ComplianceCheck(
            "channel", False, "unknown_channel",
            f"'{channel}' is not a supported channel {CHANNELS} — fail closed",
        )
        return ComplianceResult(lead.lead_id, channel, False, ["unknown_channel"], [check])

    checks = []
    plan = [lambda: check_state_eligibility(lead), lambda: check_suppression(lead, channel, suppression)]
    if channel in ("call", "sms"):
        plan.append(lambda: check_calling_window(lead, when))
    if channel == "sms":
        plan.append(lambda: check_sms_consent(lead))
    if channel == "email":
        plan.append(lambda: check_canspam(email_meta))

    for run in plan:
        try:
            checks.append(run())
        except Exception as exc:  # noqa: BLE001 — fail closed on anything
            checks.append(ComplianceCheck("internal", False, "check_error", f"{type(exc).__name__}: {exc}"))

    # Deduplicate reason codes while keeping first-seen order (two checks can
    # fail for the same root cause, e.g. missing_state).
    blocked = list(dict.fromkeys(c.reason for c in checks if not c.passed))
    return ComplianceResult(
        lead_id=lead.lead_id,
        channel=channel,
        allowed=not blocked,
        blocked_reasons=blocked,
        checks=checks,
    )
