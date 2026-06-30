"""Demo: an agent navigates YourGov programmatically via the agent control API.

This script proves the core judge story:
"YourGov is not just a website -it exposes a safe agent control surface."

Usage:
    # 1. Start the YourGov app in another terminal:
    #    MYGOV_AGENT_API_TOKEN=dev-token-123 python app.py
    #
    # 2. Run this script:
    #    MYGOV_AGENT_API_TOKEN=dev-token-123 python agent-mcp/demo_run.py

import is done at module level so missing token gives a clear error up front.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yourgov_client import YourGovClient, YourGovClientError

_SEP = "-" * 60


def banner(title: str):
    print(f"\n{_SEP}\n  {title}\n{_SEP}")


def main():
    token = os.environ.get("MYGOV_AGENT_API_TOKEN", "")
    base_url = os.environ.get("MYGOV_APP_URL", "http://127.0.0.1:5050")

    if not token:
        print("ERROR: MYGOV_AGENT_API_TOKEN is not set.", file=sys.stderr)
        print("  export MYGOV_AGENT_API_TOKEN=dev-token-123", file=sys.stderr)
        sys.exit(1)

    client = YourGovClient(base_url=base_url, token=token)
    summary = {}

    # Step 1: Health check
    banner("Step 1 -health_check()")
    health = client.health_check()
    print(f"  status : {health.status}")
    print(f"  db     : {health.db}")
    print(f"  version: {health.version}")
    if health.status not in ("ok", "degraded"):
        print("ABORT: unhealthy app.")
        sys.exit(1)
    summary["health"] = {"status": health.status, "db": health.db}

    # Step 2: List recent divisions
    banner("Step 2 -list_divisions(limit=5)")
    divisions = client.list_divisions(limit=5)
    if not divisions:
        print("ERROR: no divisions returned.")
        sys.exit(1)
    for d in divisions:
        print(f"  [{d.division_id}] {d.date}  {d.title[:70]}")
    summary["divisions_listed"] = len(divisions)

    # Step 3: Select first division
    first = divisions[0]
    banner(f"Step 3 -select_division({first.division_id})")
    detail = client.select_division(first.division_id)
    print(f"  title     : {detail.title}")
    print(f"  date      : {detail.date}")
    print(f"  aye/no    : {detail.aye_count} / {detail.no_count}")
    print(f"  voters    : {len(detail.sample_voters)} sampled")
    print(f"  caveat    : {detail.caveat[:80]}...")
    summary["division"] = {
        "division_id": detail.division_id,
        "title": detail.title,
        "date": detail.date,
    }

    # Step 4: Pick a member from the sample voters who has a recorded vote
    member_id = None
    for voter in detail.sample_voters:
        if voter.get("vote") in ("Aye", "No"):
            member_id = voter["member_id"]
            break
    if member_id is None:
        print("  (no voted member found in sample -using David Lammy 206 as fallback)")
        member_id = 206

    # Step 5: Explain the item
    banner(f"Step 4 -explain_item(division={first.division_id}, member={member_id}, level='practical')")
    explain = client.explain_item(first.division_id, member_id, level="practical")
    print(f"  explanation : {explain.explanation}")
    print(f"  cached      : {explain.cached}")
    print(f"  fallback    : {explain.fallback}")
    print(f"  caveat      : {explain.caveat}")
    summary["explanation"] = {
        "member_id": member_id,
        "cached": explain.cached,
        "fallback": explain.fallback,
        "snippet": explain.explanation[:120],
    }

    # Final summary
    banner("Demo complete -structured summary")
    print(json.dumps(summary, indent=2))
    print(f"\n{_SEP}")
    print("  RESULT: Agent successfully navigated YourGov via API.")
    print(f"{_SEP}\n")


if __name__ == "__main__":
    main()
