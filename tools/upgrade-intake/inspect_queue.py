"""
Read-only inspector for the upgrade queue.

This script never writes, edits, or deletes queue records. It reads
upgrade-queue.jsonl, collapses the append-only log to the latest record per
`id` (so a triaged item shows its current status, not its original one), and
prints a human-readable summary. Use it to triage.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter

import core


def _apply_filters(records: list[dict], status, source, category, priority) -> list[dict]:
    def keep(r: dict) -> bool:
        if status is not None and r.get("status") != status:
            return False
        if source is not None and r.get("source") != source:
            return False
        if category is not None and r.get("category") != category:
            return False
        if priority is not None and r.get("priority") != priority:
            return False
        return True

    return [r for r in records if keep(r)]


def cmd_list(records: list[dict], status, source, category, priority) -> None:
    rows = _apply_filters(core.latest_records(records), status, source, category, priority)
    if not rows:
        print("(no records)")
        return
    for r in rows:
        print(
            f"[{r.get('status','?'):>12}] "
            f"{r.get('source','?'):>8} "
            f"{r.get('priority','?'):>7} "
            f"{r.get('kind','?'):>11} "
            f"{r.get('contributor','?'):>18} "
            f"id={r.get('id','?')[:8]}  {r.get('summary','')}"
        )


def cmd_show(records: list[dict], rec_id: str) -> None:
    matches = core.find_by_prefix(records, rec_id)
    if not matches:
        print(f"(no record matches id prefix '{rec_id}')")
        return
    if len(matches) > 1:
        print(f"(ambiguous prefix '{rec_id}' matches {len(matches)} records; showing all)")
    for r in matches:
        print(json.dumps(r, indent=2, ensure_ascii=False))


def cmd_stats(records: list[dict]) -> None:
    latest = core.latest_records(records)
    print(f"total: {len(latest)} (queue lines: {len(records)})")
    for label, key in (
        ("status", "status"),
        ("source", "source"),
        ("kind", "kind"),
        ("category", "category"),
        ("priority", "priority"),
    ):
        counts = Counter(r.get(key, "?") for r in latest)
        bits = ", ".join(f"{k}={v}" for k, v in counts.most_common())
        print(f"{label}: {bits or '(none)'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect the upgrade queue (read-only).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_list = sub.add_parser("list", help="List latest records.")
    p_list.add_argument("--status", default=None)
    p_list.add_argument("--source", default=None)
    p_list.add_argument("--category", default=None)
    p_list.add_argument("--priority", default=None)
    p_show = sub.add_parser("show", help="Show latest record(s) by id prefix.")
    p_show.add_argument("id")
    sub.add_parser("stats", help="Show summary counts (latest per id).")
    args = parser.parse_args(argv)

    records = core.load_records()
    if args.cmd == "list":
        cmd_list(records, args.status, args.source, args.category, args.priority)
    elif args.cmd == "show":
        cmd_show(records, args.id)
    elif args.cmd == "stats":
        cmd_stats(records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
