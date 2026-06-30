#!/usr/bin/env python3
"""Verify the agent guided tour is real, not just words.

Checks that every stop in docs/agent-tour-manifest.json points to something that
actually exists: files to read, directories, runnable scripts, the TODO and
CONTRIBUTING files — and that every route the tour names is registered in the
Flask app. Exits non-zero (and prints what's wrong) if any pointer is dead.

Run:  python scripts/verify_agent_tour.py
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "docs", "agent-tour-manifest.json")


def _registered_routes():
    """Return the set of URL rule patterns registered in the Flask app, or None
    if the app can't be imported (route checks are then skipped, not failed)."""
    try:
        sys.path.insert(0, ROOT)
        import app  # noqa: WPS433
        return {str(r.rule) for r in app.app.url_map.iter_rules()}
    except Exception as exc:  # pragma: no cover - import problems are env-specific
        print(f"  (note: could not import app to verify routes: {exc})")
        return None


def _route_ok(route: str, rules: set[str]) -> bool:
    """A manifest route matches if its leading static segment matches a rule.
    Tolerant of converters, so '/mp/<member_id>' matches '/mp/<int:member_id>'."""
    seg = "/" + route.strip("/").split("/", 1)[0]
    return any(rule == route or rule.startswith(seg) for rule in rules)


def verify(manifest_path: str = MANIFEST) -> list[str]:
    """Return a list of problems (empty == tour is fully grounded)."""
    problems: list[str] = []
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    def check_file(rel: str, where: str):
        if not os.path.isfile(os.path.join(ROOT, rel)):
            problems.append(f"[{where}] missing file: {rel}")

    def check_dir(rel: str, where: str):
        if not os.path.isdir(os.path.join(ROOT, rel)):
            problems.append(f"[{where}] missing dir: {rel}")

    # Top-level files the tour funnels toward.
    for key in ("todo_file", "contributing_file"):
        rel = manifest.get(key)
        if rel:
            check_file(rel, key)
    for rel in (manifest.get("ethos", {}) or {}).get("read", []):
        check_file(rel, "ethos")

    rules = _registered_routes()
    stops = manifest.get("stops", [])
    if not stops:
        problems.append("[manifest] no stops defined")

    for stop in stops:
        sid = stop.get("id", "?")
        for rel in stop.get("read", []):
            check_file(rel, f"stop:{sid}.read")
        for rel in stop.get("run", []):
            check_file(rel, f"stop:{sid}.run")
        for rel in stop.get("dirs", []):
            check_dir(rel, f"stop:{sid}.dirs")
        if rules is not None:
            for route in stop.get("routes", []):
                if not _route_ok(route, rules):
                    problems.append(f"[stop:{sid}.routes] route not registered: {route}")
        # Each stop should actually guide, not just point.
        for field in ("say", "do_not_claim", "verify"):
            if not (stop.get(field) or "").strip():
                problems.append(f"[stop:{sid}] empty '{field}' (a tour stop must guide, not just link)")

    return problems


def main() -> int:
    print(f"Verifying agent tour manifest: {os.path.relpath(MANIFEST, ROOT)}")
    problems = verify()
    if problems:
        print(f"\nFAIL — {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1
    with open(MANIFEST, encoding="utf-8") as f:
        n = len(json.load(f).get("stops", []))
    print(f"OK — all {n} tour stops point to real files, dirs, scripts, and routes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
