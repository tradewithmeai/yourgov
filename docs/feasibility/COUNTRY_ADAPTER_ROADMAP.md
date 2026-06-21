# Country Adapter Roadmap

YourGov is not a universal one-click civic app. It is a source-linked parliamentary explainer with country adapters.

The UK Source Lens is the first working adapter. It proves the core pattern:

| Adapter layer | UK implementation |
|---|---|
| Representative adapter | Parliament Members API and local SQLite seed |
| Vote/division adapter | Commons division records and PublicWhip-style source pane |
| Geography adapter | UK constituency GeoJSON joined by constituency name |
| Explainer terminology adapter | Plain-English vote explanation prompts and caveats |
| Source-record adapter | Same-origin source panel and source-linked division routes |

`/global` is a feasibility globe. It does not claim YourGov currently supports every country.

## What `/global` does

`/global` renders the Global Civic Lens: a 3D globe with one plus marker per country in the feasibility dataset. The marker colour is a buildability signal:

| Colour | Meaning |
|---|---|
| Green | Ready/Pilot: strong candidate for a YourGov-style adapter |
| Orange | Buildable with effort: possible, but data joins/licence/source work remain |
| Red | Not currently build-ready: insufficient verified data, high friction, or safety/legal concerns |

This is civic-data feasibility, not a political score.

## Data source

The initial dataset lives at:

```text
static/data/global_feasibility.json
```

The same data is exposed through:

```text
GET /api/global/feasibility
```

The dataset is structured from the uploaded global feasibility research report. It covers 193 UN member states plus the Holy See and the State of Palestine. The report gives a verified top band and buildable band. Countries outside those verified positive bands are marked red conservatively until a country-specific audit proves otherwise.

## First adapter targets after the UK

The strongest first pilots are:

1. Canada
2. Sweden
3. Norway
4. Netherlands
5. Australia

Canada is the recommended first non-UK prototype because it is close enough to Westminster logic to reuse much of the UK mental model, but different enough to test whether the adapter abstraction is real.

## Adapter contract

Future country adapters should aim to produce these portable entities:

| Object | Minimum requirement |
|---|---|
| Person | Stable ID, official name, party/group, chamber memberships, contact/source links |
| Membership | Person ID, chamber ID, party/group, seat status, start/end dates |
| Chamber | Legislature, chamber type, term, official source |
| District | District ID, official name, geometry source, boundary validity dates |
| Vote / Division | Vote ID, chamber, date, title/motion, result, per-member vote where available |
| Speech / Intervention | Event ID, speaker ID, chamber, timestamp/date, transcript fragment, source URL |
| Question | Question ID, asker, respondent, date, answer text if available |
| Source | URL, publisher, retrieval date, licence, language, confidence |
| Caveat file | Legal, political, linguistic, matching, and safety caveats per country |

## Eligibility gate before building

Do not build a new adapter until these checks are answered with evidence:

1. Can representatives be identified by stable official IDs?
2. Can representative records be joined to districts or seats?
3. Are roll-call votes available and reusable?
4. Are debates, speeches, questions, or equivalent parliamentary activity records available?
5. Are boundaries available with a usable licence?
6. Are source URLs stable enough for user verification?
7. Is licence/reuse clear enough for production?
8. Is a public-facing civic explainer safe to operate in that environment?

If the answer is unclear, the country remains red or orange. The correct output is sometimes “not yet”.

## Implementation notes

The globe deliberately uses centroid markers rather than country polygons. That keeps the Flask deployment small, avoids Mapbox or token-based services, and makes the data layer easier to extend.

Country-specific adapters should not mutate `global_feasibility.json` into a support claim. The feasibility layer and working adapter layer should stay separate:

```text
global_feasibility.json  -> readiness map
country adapter modules  -> working source-linked civic data
```

## Copy rules

Allowed wording:

- “Canada is a strong candidate for the next adapter.”
- “Brazil is buildable with effort.”
- “This country needs source verification before build work.”

Avoid wording:

- “All countries are supported.”
- “This is a government quality score.”
- “Red means bad government.”
- “YourGov has live parliamentary data for every country.”

The globe is there to show the expansion strategy honestly. Shiny globe, sober caveats. That is the deal.
