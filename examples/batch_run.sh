#!/usr/bin/env bash
# Nightly batch run for WC Lead-Gen
# Cron: 0 6 * * * /path/to/batch_run.sh

set -euo pipefail

LEADS_FILE="examples/leads.csv"
OUTPUT_DIR="output/$(date +%Y-%m-%d)"

mkdir -p "$OUTPUT_DIR"

echo "[batch] Scoring leads..."
python -m wc_leadgen score "$LEADS_FILE" --output "$OUTPUT_DIR/scored.csv"

echo "[batch] Compliance filter..."
python -m wc_leadgen filter "$OUTPUT_DIR/scored.csv" \
    --dnc examples/dnc.txt \
    --output "$OUTPUT_DIR/compliant.csv"

echo "[batch] Routing..."
python -m wc_leadgen route "$OUTPUT_DIR/compliant.csv" \
    --partners examples/partners.json \
    --output "$OUTPUT_DIR/routed.csv"

echo "[batch] Done: $OUTPUT_DIR/"
