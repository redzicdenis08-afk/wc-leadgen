# Compliance Guide

WC Lead-Gen is fail-closed: if a compliance check cannot be confirmed,
the lead is not routed.

## DNC enforcement

1. Internal DNC file (examples/dnc.txt) - one E.164 number per line
2. Lead-level opt_out field - if true, lead is permanently suppressed
3. National DNC list check - pluggable adapter (see adapters/dnc.py)

## Calling window

    {"call_window_start": 9, "call_window_end": 17, "timezone": "America/New_York"}

## Opt-out handling

When a lead opts out during a call:
1. Set opt_out=true in lead record
2. Add phone to internal DNC file
3. Log event with timestamp and agent ID
4. Never route this lead again

## Audit trail

Every routing decision is logged:

    lead-004: BLOCKED -- opt_out=true
    lead-001: BLOCKED -- outside calling window
    lead-002: ROUTED -- partner-003 assigned
