# Contributing to YourGov

YourGov is built **in public, and by the public**. If you can describe a change,
you can help make it — most contributors here work *with* a coding agent
(Claude, Codex, Cursor, and friends), and that's exactly who this guide is for.
You don't need to be a professional developer. You do need to bring a little
care, and this page shows you how.

The whole repo is set up to make this easy: it explains itself to your agent
(see [`AGENTS.md`](AGENTS.md) and [`docs/agent-guided-tour.md`](docs/agent-guided-tour.md)),
[`ARCHITECTURE.md`](ARCHITECTURE.md) maps how the parts fit together, and there's
a live list of things that need doing in [`docs/AGENT_TODO.md`](docs/AGENT_TODO.md).

## The short version

1. **Pick something small.** A task from [`docs/AGENT_TODO.md`](docs/AGENT_TODO.md)
   (look for `good-first`), a bug you hit, or a clear improvement. Small beats big.
2. **Branch off `main`.** Never commit straight to `main` — it's the live site.
3. **Make the change with your agent** — and then *read what it wrote* (see
   "Working with a coding agent" below).
4. **Run the tests**: `python -m pytest -q`. Keep them green.
5. **Open a pull request** with a short, plain-English description of what changed
   and how you checked it.

That's it. A maintainer reviews, and good changes get merged.

## Working with a coding agent (the careful bit)

Using an AI agent to write the change is welcome and encouraged. The one thing we
ask: **stay in the loop.** A few habits keep contributions safe and reviewable —
they're quick, and they're the difference between a PR that gets merged and one
that gets bounced:

- **Read the diff before you open the PR.** Skim every changed line. If you can't
  say what a change does in a sentence, ask your agent to explain it — or to make
  it simpler.
- **Keep it focused.** One change per PR. If your agent also "tidied up" ten other
  files, ask it to undo that and keep the PR to the actual task.
- **Run it.** Run the tests, and where you can, run the app (`python app.py`) and
  click the thing you changed. "The tests pass" plus "I saw it work" is a great PR.
- **Don't paste secrets.** No real API tokens, passwords, or personal data in code,
  commits, or examples — not even in a comment your agent suggested.
- **Don't deploy, and don't force anything.** Opening a PR is the finish line for a
  contributor. Merging and deploying are a maintainer's call.
- **When in doubt, ask in the PR.** "I'm not sure this is the right approach" is a
  perfectly good way to start a conversation.

## What we care about (project guardrails)

YourGov shows people what the public record *actually says*. Please don't break
that contract:

- **Source-led and factual.** Never infer an MP's intent, motivation, or character
  from a vote. Never imply a "best/worst MP" ranking.
- **Keep the caveats.** The distinction between *what the record shows*, *what it
  supports*, and *what it does not prove* must survive your change. Don't overclaim.
- **Accessibility is not optional.** Keep things keyboard-operable, labelled, and
  legible. We build accessibility natively — never bolt on an "accessibility
  widget"/overlay. See [`docs/accessibility`](docs/) notes.
- **Privacy by default.** No per-user tracking, no cookies for analytics, no
  collecting personal data without a clear reason.

## Pull request guidelines

A good PR is easy to review. Aim for:

- **A clear title** — what changes, in plain words (e.g. "Label the search input
  for screen readers", not "fix a11y").
- **A short description** covering: *what* you changed, *why*, and *how you checked
  it* (tests run, what you clicked). Link the `AGENT_TODO.md` item if there is one.
- **Small and scoped** — ideally one concern. Large PRs are fine when the task
  genuinely needs them; say so.
- **Green tests** — `python -m pytest -q` passes. New behaviour gets a test where
  it reasonably can.
- **No secrets, no unrelated churn, no reformatting-the-world.**

If a reviewer asks for changes, that's normal and not a judgement — it's how the
"built by anyone" approach stays trustworthy.

## Setup

```bash
pip install -r requirements.txt
python -m pytest -q        # run the tests
python app.py              # run the app locally (http://127.0.0.1:5050)
```

New here? The friendliest on-ramp is to let your agent take the
[guided tour](docs/agent-guided-tour.md) first — it'll come back able to explain
the project *and* help you make a solid first contribution.

Thank you for helping build civic transparency in the open.
