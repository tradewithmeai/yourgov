# Experiment: security-review model comparison

A real-world, single-case comparison of two AI models on the **same** security
review of YourGov's "new surface" (metrics beacon + admin dashboard, the two
`after_request` HTML injectors, the Explain-drawer client, and the unauthenticated
`/api/explain-selection` LLM endpoint).

## Files
- **`review-A.md`**, **`review-B.md`** — the two security reviews, anonymised
  (model identity stripped) so a judge can score them blind. Same verdict: no
  exploitable vulnerabilities, zero false positives.
- **`JUDGE-TASK.md`** — a prompt for a neutral judge (e.g. ChatGPT connected to
  this repo) to **verify each review's claims against the code** and score them.
- **`COMPARISON.md`** — the full write-up (method, results, threats to validity,
  a fairer follow-up design). **Reveals which model wrote which review** — read it
  only *after* judging, and do not feed it to a blind judge.

## ⚠️ Blindness
For an unbiased judge, provide it only `review-A.md`, `review-B.md`, `JUDGE-TASK.md`
and the repo code. `COMPARISON.md` and this `README.md` disclose the A/B→model
mapping. The mapping itself is kept in a private answer key outside the repo.

## The honest caveat (see COMPARISON.md §4, §6)
The codebase has **no planted vulnerability**, so this experiment tests
false-positive discipline and thoroughness of confirmation — not the ability to
*detect* a real bug one model would catch and the other miss. Both reviews
correctly returned "no exploitable vulns." To measure detection capability, run
the seeded-vulnerability, compute-matched, neutrally-designed rerun described in
`COMPARISON.md` §6.
