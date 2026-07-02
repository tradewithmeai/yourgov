# ChatGPT-as-judge — task setup

Goal: an independent, cross-family judge (ChatGPT, connected to the `yourgov`
repo) evaluates the two security reviews **against the actual code** — verifying
claims, not grading prose — and says which review it would trust and whether the
newer model earns its keep.

Why cross-family: a non-Anthropic judge grading two Anthropic models removes
in-family bias. It does **not** remove the fact that the two reports differ in
format/verbosity in ways that hint at authorship — so the prompt tells the judge
to **verify against ground truth (the code)**, which is the part that can't be
faked, and to ignore style.

---

## How to wire it up

1. Connect ChatGPT to the repository `tradewithmeai/yourgov` (GitHub connector),
   at commit **`43cd9c2`** (or `main` if unchanged). The judge needs to read the
   code — that is the ground truth.
2. Point the judge at the two review files, committed next to this one:
   - **Review A** = `docs/experiments/security-model-comparison/review-A.md`
   - **Review B** = `docs/experiments/security-model-comparison/review-B.md`
   - For a BLIND judge, give it ONLY `review-A.md`, `review-B.md`, this
     `JUDGE-TASK.md`, and the repo code. Do **NOT** give it `COMPARISON.md` or
     `README.md` — they reveal which model authored which review. The A/B→model
     mapping is in a private answer key kept outside the repo.

---

## Paste this as the ChatGPT task prompt

> You are an independent senior application-security engineer. Two AI systems each
> produced a security review of the same code: the "new surface" of a Flask app in
> the connected repository `yourgov` at commit 43cd9c2 — specifically:
> - the unauthenticated `POST /api/telemetry` metrics beacon + its storage/aggregation and the `/admin/metrics` dashboard (`app.py`, `templates/admin_metrics.html`),
> - the two `after_request` HTML injectors `_inject_feedback_link` / `_inject_skip_link` (`app.py`),
> - the Explain-drawer client (`static/explain-mode.js`),
> - the unauthenticated `POST /api/explain-selection` LLM endpoint and its helpers (`app.py`, `explainer_context.py`).
>
> I will give you **Review A** and **Review B**. Do NOT take either at face value.
> Your job is to VERIFY them against the actual code and judge their quality.
>
> Do this:
> 1. **Independently form your own verdict first.** Read the code in scope and
>    decide: are there exploitable vulnerabilities (SQL injection, stored/reflected/DOM
>    XSS, auth bypass, RCE/deserialization, SSRF controlling host/protocol, path
>    traversal from request input)? Apply the standard exclusions (denial-of-service,
>    rate-limiting/resource-exhaustion, secrets-at-rest, and untrusted-text-into-an-LLM-prompt
>    are out of scope). Write your own findings before reading either review in detail.
> 2. **Verify each review against the code.** For every material claim in A and B
>    (each "defense confirmed" and any finding), check it at the cited `file:line`
>    and mark it: CORRECT / INCORRECT / UNVERIFIABLE. Note any claim that is wrong
>    or overstated.
> 3. **Check for misses.** Does either review miss a real, in-scope vulnerability
>    that YOU found in step 1? Does either raise a false positive?
> 4. **Score each review (1–5)** on: (a) verdict correctness, (b) true-positive
>    completeness, (c) false-positive discipline, (d) evidence specificity /
>    verifiability against the code, (e) coverage (did it review the whole surface,
>    including the injectors and the `/api/explain-selection` handler), (f)
>    calibration (does it distinguish confirmed defenses from residual unknowns
>    without over-claiming).
> 5. **Judge style-blind.** Ignore length, formatting, and any self-referential /
>    provenance lines. Grade only security substance verified against the code.
>
> Output:
> - Your own independent verdict (vuln / no-vuln) with any findings.
> - A table: claim-verification summary for A and B (counts of correct / incorrect / unverifiable).
> - The 6 scores per review, with one-line justifications.
> - **Which review would you trust for a production go/no-go, and why.**
> - Anything BOTH reviews missed.
> - Your confidence, and what would raise it (e.g. a seeded-bug rerun).

---

## Reading the judge's answer (for the operator)

- If the judge **independently agrees "no exploitable vulns"** and finds both
  reviews' claims CORRECT against the code, that validates both models and the
  verdict — the strongest possible outcome for a null-result task.
- The discriminating signals are (c) false-positive discipline, (d) evidence
  specificity, and (e) coverage — that's where the two reviews actually differ.
- **Caveat to keep in mind:** the code has no planted bug, so even a perfect judge
  can't measure *detection* skill here. To test that, run the seeded-vulnerability
  follow-up in the comparison paper (§6) and re-judge.
