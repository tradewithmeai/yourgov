# YourGov First-Party Source Lens Design

**Date:** 2026-06-08
**Branch:** `codex/production-readiness-map-validation`
**Status:** Ready for user review

## Goal

Turn the current hackathon-led Source Lens into a first-party YourGov product surface. The user should see the YourGov site controls and the map at the same time, while PublicWhip moves into a supporting source dropdown in the left panel.

## Product Direction

YourGov becomes the primary experience. PublicWhip remains important as evidence, but it should no longer define the default layout or feel like the app is a mirror of another service.

The core user flow becomes:

1. User searches for an MP, constituency, postcode, issue, or division.
2. User selects a division or arrives with a default recent division.
3. The left panel shows a YourGov summary of that selected record.
4. The map remains visible and applies the selected division through four views.
5. The user can open PublicWhip or Parliament source records from a dropdown when they want supporting evidence.

## Current Baseline

Audit on 2026-06-08 found:

- `24` tests pass with Python 3.12.
- Key routes such as `/`, `/source-lens`, `/global`, `/publicwhip`, and `/mp/206` return `200`.
- Local database has `647` members, `157542` vote rows, `1167` distinct divisions, and `195` feasibility countries.
- The local seed latest division is `2356` dated `2026-05-21`.
- The Commons Votes API has newer divisions, with `2361` dated `2026-06-03`, so production validation must check freshness.
- The active Source Lens UI is `templates/panel_test.html` with behavior in `static/panel_test.js`.
- The active map relay is `templates/map_relay.html`.
- The formal production validation script referenced in docs is missing from this repo.

## Problems To Fix

### PublicWhip Dominates The Product

The current default layout makes PublicWhip feel like the main product. This weakens the YourGov identity and makes the app look like a wrapper rather than a first-party civic tool.

### Map Modes Are Not Division-Scoped

Selecting a division correctly loads vote-specific data. The four map wedges then diverge:

- Vote mode uses the selected division.
- Party mode fetches a generic current-party map.
- Gender mode fetches a generic current-gender map.
- Rebel mode fetches a generic historical rebel-rate map.

This breaks the intended contract. The four visual modes should show the selected division in different ways.

### Brand Is Split Across MyGov And YourGov

The repo contains public `MyGov` strings, plus technical identifiers such as `MYGOV_AGENT_API_TOKEN`, `mygov.db`, `mygov:*` browser events, MCP names, Android package IDs, and iOS bundle IDs.

The first production rename should remove public-facing `MyGov` while preserving internal compatibility aliases where changing them would create unnecessary deployment or integration risk.

### Validation Is Not Strong Enough For Production

The current tests prove route and API basics, but they do not yet prove:

- the selected division drives every map mode;
- every displayed claim has a source link;
- the seed data is fresh enough;
- public copy no longer says MyGov;
- PublicWhip is available as a supporting source rather than default product chrome.

## Design

### Layout

Desktop layout uses two fixed panels:

```text
+--------------------------------+--------------------------------+
| YourGov Panel                  | Map View                       |
|                                |                                |
| Search                         | UK constituency map            |
| Selected division summary      |                                |
| Mode-aware explanation         | Vote / Party / Gender / Rebel  |
| Source dropdown                | Legend and caveats             |
| Evidence links                 |                                |
+--------------------------------+--------------------------------+
```

The left panel is the YourGov control and explanation surface. The right panel is the visible map. The map should remain visible throughout normal desktop use.

On mobile, the same hierarchy stacks into a top YourGov control panel followed by the map. A sticky mobile switcher can be added later if the first implementation becomes cramped, but the initial production goal is to keep both surfaces discoverable without hiding the source controls behind PublicWhip.

### Left Panel Content

The left panel contains:

- YourGov brand header and logo.
- Search input for MP, constituency, postcode, issue, or division text.
- Recent or matched division list.
- Selected division summary:
  - title;
  - date;
  - Aye count;
  - No count;
  - absent or unknown count;
  - plain-English caveat;
  - source links.
- Source dropdown:
  - `YourGov Summary` as default;
  - `PublicWhip Record`;
  - `Parliament Record` where a direct official source URL is available;
  - `TheyWorkForYou` only where a reliable URL match exists.

The dropdown changes the supporting evidence view inside the left panel. It does not replace the whole product shell.

### Map Panel Content

The map panel contains:

- UK constituency map.
- Four visible mode controls:
  - Vote;
  - Party;
  - Gender;
  - Rebel.
- Data legend tied to the selected mode.
- Status text for loading, stale data, unavailable source, and failed map paint.
- Caveat text explaining that public records show recorded actions, not motive or character.

### Selected Division State

The selected division becomes the single source of truth for map visualisation.

State must track:

- `selectedDivisionId`;
- `selectedDivisionTitle`;
- `selectedDivisionDate`;
- `selectedDivisionCounts`;
- `selectedMapMode`;
- `selectedDivisionPayloadByMode`.

Changing mode must not discard the selected division. Changing division must refresh the active mode.

### Division-Scoped Map Modes

All modes must be built from the selected division.

#### Vote Mode

Shows how each constituency's MP voted on the selected division:

- Aye;
- No;
- Absent or unknown.

#### Party Mode

Shows party colours for MPs in the selected division context. Labels and hover text must mention the selected division and the MP's vote.

Example label:

`Labour: Jane Example. Voted Aye on King's Speech Motion for an Address.`

This is not a generic party map. It is a party-coloured view of the selected division.

#### Gender Mode

Shows MP gender colours for MPs in the selected division context. Labels and hover text must mention the selected division and the MP's vote.

Unknown gender remains an explicit unknown-data state, not an inferred claim.

#### Rebel Mode

Shows whether each MP voted with or against their party majority on the selected division.

Categories:

- with party majority;
- against party majority;
- no clear party majority;
- absent or unknown;
- independent or no party grouping.

This replaces the current generic historical rebel-rate behavior for the four-wedge flow. A separate historical rebel-rate view can return later as a profile metric, but it should not be one of the selected-division map views.

### Backend Data Contract

Add one canonical payload builder:

```text
division_id + mode -> map payload
```

Supported modes:

- `vote-split`;
- `party-split`;
- `gender-split`;
- `rebel-split`.

The payload must include:

- `ok`;
- `mode`;
- `division`;
- `counts`;
- `map_data`;
- `legend`;
- `caveat`;
- `source_links`;
- `data_quality`.

`map_data` entries must include:

- `constituency`;
- `member_id`;
- `name`;
- `party`;
- `vote`;
- `color`;
- `label`;
- `source`;
- mode-specific fields such as `gender`, `party_majority`, or `rebel_status`.

The current endpoints can remain as compatibility wrappers during the first implementation, but new UI code should call the canonical division-scoped endpoint.

### Source Dropdown Contract

The source dropdown is scoped to the selected division.

Default state:

- `YourGov Summary` selected.
- PublicWhip and Parliament options visible only when their URLs can be built.

If no division is selected:

- show recent divisions and search;
- disable record-specific source options;
- explain that selecting a division unlocks source records.

If PublicWhip is selected:

- load the PublicWhip record in a contained evidence view in the left panel;
- keep the map visible;
- keep the YourGov brand and selected-division header visible.

If Parliament source is selected:

- open the source in a new tab if it cannot be safely embedded;
- keep a visible source link and citation in the YourGov summary.

### Rename And Logo

Public-facing brand changes from MyGov to YourGov.

Public-facing surfaces include:

- page titles;
- headings;
- navigation;
- visible body copy;
- metadata descriptions;
- source caveats;
- release docs intended for users;
- mobile app display names;
- visible screenshot alt text;
- logo and favicon.

Compatibility-sensitive internals can keep old names in the first migration if they are not visible to users:

- `mygov.db`;
- `MYGOV_AGENT_API_TOKEN`;
- `MYGOV_APP_URL`;
- `mygov:*` browser events;
- existing MCP class names and Python module names;
- existing Android and iOS package identifiers.

Those compatibility names should be documented as temporary aliases. A later hard migration can rename them once deployments, secrets, mobile identifiers, and agent integrations are ready.

Logo direction:

- Create a first-party YourGov wordmark.
- Include a compact `YG` mark for favicon, mobile launcher, and small UI chips.
- Use a source/check motif rather than official crown or GOV.UK-style branding.
- Avoid visual claims that the app is an official government service.
- Prefer a civic, source-led visual identity: clear typography, map-grid geometry, and confident but non-governmental colours.

Initial assets to create during implementation:

- `static/img/yourgov-logo.svg`;
- `static/img/yourgov-mark.svg`;
- `static/img/favicon.svg`;
- Android launcher foreground update if mobile build is in scope;
- iOS app icon update if mobile build is in scope.

### Validation

Add a production validation script inside this repo.

It should check:

- core routes return `200` or documented redirects;
- `/source-lens` shows YourGov as the primary product, not MyGov or PublicWhip mirror language;
- PublicWhip is available through the source dropdown contract;
- `/api/lens/source-divisions` returns non-empty results;
- the canonical map payload endpoint returns non-empty `map_data` for every supported mode and a known division;
- all four mode payloads include the same selected `division_id`;
- Party/Gender/Rebel labels reference the selected division or include the MP's vote;
- source links exist for selected division output;
- global feasibility data has no duplicate ISO2 values and includes the UK working adapter;
- seed data freshness is checked against Commons Votes search results and reports stale data when local latest division trails upstream beyond an accepted threshold;
- public-facing files have no visible `MyGov` text after the rename, excluding documented compatibility internals and generated third-party artifacts.

The validation script should fail loudly for broken production contracts and print a summary that can be pasted into release notes.

## Approaches Considered

### Option A: Keep PublicWhip As The Main Right Pane

This is closest to the current hackathon design, but it keeps YourGov subordinate to PublicWhip and does not address the user's clarified product direction.

Decision: reject.

### Option B: Remove PublicWhip From The UI Entirely

This would make the product feel first-party, but it weakens the evidence trail. The app's core value depends on showing what the public record supports.

Decision: reject.

### Option C: First-Party YourGov Panel With PublicWhip As Dropdown Source

This keeps YourGov as the product while preserving source transparency. It also allows the map to stay visible and keeps selected-division state centralized.

Decision: accept.

## Non-Goals For First Implementation

- Do not build a full replacement for PublicWhip.
- Do not remove PublicWhip routes.
- Do not rename package identifiers, database filenames, or env vars unless required by a public-facing change.
- Do not redesign the entire global feasibility view beyond brand copy and logo updates.
- Do not add country adapters in this stage.
- Do not infer MP motive, character, or corruption from votes.

## Risks And Mitigations

### Brand Confusion Risk

`YourGov` is close to other civic and polling brands. Before a broad public launch, run a separate naming, domain, and trademark review.

Mitigation for this stage: use clear disclaimers that YourGov is an independent civic transparency app and avoid official government visual language.

### Data Freshness Risk

The seed currently trails upstream Commons Votes data.

Mitigation: validation must report freshness and deployment docs must state when the seed was last refreshed.

### Map Payload Drift Risk

Multiple endpoints can drift if each builds payloads independently.

Mitigation: use one canonical payload builder and wrap legacy endpoints around it.

### Compiled Map Bundle Risk

The Promap bundle is compiled and may be hard to edit directly.

Mitigation: keep map data and selected-division logic in Flask and `panel_test.js`; use the relay API already exposed by `map_relay.html`.

## Acceptance Criteria

- `/source-lens` presents YourGov as the default first-party product.
- The map is visible beside the YourGov panel on desktop.
- PublicWhip is available from a source dropdown, not as the default product frame.
- Selecting a division updates the selected division state.
- Clicking Vote, Party, Gender, or Rebel keeps the same selected division.
- Each map mode sends a division-scoped payload to the map.
- Validation fails if any of the four mode payloads ignore `division_id`.
- Public UI copy says YourGov, not MyGov.
- The logo and favicon use YourGov assets.
- Tests and production validation pass before merge.

## Self-Review

- Placeholder scan: no TBD, TODO, or incomplete sections remain.
- Internal consistency: PublicWhip is retained as evidence, not removed.
- Scope check: this is one coherent production stage with three connected streams: layout, division-scoped data, and rename/validation.
- Ambiguity check: compatibility internals are explicitly preserved for this first migration while public-facing MyGov is removed.
