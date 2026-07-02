# Does Fable 5 earn its keep? A real-world security-review comparison against Opus 4.8

*A single-case field comparison on the YourGov codebase. Written 2026-07-02.*

---

## Abstract

We compare two Anthropic models — Opus 4.8 (incumbent) and Fable 5 (new) — on an
identical task: a security review of the "new surface" of the live YourGov Flask
application (first-party metrics, admin dashboard, two `after_request` HTML
injectors, the Explain-drawer client, and the unauthenticated
`/api/explain-selection` LLM endpoint). Opus 4.8's review is a frozen artifact
already in the project's history; Fable 5's review was run fresh, blinded to the
Opus output, using a matched multi-agent methodology. **Both models returned the
same top-line verdict — no exploitable vulnerabilities — with zero false
positives.** Fable 5 produced a materially more exhaustive artifact (more
line-level evidence, more documented adversarial probes, and it resolved the
three questions Opus left open). However, the comparison is heavily confounded —
most importantly, the author of this paper *is* the treatment model, the scope
was expanded using Opus's own open questions, and the codebase contains no
planted vulnerability, so the task cannot discriminate *detection* ability. We
report the result honestly as "Fable 5 is at least as capable here and writes a
more thorough report," not as a clean capability win, and propose a fairer
follow-up.

---

## 1. Background and question

YourGov is a production civic-transparency app. During its build, a 4-agent
"quality sweep" run on **Opus 4.8** (2026-06-30) included one dedicated security
agent that reviewed the then-new attack surface and concluded there were no
exploitable vulnerabilities. That report is preserved verbatim at
`scratchpad/quality-sweep/Audit__security-new-surface.md`.

The operator's question: **now that Fable 5 is available, does it "earn its keep"
on the same kind of work?** We treat this as a controlled-as-possible re-run.

## 2. Method

### 2.1 Baseline (control)
- **Model:** Opus 4.8.
- **Artifact:** `Audit__security-new-surface.md` (frozen; part of a 4-agent sweep in which security was **one** agent).
- **Verification stage:** none — the sweep's "security verdicts" array was empty because the finder raised no findings to verify.
- **Result:** no exploitable vulnerabilities; 8 `info`-level defence confirmations; **3 explicit "unknowns to confirm"** left out of scope (the skip-link injector, the `/api/explain-selection` server handler, and a duplicate `.agentwork` template copy).

### 2.2 Treatment
- **Model:** Fable 5 (per harness config; see Threat T1 — self-verification of model identity is not possible from inside the run).
- **Harness:** a 3-phase multi-agent workflow — **6 blinded finder agents** (one per surface) → **adversarial verification** of every candidate finding → **synthesis**. 7 agents total, ~326k tokens, 0 errors.
- **Blinding:** finder prompts forbade reading any prior audit / scratchpad file; each formed its verdict from source only.
- **Result:** no exploitable vulnerabilities; 0 candidate findings; 0 confirmed. Artifact: `Fable5__security-new-surface.md`.

### 2.3 Shared scope
Identical surfaces, expanded to *include the three items Opus flagged as unknown*
(see Threat T4 — this expansion is a confound). Same review methodology (the
built-in `security-review` rules: report only >80%-confidence exploitable vulns;
exclude DoS, rate-limiting, secrets-at-rest, and LLM-prompt-injection).

### 2.4 Run history
- **Fable 5 run #1: VOIDED.** The harness silently reverted Fable 5 → Opus 4.8 mid-session on a safeguard flag; provenance could not be trusted, so the run was quarantined, not used. This directly motivated the start-and-end model check in the protocol.
- **Fable 5 run #2:** the run reported here. Model confirmed at start (harness config) and no revert notice appeared through completion.

## 3. Results

### 3.1 Top-line verdict — a tie
| | Opus 4.8 | Fable 5 |
|---|---|---|
| Verdict | No exploitable vulns | No exploitable vulns |
| Confirmed findings | 0 | 0 |
| False positives raised | 0 | 0 |

On the headline security question the models **agree**, and neither produced a
false positive — the outcome that matters most for a review's trustworthiness.

### 3.2 Where Fable 5 went further (thoroughness, not verdict)
- **Resolved all three of Opus's "unknowns."** The skip-link injector (confirmed static-literal; the regex `\1` backreference only re-emits the page's own `<main>` bytes, app.py:144/162); the `/api/explain-selection` handler (full type-coercion + caps, role-injection blocked, cache-poisoning prevented); and the `.agentwork` template copy (out of serving path). Opus explicitly left these unreviewed.
- **Deeper evidence.** Fable 5 cited specific `file:line` for each defence (e.g. role-injection blocked at `explainer_context.py:397`; cache key injective at `:347`; constant-time gate at `app.py:2932`). Opus's citations were coarser and range-based.
- **Documented adversarial probe list.** Fable 5 recorded ~15 in-scope probes that found nothing (forged cross-origin postMessage, role injection via `messages[]`, cache-key collision, metadata SQLi, `escHtml` breakout attempts) **and** 7 out-of-scope probes correctly excluded (notably an **X-Forwarded-For rate-limit bypass** on the OpenAI-spending endpoint — a real control weakness, out of scope by category and already mitigated by a global daily budget). Opus's report listed confirmations but far fewer explicit attack attempts.

### 3.3 Where they were equal
Both correctly identified the load-bearing defence (Jinja autoescape closing the
stored-XSS path on attacker-controlled `event`/`path`), both confirmed
parameterised SQL and the constant-time fail-closed admin gate, both flagged
residual unknowns rather than over-claiming.

## 4. Threats to validity (read this before believing Section 3)

This is a field anecdote, not a controlled trial. The confounds are severe and
mostly favour the treatment:

- **T1 — Experimenter = treatment (the big one).** This paper, the experiment
  design, the scope, and the finder prompts were all authored by Fable 5, the
  model under test. Blinding the *finders* from Opus's output reduces
  finding-generation bias, but the framing, scope, and this write-up are not
  neutral. A self-graded exam.
- **T2 — Model provenance is unverifiable, and has already failed once.** No
  in-run check can prove which weights served which token; run #1 proved the
  provenance can silently break. We rely on the harness config label.
- **T3 — Unequal harness and compute.** Opus ran **1** security agent with **no**
  verification stage inside a general sweep; Fable 5 ran **6** dedicated finders +
  an adversarial verify + a synthesis (~326k tokens). More agents and more
  compute alone would make almost any model's *artifact* look more thorough. This
  is not a compute-matched comparison.
- **T4 — Scope was informed by the baseline's gaps.** Fable 5's scope was
  expanded (by the experimenter) to include exactly the three unknowns Opus left
  open. So "Fable 5 resolved Opus's unknowns" is partly *"Fable 5 was told to
  look there."* The finders were blind to Opus's *findings*, but the *scope*
  encodes Opus's *gaps*.
- **T5 — Different codebase state.** Opus reviewed the pre-hardening code; Fable 5
  reviewed HEAD `43cd9c2`, after a connection-manager migration and two 500
  hotfixes (themselves authored earlier in this session by the same model
  lineage). The target moved between control and treatment.
- **T6 — The task has no planted vulnerability, so it cannot test detection.**
  The codebase is genuinely clean. A null-result task rewards false-positive
  discipline and thoroughness of *confirmation*, but says little about which
  model would *catch a real bug the other missed* — the question operators most
  care about. Both models "passed a test with no wrong answers to avoid."
- **T7 — N=1 per model.** No repeats, no variance estimate. Model output is
  stochastic; a single run per arm cannot separate skill from sampling.

## 5. Interpretation — does it earn its keep?

**Honest answer: on this task, Fable 5 is at least as capable as Opus 4.8 and
produces a more exhaustive, better-evidenced security artifact — but this run does
not prove a capability *edge*, because the comparison is confounded (T1, T3, T4)
and the task cannot discriminate detection ability (T6).**

What we can say with reasonable confidence:
1. Fable 5 did not regress: same correct verdict, zero false positives, no
   hallucinated vulnerabilities — the failure mode that would disqualify a review
   model.
2. Fable 5's *output quality* (evidence specificity, probe coverage, resolving
   open questions) is higher here — though partly bought with more agents and a
   scope pointed at the gaps.
3. The one genuinely new substantive observation across both reviews — the XFF
   rate-limit bypass on the paid endpoint — surfaced in the Fable 5 run. It is
   out of the review's scope and already mitigated, so it changes no verdict, but
   it is the kind of thing a keen reviewer notes.

## 6. A fairer follow-up (recommended)

To actually measure capability rather than harness/scope:
1. **Plant known vulnerabilities.** Introduce 3–5 seeded bugs of varying subtlety
   on a scratch branch (e.g. a genuine `|safe` stored-XSS, an f-string SQL
   concat, a broken origin check). Detection rate becomes measurable.
2. **Match the harness and compute.** Same agent count, same verification stage,
   same token budget for both models. Same codebase HEAD.
3. **Neutral experimenter.** Have a third party (or a different model) design the
   scope and prompts, so neither competitor sets its own exam.
4. **Repeat (n≥3 per arm)** to estimate variance.
5. **Blind the judge to authorship** where format allows.

## 7. Judging

A neutral judge (ChatGPT, connected to the repo) scores both reports against the
code on: verdict correctness, true findings each caught that the other missed,
false-positive count, evidence specificity, coverage of the flagged unknowns, and
calibration. The judge prompt is in `JUDGE__chatgpt-task.md`. Cross-family judging
(a non-Anthropic model grading Anthropic models) reduces in-family bias; it does
not remove the authorship-format correlation (T1/T3).

## 8. Conclusion

Fable 5 cleared the bar and then some: identical correct verdict, no false
positives, and a more thorough artifact that closed the incumbent's open
questions. But the clean statement this experiment supports is narrow — *"Fable 5
is a safe, at-least-as-good replacement for Opus 4.8 on this review, and writes a
more exhaustive report"* — not *"Fable 5 is more capable at finding
vulnerabilities."* Proving the latter needs the seeded, compute-matched,
neutrally-designed rerun in Section 6. The most important artifact of this whole
exercise may be procedural: run #1's silent model revert is exactly why any such
comparison must verify provenance at both ends and quarantine what it cannot
trust.
```

Artifacts:
- Control: scratchpad/quality-sweep/Audit__security-new-surface.md (Opus 4.8, frozen)
- Treatment: scratchpad/fable5-security/Fable5__security-new-surface.md (Fable 5, blinded multi-agent)
- Voided: scratchpad/fable5-security/QUARANTINED__...security-run.md (run #1, provenance-broken)
- Protocol: scratchpad/fable5-security/EXPERIMENT-PROTOCOL__ready-to-run.md
```
