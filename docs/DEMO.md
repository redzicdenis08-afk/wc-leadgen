# Demo

This is the fastest way to show why WC Lead-Gen is worth starring. Use fictional example data only.

## Run it

```bash
pip install -e .
python -m wcleadgen score examples/leads.csv
python -m wcleadgen check examples/leads.csv --channel call --when 2026-07-08T18:00:00+00:00 --dnc examples/dnc.txt
python -m wcleadgen run examples/leads.csv --partners examples/partners.json --when 2026-07-08T18:00:00+00:00 --dnc examples/dnc.txt
```

## What to screenshot

Lead scores, blocked reasons, allowed decisions, routing status, and audit trail.

A good launch screenshot should show the command and the useful output in one image. Avoid giant terminal dumps.

## 30-second narration

1. Say the pain this repo solves.
2. Run the command.
3. Point at the output that proves it works.
4. Mention that the examples are fictional and the engine is inspectable.

## Good caption

This is the whole point of WC Lead-Gen: small input in, useful decision output, no black-box dashboard needed.
