# Explainer Cost Guards

`/api/explain-selection` is unauthenticated and calls OpenAI per request, so it
is the one real cost risk in the app. Three guards protect it, and **every one
degrades to the safe non-LLM fallback envelope** — never an error, never an
unbounded bill. Implemented in `app.py` (`explain_selection` + the
`_explainer_*` helpers) with pure helpers in `explainer_context.py`.

## The three layers

1. **Cache** (`selection_cache` table). Opening-turn clicks — no follow-up, no
   prior conversation — are deterministic, so the answer is cached in SQLite and
   served for **$0** on repeat. For a **division click the key is
   `(level, division_id, vote fingerprint, element-type)`** — not the free-text
   click — so every user clicking the same division shares one cached answer, and
   an attacker cannot force endless cache misses by mutating the text (misses are
   bounded to real divisions). The vote fingerprint means a corrected division
   auto-invalidates its cached explanation. Follow-ups are conversation-dependent
   and never cached (but are still rate/budget limited).
2. **Per-IP rate limit** (in-process sliding window). Per-minute and per-day caps
   per client IP (first `X-Forwarded-For` hop). Over-limit → fallback. The IP map
   is bounded (`_prune_ip_store`) so a spoofed-IP flood can't exhaust memory.
3. **Global daily budget** (`explainer_budget` table). A hard ceiling on total
   LLM calls per UTC day, persisted in SQLite (shared across Passenger workers,
   survives worker respawns; atomic reserve via
   `INSERT … ON CONFLICT DO UPDATE … WHERE count < budget`). This is the real
   backstop against distributed abuse, since `X-Forwarded-For` is spoofable.

Order per request: **cache hit → (free) return**; else **per-IP rate → budget →
OpenAI**. Cache hits, rate-limited requests, and the no-API-key path never charge
the budget. If the guard DB is unreachable the request fails **cost-safe** to the
fallback.

## Tunable env vars (set on Krystal; restart to apply)

| Variable | Default | Meaning |
|---|---|---|
| `EXPLAINER_DAILY_BUDGET` | `2000` | Max LLM calls per UTC day (the hard cost ceiling). |
| `EXPLAINER_RATE_PER_MIN` | `10` | Max LLM calls per client IP per minute. |
| `EXPLAINER_RATE_PER_DAY` | `100` | Max LLM calls per client IP per UTC day. |
| `EXPLAINER_CACHE_TTL_SECONDS` | `604800` (7d) | Opening-turn cache lifetime; `0` = no expiry. |
| `EXPLAINER_IP_STORE_CAP` | `20000` | Max distinct IPs tracked in memory before pruning. |
| `MAX_CONTENT_LENGTH` | `262144` (256 KB) | Max request body (global); blocks oversized payloads. |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model id (one-line swap to a Claude model later). |

Per-call **output** tokens are capped per level (`_SELECTION_MAX_TOKENS` =
160/260/400/600 for levels 0–3), sized for the JSON envelope, so each LLM call has
a bounded cost and the daily budget maps to a tight dollar ceiling.

To make the explainer cheaper later: lower `EXPLAINER_DAILY_BUDGET`, keep the
cache TTL high. To raise quality regardless of cost: raise the budget and/or
change `OPENAI_MODEL`.

## Notes / accepted limits

These were surfaced by an adversarial review and accepted because each is bounded
to a *few multiples* of the budget (never an unbounded bill), and the per-call
token cap keeps even that cheap:

- **Budget reset on redeploy / UTC midnight.** The counter lives in the wipeable
  `/tmp` DB and is keyed on the UTC calendar day, so a redeploy (≈daily) or a
  23:59→00:00 straddle can grant an extra day's budget. Redeploys are
  operator/cron-controlled (matching the daily intent); persisting the counter
  outside `/tmp` would need infra the host may not offer.
- **Per-IP limit is XFF-spoofable.** An attacker rotating `X-Forwarded-For` can
  drain the shared daily budget — a denial-of-service (everyone then gets the safe
  fallback), **not** extra spend, since the global budget still caps dollars.
- **Verified sound:** the budget counter is atomic and race-free even across
  concurrent Passenger workers (never over-counts), and every guard failure —
  including a genuine OpenAI error or a hostile/wrong-typed request body —
  degrades to the safe fallback envelope (HTTP 200), never a raw 500.
