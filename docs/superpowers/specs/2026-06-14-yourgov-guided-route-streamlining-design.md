# YourGov Guided Route Streamlining Design

**Date:** 2026-06-14
**Status:** Ready for user review

## Goal

Make the advertised YourGov journey obvious and frictionless without changing the core layout or interaction model.

The campaign route is:

1. User lands on the global map.
2. User clicks the United Kingdom.
3. User enters YourGov.
4. User searches by postcode, constituency, or MP name.
5. The left YourGov panel opens that MP's voting record.
6. User single-clicks a division to show the national vote visualisation on the map.
7. User double-clicks a division to open the division summary.
8. User can use Explain Mode to understand the selected MP, division, map, and visible data.

## Product Framing

The public product is YourGov.

The current implementation may continue to use internal route and file names such as `/source-lens`, `panel_test.html`, and `panel_test.js`, but user-facing language should not describe the experience as "local lens" or "Source Lens". Public copy should describe one YourGov journey:

> Find your MP. See how they voted. Understand the public record.

## Current Layout

Do not redesign the layout.

The accepted layout is:

```text
+--------------------------------+--------------------------------+
| YourGov panel                  | Map panel                      |
| left side                      | right side                     |
|                                |                                |
| Search                         | UK constituency map            |
| MP voting record               | Selected division visualised   |
| Division rows                  | Vote / Party / Gender / Rebel  |
| Explanation controls           | Legend and selected context    |
+--------------------------------+--------------------------------+
```

The left panel is the YourGov surface. The right panel is the map. The map should stay visible on desktop while the user searches, selects an MP, clicks divisions, changes map mode, and uses explanations.

## Existing Interaction Model To Preserve

The current model remains:

- Search finds an MP, constituency, or postcode.
- Selecting an MP opens that MP's YourGov voting record in the left panel.
- The voting record lists divisions the MP voted on.
- Single click on a division visualises that national division vote on the right-hand map.
- Double click on a division opens the division summary in the existing destination.
- The four visualisation controls stay scoped to the selected division.

This stage should streamline and clarify those behaviours, not replace them.

## Problems To Fix

### Users Do Not Understand The App Quickly Enough

People should understand the app within a few seconds. The current UI has working pieces, but the route is not explicit enough for a cold visitor arriving from social media.

### Search Intent Is Undersold

The campaign promise depends on "find your MP". The search needs to say clearly that postcode, constituency, and MP name are accepted.

### Division Rows Need Stronger Affordance

The most important interaction is not obvious enough:

- single click maps the vote;
- double click opens the division summary.

Rows should say this directly and provide hover, focus, and selected-state feedback.

### Map Context Needs To Stay Attached To The Selected Division

The right-hand map must always tell the user what they are looking at:

- selected MP if one is active;
- selected division;
- active visualisation mode;
- what the colours mean;
- what the data can and cannot prove.

### Explain Mode Needs Better Product Context

Explain Mode should explain YourGov and the user's visible route, not just generic parliamentary terms. It should use the clicked item, the selected MP, the selected division, visible summary text, and available source metadata.

## Design

### Entry From Global Map

When the user clicks the UK on the global map, they should enter the YourGov UK experience. The next page should not feel like a different product.

The entry copy should make the next action explicit:

> You are in YourGov UK. Search by postcode, constituency, or MP name to see your MP's voting record.

Implementation can keep routing through `/source-lens?source=lens&cc=GB&lang=en`, but the rendered public copy should say YourGov.

### Left Panel Hero Copy

The left panel should open with a short route explanation:

> Find your MP. Click a vote to colour the national map. Double click for the division summary.

This text should remain short. It is an instruction, not a marketing paragraph.

### Search

The search label should be clear:

> Search by postcode, constituency, or MP name

Placeholder:

> e.g. SW1A 1AA, Tottenham, or David Lammy

Search results should show:

- MP name;
- party;
- constituency;
- whether selecting this result will open the MP voting record.

When postcode lookup fails, show a useful next action:

> We could not match that postcode. Try the constituency name or your MP's name.

When there are multiple text matches, show enough information to choose between them without leaving the page.

### MP Voting Record State

After an MP is selected, the left panel should clearly switch to that MP's record.

Header copy:

> Voting record for [MP name]

Supporting copy:

> These are recorded House of Commons divisions in the YourGov dataset.

Show the constituency and party near the MP name. If a contact link exists in this stage, keep it secondary. The contact/email feature is not part of this implementation stage.

### Division Rows

Each division row should include:

- division title;
- date;
- the MP's vote;
- Aye/No totals where available;
- visible instruction text or compact action labels:
  - `Click to map`;
  - `Double click for summary`.

Single click behaviour:

- updates selected division state;
- loads the national map visualisation for that division;
- applies the current map mode;
- marks the row selected;
- updates map status and legend.

Double click behaviour:

- opens the division summary using the existing destination;
- does not break the single-click map contract;
- preserves enough context for the user to return or understand what was opened.

Keyboard behaviour:

- Enter on a focused row should perform the primary action: map the vote.
- A visible secondary link or button should open the summary for keyboard and touch users, because double-click is not accessible on all devices.

### Map Panel Context

The map panel should make the current state explicit.

Minimum visible context:

- selected division title;
- selected MP vote if an MP is active and the MP has a record for the division;
- active mode: Vote, Party, Gender, or Rebel;
- legend tied to the active mode.

Example status:

> Showing how MPs voted nationally on [division title]. [MP name] voted [Aye/No/Absent].

When no MP is selected:

> Search for your MP on the left, then click a vote to map it here.

When no division is selected:

> Choose a division from the MP voting record to colour the map.

### Four Map Controls

Keep the four controls and their existing intent:

- Vote;
- Party;
- Gender;
- Rebel.

They must remain scoped to the selected division. The UI should explain this near the controls or in status text:

> These views all use the selected division. They show the same vote in different ways.

### Explain Mode

Explain Mode should stay in the same general pattern, but the prompt and collected context need to better reflect the YourGov journey.

Context supplied to the explainer should include where available:

- current product surface: YourGov;
- current route;
- selected MP id, name, party, and constituency;
- selected division id, title, date, MP vote, Aye count, No count;
- active map mode;
- clicked element text;
- row or panel surrounding text;
- source links;
- map caveat text.

The explainer should be able to answer:

- what the user clicked;
- what the public record shows;
- what the map colours mean;
- what the selected MP did on this division;
- what this does not prove.

The explainer must not infer motive, character, corruption, or intent.

### Source And Summary Behaviour

The existing double-click division summary behaviour should remain. The summary should be treated as a deeper evidence view, not a separate product route.

If the summary opens in the left panel, preserve the map on the right.

If the summary opens as a contained source view or page, use copy that explains:

> This is the division summary for the vote you selected.

### Error And Empty States

Every empty state should tell the user what to do next.

Required states:

- no search entered;
- postcode not found;
- no MP match;
- selected MP has no loaded divisions;
- division map payload failed;
- map iframe not ready;
- Explain Mode service unavailable.

Each state should avoid blame and avoid implying missing data means an MP did nothing.

## Out Of Scope For This Stage

Do not implement the first-party "write to your MP" feature in this stage.

Do not scrape MP email addresses in this stage.

Do not draft emails from explainer chat history in this stage.

Do not replace the current layout.

Do not rename internal route and file identifiers unless required for public copy.

Do not redesign the global map beyond ensuring the UK entry sends users into YourGov cleanly.

## Future Stage: Contact Your MP

The next major stage can bring the WriteToThem concept into YourGov.

Likely direction:

- use only official public MP contact details;
- store source provenance for each contact;
- show clear privacy and safety warnings;
- draft an email from the user's selected MP, selected division, and explainer chat context;
- require the user to edit and explicitly send;
- avoid automatic sending or hidden background delivery;
- keep all generated wording factual and source-bound.

This requires a separate security and abuse review because it involves contact data, user-authored messages, and possible email delivery.

## Future Stage: Richer Explainer Chat

The explainer can later become a fuller chat assistant.

Likely additions:

- persistent in-session chat history;
- "draft an email from this discussion" action;
- stronger source citations;
- division summary ingestion;
- current visible screen context;
- YourGov help knowledge so it can explain how to use the site.

This should follow the guided-route streamlining because the explainer needs stable user state to work well.

## Validation

Implementation should add or update tests that prove:

- `/` or the campaign entry reaches the global map and UK click enters YourGov.
- The YourGov page uses public YourGov copy, not Source Lens language for the main journey.
- Search copy explicitly supports postcode, constituency, and MP name.
- Selecting an MP shows an MP voting record in the left panel.
- Division rows expose single-click map behaviour and double-click summary behaviour.
- Single click calls the selected-division map payload path.
- Double click opens the summary path.
- The four map modes keep the selected division.
- Explain Mode requests include selected MP, selected division, active map mode, clicked text, and surrounding context.
- Empty states contain next-action copy.

## Acceptance Criteria

- A cold user can understand the campaign route from the first YourGov page without prior political knowledge.
- The left panel remains YourGov and the right panel remains the map.
- The MP voting record is the central left-panel view after search.
- Single-click division visualisation is discoverable and tested.
- Double-click division summary is discoverable and tested.
- Map context clearly identifies the selected division and active mode.
- Explain Mode is seeded with enough YourGov state to explain the visible screen.
- Email/contact functionality is documented as a future stage, not mixed into this first stage.

## Self-Review

- Placeholder scan: no placeholder markers or incomplete sections remain.
- Internal consistency: the spec preserves the existing layout and interaction model throughout.
- Scope check: this stage is limited to streamlining the guided YourGov route; contact/email and richer chat are future stages.
- Ambiguity check: single-click and double-click behaviours are explicit, including the accessible alternative for double-click.
