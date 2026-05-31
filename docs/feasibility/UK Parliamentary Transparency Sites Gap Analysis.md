# UK Parliamentary Transparency Sites Gap Analysis

## Executive summary

Across the three products, the market is not missing **parliamentary data**. It already has that in abundance. What is missing is a **trusted, voter-friendly judgment layer** that answers a simple set of questions: **What has my MP actually done? What have they said? How have they voted? Did that line up with promises? And how do they compare with other MPs?** TheyWorkForYou is the strongest public-interest record and alerting tool; TrackPolitics is the best attempt at plain-English interpretation and is the only one here doing manifesto-promise tracking; Parallel Parliament is the deepest monitoring stack, but it is clearly built for professional monitoring more than everyday voters. citeturn5view0turn5view1turn5view2turn8view0turn8view1turn19view0turn19view1turn20view0

The strongest gap is **not** “show me more documents.” It is “**help me understand the relationship between words, votes, promises, and outcomes**.” None of the three sites fully closes that loop. TheyWorkForYou tells you what happened in Parliament and how an MP voted; TrackPolitics makes some of that easier to read, but trust is weakened by visible freshness and methodology inconsistencies; Parallel Parliament can tell a professional almost everything happening around an MP, bill, or department, but a normal voter can still come away asking, “So… what does this mean?” citeturn5view3turn8view0turn8view1turn11view0turn19view0turn20view0

Public demand exists for exactly those missing layers. In indexed public discussions, people ask for simple explanations of party promises, use voting records to decide whether to back a candidate, complain that MPs seem inactive or unresponsive, question whether manifesto promises were kept, and explicitly search for quick vote lookups. The signals are clearest in Mumsnet and Bluesky results, while indexed Reddit/X evidence was comparatively weak in this crawl. citeturn31search2turn34search0turn34search1turn34search2turn31search0turn31search9turn24search0turn30search6turn36search0

## What the three sites already do

### TheyWorkForYou

TheyWorkForYou’s job is straightforward and still powerful: make parliamentary information easier to understand and easier to use. The site says it was founded to make Parliament more accessible and accountable, works across the UK’s parliaments, makes debates searchable, powers email alerts, and adds summaries such as voting-record summaries and more accessible registers of interests. Its MP pages make it easy to find speeches and questions, committees, APPGs, signatures, voting summaries, recent votes, declared interests, and a direct route to contact the MP via WriteToThem. It also supports postcode lookup, email alerts, API access, and raw data. citeturn5view0turn5view1turn5view2turn4view0

The user problem it solves is clear: official parliamentary sites are comprehensive but hard to navigate, so TheyWorkForYou turns them into a public-facing record of representation. It shows debates from the House of Commons back to the 1918 general election, MP data back to roughly 1806, voting summaries by policy area, recent votes, written answers, registers of interests, and recent parliamentary activity. On Alex Norris’s page, for example, the product surfaces role history, committee attendance, recent speeches and questions, signatures, voting summaries, interests, and a send-a-message button in one place. citeturn5view1turn5view2turn5view3

What it makes easy is the basics a normal voter actually needs: “Who represents me?”, “How have they voted on big issues?”, “What have they said?”, and “How do I contact them?” It also gets points for public-interest posture: independent, donation-supported, open source, with API and raw-data links visible. citeturn5view0turn4view0

What it makes difficult is the interpretive layer. Voting summaries are useful, but they still require users to understand party whipping, absences, procedural votes, comparison periods, and the difference between an MP’s personal beliefs and the parliamentary votes they cast. The site itself points users to explanations of its process, the votes it includes, and how it compares MPs with parties, which is honest and good — but also a tell that the model still needs explanation. Crucially, it does **not** answer “Did this lead to a real-world change?” or “Did this MP do what they said they would do?” citeturn5view3turn5view1

What is missing is side-by-side MP comparison, pledge tracking, said-versus-done analysis, and a simple “what actually mattered” view of parliamentary activity. There are also visible freshness quirks: the homepage surfaced recent votes in May 2026, but also highlighted voting summaries updated only to October 2025, and the recent-votes page itself showed current May 2026 votes while also displaying a “Last updated: 2025-09-10” footer line. That looks like a metadata or freshness mismatch, which is small in isolation but bad for trust. A normal voter could still leave understanding **what their MP said and how they voted**, yet still not know **whether the MP was effective, whether their promises were kept, or what any of those votes changed in practice**. citeturn3view3turn4view0

### TrackPolitics

TrackPolitics is the most explicitly product-shaped of the three. It positions itself as an independent, non-partisan platform that makes Parliament readable through voting records, bill tracking, and AI-powered plain-English summaries. It tracks MPs, bills, divisions, issue pages, party comparison, a political spectrum, and — most distinctively — a government promises tracker that maps manifesto commitments to statuses such as kept, in progress, or not started. It says it pulls official data from Parliament APIs and enriches it with AI summaries and topic classification. citeturn8view0turn8view1turn8view3turn9view0turn9view1

The user problem it solves is the “Parliament is public but unreadable” problem. Compared with the other two sites, it does the best job of turning votes and bills into plain-English, scannable interfaces. MP pages expose attendance, party loyalty, political-position estimates, voting patterns, notable positions, career roles, and financial-interest summaries. Bill pages give AI-generated “In Plain English” summaries, clearly labeled as AI-generated and possibly error-prone. Issue pages group votes into topics like housing and show timelines, bills, party positions, and recent related news. citeturn1view4turn10search10turn10search5turn11view0

What it makes easy is fast orientation. In seconds, a user can see roughly where an MP sits, whether they are party-loyal, whether they attend votes, how parties differ on an issue, what a bill is about, and what the government says it is delivering. Its “How Parliament Works” explainer also helps lower the comprehension barrier. This is the closest of the three to “Parliament for normal people.” citeturn6search1turn9view0turn8view0

But TrackPolitics is also where trust risk shows up most clearly. It says data is updated daily, yet on the promises page the footer says “Last updated February 2026,” while the crawl date was May 2026. AI-generated MP and bill summaries were also stamped “Generated 21 February 2026,” which makes some key explanatory layers feel like snapshots rather than continuously refreshed products. There are also count inconsistencies: the homepage showed 649 MPs tracked, while the About page said 650+ MPs and the MPs page said 650. That is not fatal, but it is the kind of product grit users notice when you are selling clarity and accountability. citeturn6search3turn8view0turn8view1turn6search2turn10search5turn1view4

What is missing is equally important. Promise tracking is only for the governing Labour manifesto; the site itself says opposition-party tracking is planned for a future update. There is no strong said-versus-done layer for an individual MP. Comparison is party-level rather than truly MP-vs-MP. The political spectrum is neat, but it is still a simplification. Issue pages blend parliamentary data with recent news in a way that is engaging but can feel a bit conceptually mushy. A normal voter may learn more quickly than on the other sites, but could still be unclear on **which votes were most consequential, whether AI classifications are fully reliable, how to compare MPs directly, and whether an MP’s public rhetoric matches their voting behavior**. citeturn8view1turn9view0turn11view0turn8view0

### Parallel Parliament

Parallel Parliament is the heavyweight monitoring product. Its homepage advertises live Commons and Lords transcripts, bill amendments with track changes, petitions, tweets, publications, written questions, debates, parliamentary research, APPGs, datasets, stakeholder targeting, and pricing. Its About page says it was founded in 2019 to unify scattered official political information and now serves MPs, trade organizations, charities, and local authorities through subscription services. The user guide describes it as an independent aggregator of UK parliamentary and governmental information, with hourly checks for many sources and large indexed archives across debates, bill documents, written questions, research, petitions, tweets, division votes, expenses, and financial interests. citeturn1view5turn1view6turn19view0turn19view1turn20view0

The user problem it solves is fragmentation. If you are a professional monitor — public affairs, campaigns, policy, trade associations, local government — this is catnip. The site makes it easy to follow a bill across stages, inspect amendments, monitor departments, search across diverse source types, set immediate/daily/weekly alerts, download datasets, build PDF packs, and even identify stakeholders relevant to an issue. MP pages bundle role history, APPGs, alerts, debates by department and legislation, division-vote history, petition activity in the constituency, financial disclosures, and expenses. citeturn19view0turn17view0turn19view1turn20view0

What it makes easy is **monitoring**, not **understanding**. That is the key distinction. It gives serious users a lot of connected information, a lot of it updated very frequently, and the amendment-tracking capability is genuinely differentiated. For legislation and public-affairs work, this is the most feature-rich of the three by a distance. citeturn18view2turn19view0turn20view0

What it makes difficult is being an ordinary voter. The entire commercial frame — pricing tiers, alert quotas, stakeholder targeting, PDF packs, enterprise users, notes, dataset downloads — tells you who the primary customer is. The interface is dense. The taxonomy is broad. The free site is useful, but much of the high-leverage workflow is paywalled or subscription-oriented. There is very little simple judgment for a voter who wants a plain answer such as “Is my MP active?”, “Do they back what they claim to back?”, or “How do they compare with my neighbors or with their party peers?” citeturn19view1turn20view0turn15view0

What is missing is not depth. It is prioritization and translation. Parallel Parliament has tons of evidence, but very little voter-facing synthesis. A normal voter could absolutely find out a lot here — including petitions in their constituency, division voting, debates, APPGs, previous appointments, and alertable activity — yet still not understand **what matters most, what changed because of it, or how this MP compares on trust, delivery, and consistency**. citeturn17view0turn19view0

## Where the gap is

All three products are strong on **recording parliamentary behavior**. All three are weaker on **explaining political accountability in a way normal voters can use quickly**. The difference is mostly one of emphasis: TheyWorkForYou is strongest on public-service transparency, TrackPolitics is strongest on accessibility and narrative packaging, and Parallel Parliament is strongest on monitoring depth and professional workflows. citeturn5view0turn8view0turn19view0

The common blind spot is that parliamentary inputs are not the same as voter decisions. Voters do not mainly need another feed of debates or another bill list. They need a reliable answer to a cross-source question: **What did this person say they believed, how did they vote when it mattered, what did they actually prioritize, and what has happened since?** None of the three products fully provides that end-to-end accountability layer. citeturn5view3turn8view1turn17view0

| Gap | Evidence across the three sites | Product implication |
|---|---|---|
| **Words versus actions** | TheyWorkForYou separates speeches and votes but does not join them into a consistency view; TrackPolitics summarizes positions from voting records but does not robustly reconcile them with speeches or claims; Parallel Parliament exposes speeches, votes, petitions, and alerts, but mostly as monitoring objects rather than a single verdict. citeturn5view2turn5view3turn8view0turn17view0 | Biggest opportunity: a “said vs voted vs delivered” layer. |
| **Promise tracking below government level** | TrackPolitics has the only built-in promises tracker here, but it covers the governing Labour manifesto only and says opposition-party tracking is planned later; TheyWorkForYou and Parallel Parliament do not provide per-MP pledge tracking. citeturn8view1turn19view0turn5view2 | Strong white space for MP-level pledge/commitment tracking. |
| **Direct MP comparison** | TheyWorkForYou surfaces one MP at a time; TrackPolitics has party comparison and party heatmaps but not a strong MP-vs-MP compare product; Parallel Parliament offers rich MP pages but not a clean comparison experience for voters. citeturn5view2turn9view0turn17view0 | Fast MVP wedge: “compare my MP with 2–3 others.” |
| **Which activity actually mattered** | TheyWorkForYou shows large amounts of activity and summaries; TrackPolitics distinguishes some key votes and procedural votes, but practical significance still requires user interpretation; Parallel Parliament is especially rich but even more volume-heavy. citeturn5view3turn8view3turn17view0 | Need consequence-first ranking of speeches, votes, and bills. |
| **Freshness confidence** | TheyWorkForYou displayed a visible freshness mismatch on voting summaries and recent-votes metadata; TrackPolitics showed multiple February 2026 timestamps while claiming daily updates; Parallel Parliament’s update model is clearest and strongest. citeturn3view3turn4view0turn8view1turn10search5turn20view0 | Build visible freshness/confidence labels into every insight. |
| **Constituency-facing accountability** | TheyWorkForYou offers contact routes and some constituency links; TrackPolitics is mostly Westminster-data-first; Parallel Parliament shows constituency petitions and MP information, but not a simple “how active are they for my area?” layer. citeturn5view2turn8view0turn17view0 | Opportunity for a local relevance layer, not just Westminster activity. |
| **Overserved feature area** | Parallel Parliament in particular goes deep on alerts, PDFs, datasets, enterprise notes, and stakeholder targeting; all three already provide plenty of raw document and activity access. citeturn19view1turn20view0turn4view0 | Do **not** start by cloning monitoring infrastructure. |

## Social search terms to test demand

These terms are based only on the gaps above.

| Platform | Search terms | What each query is testing |
|---|---|---|
| **Reddit** | `site:reddit.com "how did my MP vote"` | Quick vote lookup demand |
|  | `site:reddit.com "what has my MP actually done"` | Activity/impact demand |
|  | `site:reddit.com "my MP said" voted` | Said-vs-done demand |
|  | `site:reddit.com "compare MPs" voting record` | MP comparison demand |
|  | `site:reddit.com manifesto promises tracker UK` | Pledge-tracking demand |
| **X / Twitter** | `site:x.com "how did my MP vote"` | Instant lookup demand |
|  | `site:x.com "kept promises" Labour OR Conservatives` | Promise-accountability demand |
|  | `site:x.com "what has my MP done"` | Activity frustration |
|  | `site:x.com "why is this hard to understand" parliament` | UX frustration |
| **Bluesky** | `site:bsky.app/profile "how did your MP vote"` | Vote-explainer demand |
|  | `site:bsky.app/profile "track record re keeping promises"` | Promise skepticism |
|  | `site:bsky.app/profile "cannot find anything about" councillor OR MP` | Discoverability gap |
|  | `site:bsky.app/profile "what has my MP done"` | Accountability demand |
| **Google / forums** | `"what has my MP actually done" UK` | Broad public language test |
|  | `"how did my MP vote" UK` | Mass-market search behavior |
|  | `"compare MPs voting record"` | Comparison wedge |
|  | `"manifesto promises tracker UK"` | Pledge-tracker wedge |
|  | `"why is parliament hard to understand"` | Simplification wedge |
| **YouTube / comments / forums** | `site:youtube.com/watch "how did my MP vote"` | Video-led explainer demand |
|  | `site:mumsnet.com "what each party is offering/promising"` | Voter confusion in community forums |
|  | `site:mumsnet.com "voting record" MP` | Candidate evaluation via behavior |

## Evidence that people want the missing pieces

The clearest public-demand signal in this research is **confusion plus accountability hunger**. One Mumsnet user asked for someone to “please explain” what each party is offering or promising because they had “no idea who to vote for,” and later said the thing they were lost over was that parties’ figures differ massively. That is a direct demand for a simpler, more trustworthy explanation layer — not just raw manifestos. citeturn31search2turn34search1

There is also direct evidence that people want to judge **individual representatives**, not just parties. In a Mumsnet discussion about whether to vote for the party or the candidate, multiple users said their local MP’s voting record materially affected their decision, and another user explicitly recommended looking up individual voting records on TheyWorkForYou. That is strong evidence for “compare MPs” and “what did my MP actually do?” rather than another generic politics explainer. citeturn34search0turn35search1

The demand is not purely electoral. There is also frustration about **activity and responsiveness**. In another Mumsnet thread, users complained that MPs failed to respond, “don’t really do much,” and “don’t even turn up to most of the votes,” with the original poster saying the country needs “better accountability for our representatives.” That is almost a perfect statement of the product need. citeturn34search2

Promise tracking also shows up as a live public concern. A Mumsnet poster argued that manifesto promises had been broken “left, right and centre” and linked to Full Fact’s government tracker; another older but still relevant thread was explicitly angry that a policy change happened “despite Tory manifesto promise”; and a Bluesky post complained that Labour’s “track record re keeping promises” made its commitments hard to trust. People are clearly looking for ways to check whether promises survive contact with power. citeturn31search0turn31search9turn30search6

The “quick answer” demand exists too. A Bluesky result from MP Watch asked, “How did your MP vote on controversial measure on disability? Find out here,” which shows there is an audience for immediate, plain-English, issue-specific vote lookup. Another Bluesky snippet showed a user saying they had tried looking into their new elected representative and “cannot find anything about him anywhere,” which speaks directly to discoverability and comparable profile quality. citeturn24search0turn36search0

The pattern is pretty blunt: people are asking for **simple explanations, visible records, promise accountability, and easier person-level evaluation**. They are not asking for another 1,500-item document list or an hourly parliamentary alerting stack. citeturn31search2turn34search0turn34search2turn24search0turn36search0

## What to build first

### Strongest unmet need

The strongest unmet need is a **voter-trust layer that connects claims, votes, and outcomes for one representative**. In plain English: “What did my MP say, how did they vote, what did they prioritize, and did any of it add up?” That is the one question none of the three sites answers well end to end. citeturn5view3turn8view1turn17view0

### Best MVP wedge

The best MVP wedge is a **single-page MP accountability brief** rather than a full parliamentary platform. The page should be built around one primary promise to the user: **“In two minutes, understand your MP.”** It should show only a few things, but show them ruthlessly well:

A good first version would include the MP’s most consequential votes, the clearest public claims or stated positions, an activity snapshot with context, a simple promise/commitment tracker where evidence exists, and a comparison view against party average and a small peer set. The killer feature is not AI flavor text. It is a **verifiable “said / voted / delivered” strip with source links**.

That wedge is faster than trying to replicate TheyWorkForYou’s archive, TrackPolitics’ full topic model, or Parallel Parliament’s monitoring engine. It also attacks the exact under-served space: interpretation, comparison, and trust.

### Features to avoid copying

Do not copy the parts of the existing market that are already crowded or misaligned with voter use. The main traps are **enterprise alerting**, **huge raw-document inventories**, **stakeholder-targeting workflows**, and **opaque AI summaries without evidence trails**. Parallel Parliament already owns the monitoring-heavy end of the market; trying to out-Parallel-Parallel Parliament would be expensive and strategically daft. TrackPolitics also demonstrates the trust risk of visible AI plus visible timestamp inconsistencies. citeturn19view1turn20view0turn8view0turn8view1

### Features worth copying but simplifying

There are several things worth stealing shamelessly — then simplifying hard. From TheyWorkForYou: postcode-to-MP lookup, policy-area vote grouping, direct source links, and email-alert logic. From TrackPolitics: plain-English bill and MP framing, issue pages, and a promise-tracking instinct. From Parallel Parliament: strong connection between related entities — MP, bill, department, petitions, debates, amendments — and visible freshness cues. citeturn5view2turn5view3turn8view0turn8view1turn19view0turn20view0

### Recommendation

Build **“My MP, decoded”** first.

That product should not try to be the source of record for everything. It should be the source of record for the **one user journey voters keep revealing they want**: “Help me decide whether this person deserves my trust.” If you nail that, you can later expand outward into compare pages, issue pages, weekly digests, or party-level accountability.

The recommended first-build scope is therefore:

- one clean MP page
- said / voted / delivered summary
- five consequential actions, not fifty
- side-by-side comparison with a small peer set
- explicit freshness and confidence markers
- source-first design, so users can drill into evidence without drowning in it

That is the narrowest build that attacks the strongest unmet need while staying defendable against the three incumbents.

## Confidence and limitations

**Confidence score: 78/100.** The score is fairly high because the site audit is based on direct review of the three products’ public pages, feature descriptions, and example MP/bill pages, so the existence, positioning, and obvious strengths/weaknesses are grounded well. It is not higher because the public-demand step is less complete on native social platforms than I would like: the strongest indexed evidence in this pass came from Mumsnet and Bluesky snippets, while indexed Reddit and X results were relatively sparse or noisy. That means the **direction of demand** is clear, but the **volume by platform** should be treated as provisional. citeturn5view0turn8view0turn19view0turn31search2turn34search0turn34search2turn24search0turn36search0

The main open question is not whether the gap exists. It does. The open question is whether the sharper initial wedge should be **said-versus-done for MPs** or **promise tracking for parties/government**. On the evidence here, the safer first bet is the MP-level trust brief, because it is narrower, easier to verify, and more directly aligned with the recurring public questions surfaced in the indexed discussions. citeturn34search0turn34search1turn34search2turn31search0