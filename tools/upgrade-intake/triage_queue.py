"""
Append-only triage CLI for the upgrade queue.

A human decides what to do with a queued item and records the decision by
APPENDING a new line with the SAME `id` and an updated status. Existing lines
are never edited — the audit trail of who decided what, when, is preserved.

Commands:
    python triage_queue.py accept      <id-prefix> --reason "..." [--by NAME]
    python triage_queue.py reject      <id-prefix> --reason "..." [--by NAME]
    python triage_queue.py defer       <id-prefix> --reason "..." [--by NAME]
    python triage_queue.py junk        <id-prefix> --reason "..." [--by NAME]
    python triage_queue.py implemented <id-prefix> --reason "..." [--by NAME]
    python triage_queue.py reviewed    <id-prefix> --reason "..." [--by NAME]

The new line copies every field of the latest record forward (so it stays
schema-complete) and overrides status / decision_reason / decided_at /
decided_by. This tool never executes message text and never touches the repo
beyond appending one line.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from typing import Any

import core

DECISIONS = {
    "accept": "accepted",
    "reject": "rejected",
    "defer": "deferred",
    "junk": "junk",
    "implemented": "implemented",
    "reviewed": "reviewed",
}


def build_decision_record(latest: dict[str, Any], status: str, reason: str, by: str) -> dict[str, Any]:
    rec = dict(latest)  # copy all fields forward -> schema-complete
    rec["status"] = status
    rec["decision_reason"] = reason
    rec["decided_at"] = core.now_iso()
    rec["decided_by"] = by
    if status == "junk" and not rec.get("junk_reason"):
        rec["junk_reason"] = reason
    return rec


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append-only triage decisions for the upgrade queue.")
    parser.add_argument("decision", choices=sorted(DECISIONS.keys()))
    parser.add_argument("id_prefix", help="Record id (prefix is fine; must be unambiguous).")
    parser.add_argument("--reason", required=True, help="Why this decision was made.")
    parser.add_argument("--by", default=None, help="Decider name (defaults to OS user).")
    args = parser.parse_args(argv)

    records = core.load_records()
    matches = core.find_by_prefix(records, args.id_prefix)
    if not matches:
        print(f"[triage] no record matches id prefix '{args.id_prefix}'.", file=sys.stderr)
        return 1
    if len(matches) > 1:
        print(
            f"[triage] prefix '{args.id_prefix}' is ambiguous ({len(matches)} matches). "
            f"Use a longer prefix.",
            file=sys.stderr,
        )
        return 1

    latest = matches[0]
    status = DECISIONS[args.decision]
    by = args.by or getpass.getuser() or "unknown"
    new_rec = build_decision_record(latest, status, args.reason, by)
    core.append_records([new_rec])
    print(f"[triage] {latest.get('id')} -> {status} by {by}: {args.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
