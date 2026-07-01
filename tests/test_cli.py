"""CLI tests against the bundled synthetic examples."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wcleadgen.cli import main  # noqa: E402

EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")
LEADS_CSV = os.path.join(EXAMPLES, "leads.csv")
LEADS_JSON = os.path.join(EXAMPLES, "leads.json")
PARTNERS = os.path.join(EXAMPLES, "partners.json")
DNC = os.path.join(EXAMPLES, "dnc.txt")
EMAIL_META = os.path.join(EXAMPLES, "email_meta.json")

SAFE_WHEN = "2026-07-08T18:00:00+00:00"  # Wed 13:00 CDT


def run_cli(capsys, *argv):
    code = main(list(argv))
    return code, capsys.readouterr().out


def test_score_csv_human_output(capsys):
    code, out = run_cli(capsys, "score", LEADS_CSV)
    assert code == 0
    assert "lead-001" in out
    assert "qualified" in out.lower()


def test_score_json_output_parses(capsys):
    code, out = run_cli(capsys, "score", LEADS_CSV, "--json")
    assert code == 0
    rows = json.loads(out)
    assert len(rows) == 8
    acme = next(r for r in rows if r["lead_id"] == "lead-001")
    assert acme["qualified"] is True
    assert len(acme["factors"]) == 5


def test_check_blocks_dnc_and_missing_data(capsys):
    code, out = run_cli(
        capsys, "check", LEADS_CSV, "--channel", "call", "--when", SAFE_WHEN, "--dnc", DNC, "--json"
    )
    assert code == 1  # at least one lead blocked -> nonzero exit
    rows = json.loads(out)
    by_id = {r["lead_id"]: r for r in rows}
    assert by_id["lead-001"]["allowed"] is True
    assert "dnc_listed" in by_id["lead-003"]["blocked_reasons"]
    assert "state_monopolistic" in by_id["lead-005"]["blocked_reasons"]
    assert "missing_state" in by_id["lead-006"]["blocked_reasons"]


def test_check_email_channel_with_meta(capsys):
    code, out = run_cli(
        capsys, "check", LEADS_JSON, "--channel", "email",
        "--dnc", DNC, "--email-meta", EMAIL_META, "--json",
    )
    rows = json.loads(out)
    by_id = {r["lead_id"]: r for r in rows}
    assert by_id["lead-101"]["allowed"] is True
    assert "state_monopolistic" in by_id["lead-102"]["blocked_reasons"]  # WA


def test_check_without_when_fails_closed(capsys):
    code, out = run_cli(capsys, "check", LEADS_JSON, "--channel", "call", "--dnc", DNC, "--json")
    assert code == 1
    rows = json.loads(out)
    assert all("missing_timestamp" in r["blocked_reasons"] for r in rows)


def test_route_json(capsys):
    code, out = run_cli(capsys, "route", LEADS_CSV, "--partners", PARTNERS, "--json")
    assert code == 0
    rows = json.loads(out)
    by_id = {r["lead_id"]: r for r in rows}
    assert by_id["lead-001"]["firm_id"] == "firm-alpha"  # TX roofing specialist
    assert by_id["lead-007"]["firm_id"] == "firm-delta"  # NH landscaping
    assert by_id["lead-008"]["matched"] is False  # no active WC policy


def test_run_full_pipeline(capsys):
    code, out = run_cli(
        capsys, "run", LEADS_CSV, "--partners", PARTNERS,
        "--when", SAFE_WHEN, "--dnc", DNC, "--json",
    )
    assert code == 0
    rows = json.loads(out)
    by_id = {r["lead_id"]: r for r in rows}
    assert by_id["lead-001"]["status"] == "routed"
    assert by_id["lead-005"]["status"] == "blocked_compliance"  # OH monopolistic
    assert by_id["lead-006"]["status"] == "rejected_low_score"
    assert by_id["lead-008"]["status"] == "rejected_low_score"  # wc_policy_active=false
    for row in rows:
        assert row["audit_trail"], "every lead must leave an audit trail"


def test_missing_input_file_exits_cleanly(capsys):
    try:
        main(["score", "does-not-exist.csv"])
    except SystemExit as exc:
        assert "not found" in str(exc)
    else:
        raise AssertionError("expected SystemExit")
