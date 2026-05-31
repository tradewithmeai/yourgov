"""MyGov MCP Server — exposes MyGov navigation tools via the Model Context Protocol.

Run:
    MYGOV_AGENT_API_TOKEN=<token> python server.py

Requires:
    pip install mcp httpx

If the `mcp` package is unavailable, use mygov_client.py + demo_run.py directly
as a standalone proof of the agent control API.
"""
import os
import sys
import asyncio

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print(
        "ERROR: 'mcp' package not installed.\n"
        "Install with: pip install mcp\n"
        "Alternatively, run demo_run.py to prove the agent API without the MCP wrapper.",
        file=sys.stderr,
    )
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mygov_client import MyGovClient, MyGovClientError

mcp = FastMCP("mygov")
_client = MyGovClient()


@mcp.tool()
def health_check() -> dict:
    """Check that the MyGov app is reachable and the database is accessible."""
    try:
        result = _client.health_check()
        return {"status": result.status, "db": result.db, "version": result.version}
    except MyGovClientError as e:
        return {"status": "error", "error": str(e)}


@mcp.tool()
def get_routes() -> list:
    """Return the canonical routes available in the MyGov app."""
    try:
        return _client.get_routes()
    except MyGovClientError as e:
        return [{"error": str(e)}]


@mcp.tool()
def list_divisions(limit: int = 10) -> list:
    """List recent parliamentary divisions from the MyGov database.

    Args:
        limit: Number of divisions to return (max 100, default 10).
    """
    try:
        divs = _client.list_divisions(limit=limit)
        return [
            {
                "division_id": d.division_id,
                "title": d.title,
                "date": d.date,
                "aye_count": d.aye_count,
                "no_count": d.no_count,
            }
            for d in divs
        ]
    except MyGovClientError as e:
        return [{"error": str(e)}]


@mcp.tool()
def select_division(division_id: int) -> dict:
    """Fetch full details for a specific division including sample voter data.

    Args:
        division_id: The Parliament division ID.
    """
    try:
        d = _client.select_division(division_id)
        return {
            "division_id": d.division_id,
            "title": d.title,
            "date": d.date,
            "aye_count": d.aye_count,
            "no_count": d.no_count,
            "sample_voters": d.sample_voters,
            "caveat": d.caveat,
        }
    except MyGovClientError as e:
        return {"error": str(e)}


@mcp.tool()
def explain_item(
    division_id: int,
    member_id: int,
    level: str = "practical",
    context: str = "agent",
) -> dict:
    """Get a plain-English explanation of how an MP voted in a division.

    Args:
        division_id: The Parliament division ID.
        member_id: The Parliament member ID.
        level: Explanation depth — "skim", "practical", "detailed", or "full".
        context: Caller context label (e.g. "source-lens", "agent").
    """
    try:
        r = _client.explain_item(division_id, member_id, level=level, context=context)
        return {
            "explanation": r.explanation,
            "cached": r.cached,
            "fallback": r.fallback,
            "caveat": r.caveat,
        }
    except MyGovClientError as e:
        return {"error": str(e)}


@mcp.tool()
def get_mp_profile_summary(member_id: int) -> dict:
    """Fetch a summary of an MP's recorded activity.

    Args:
        member_id: The Parliament member ID (e.g. 206 for David Lammy).
    """
    try:
        mp = _client.get_mp_profile_summary(member_id)
        return {
            "member_id": mp.member_id,
            "name": mp.name,
            "party": mp.party,
            "constituency": mp.constituency,
            "votes_recorded": mp.votes_recorded,
            "questions_recorded": mp.questions_recorded,
            "recent_votes": mp.recent_votes,
        }
    except MyGovClientError as e:
        return {"error": str(e)}


if __name__ == "__main__":
    mcp.run()
