# Daily Data Refresh Implementation Plan

## Requirements

- Work only in the live `mygov` repo on branch `codex/production-readiness-map-validation`.
- Refresh parliamentary records daily out of hours, scheduled at 03:00.
- Run GitHub data validation 15 minutes after the records update.
- Validation must be a real production check, not a skipped-freshness check.
- Validation must prove the four map visualisations are scoped to the selected division, not generic party, gender, or rebel data.
- Do not claim full data availability until refreshed local data matches the latest Commons Votes API data and validation passes.

## Design

1. Add a focused data updater script for the bundled SQLite seed database.
2. Fetch current Commons members from the Members API without an empty `Name` filter.
3. Fetch recent Commons divisions from the Commons Votes API and upsert full division vote detail.
4. Keep current-constituency map data clean by removing constituency assignments from members no longer returned as current Commons members.
5. Add a GitHub Actions workflow that runs the updater at 03:00 UTC, waits 900 seconds, runs full production validation, then commits `mygov.db` only if validation passes.
6. Strengthen the production validation freshness threshold so "all data available" means the local latest division matches upstream latest.
7. Document the production data-refresh contract.

## Verification

- Unit tests for updater parsing, member sync, and recent division refresh.
- Workflow tests for cron timing, 900-second delay, full validation, and commit ordering.
- Existing production validation tests.
- Local run of the updater against `mygov.db`.
- Full `validate_production_ready.py` without `--skip-network-freshness`.
