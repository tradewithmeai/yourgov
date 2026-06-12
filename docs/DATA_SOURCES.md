# Data Sources

YourGov is source-linked and public-record based.

## Primary sources

- UK Parliament open data APIs (members, divisions, written questions)
- Local SQLite cache/seed generated from those records

## Internal datasets

- `mygov.db` bundled seed database
- Static feasibility data for `/global`: `static/data/global_feasibility.json`

## Production refresh

- GitHub Actions refreshes `mygov.db` daily at 03:00 UTC.
- The refresh pulls current Commons members and recent Commons division vote detail from Parliament APIs.
- GitHub data validation runs 15 minutes after the records update.
- The scheduled validation uses full network freshness checks; it must not use `--skip-network-freshness`.
- Production validation only passes when the local latest division matches the latest Commons Votes API division and the four Source Lens map modes remain scoped to the selected division.
- Commons coverage is reconciled against Parliament's official constituency endpoint: current MPs plus vacant seats must equal the 650 UK constituencies.
- Map payloads include all 650 constituencies. Seats without a current MP are explicit `Vacant seat` rows, not silently missing map areas.

## Important constraints

- Records can be incomplete or lag current events.
- Vote records show recorded actions, not intent.
- Missing speech/questions/votes do not imply wrongdoing.

## Source-link principle

Each visual or explainer output should be traceable to a source record where possible.
