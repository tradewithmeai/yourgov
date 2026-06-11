# Data Sources

YourGov is source-linked and public-record based.

## Primary sources

- UK Parliament open data APIs (members, divisions, written questions)
- Local SQLite cache/seed generated from those records

## Internal datasets

- `mygov.db` bundled seed database
- Static feasibility data for `/global`: `static/data/global_feasibility.json`

## Important constraints

- Records can be incomplete or lag current events.
- Vote records show recorded actions, not intent.
- Missing speech/questions/votes do not imply wrongdoing.

## Source-link principle

Each visual or explainer output should be traceable to a source record where possible.

