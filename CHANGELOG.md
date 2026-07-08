# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Planned
- `--filter-city` flag for city-scoped lead pulls
- Partner matching by service area overlap
- Webhook push on new lead ingested

## [0.2.0] - 2026-07-08

### Added
- `docs/COMPLIANCE.md`: DNC enforcement and opt-out handling guide
- `docs/SCORING.md`: lead quality scoring explanation
- `examples/batch_run.sh`: example shell script for nightly batch run

### Changed
- README: added installation and quick-start

## [0.1.0] - 2026-06-24

### Added
- Lead scoring: recency, intent, geographic match
- Fail-closed compliance: DNC list, opt-out, calling-window enforcement
- Routing: assign leads to the right partner or service provider
- CSV and JSON ingestion
- CLI: `wc-leadgen run`, `wc-leadgen score`
- Test suite and CI
