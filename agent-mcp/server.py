"""YourGov MCP Server — exposes YourGov navigation tools via the Model Context Protocol.

Run:
    MYGOV_AGENT_API_TOKEN=<token> python server.py

Requires:
    pip install mcp httpx

If the `mcp` package is unavailable, use yourgov_client.py + demo_run.py directly
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
from yourgov_client import YourGovClient, YourGovClientError

mcp = FastMCP("yourgov")
_client = YourGovClient()


@mcp.tool()
def health_check() -> dict:
    """Check that the YourGov app is reachable and the database is accessible."""
    try:
        result = _client.health_check()
        return {"status": result.status, "db": result.db, "version": result.version}
    except YourGovClientError as e:
        return {"status": "error", "error": str(e)}


@mcp.tool()
def get_routes() -> list:
    """Return the canonical routes available in the YourGov app."""
    try:
        return _client.get_routes()
    except YourGovClientError as e:
        return [{"error": str(e)}]


@mcp.tool()
def list_divisions(limit: int = 10) -> list:
    """List recent parliamentary divisions from the YourGov database.

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
    except YourGovClientError as e:
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
    except YourGovClientError as e:
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
    except YourGovClientError as e:
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
    except YourGovClientError as e:
        return {"error": str(e)}


@mcp.tool()
def search_mps(query: str, limit: int = 10) -> list:
    """Search MPs by name, party, or constituency.

    Args:
        query: Search text (min length 2).
        limit: Max rows (default 10, max 50).
    """
    try:
        return _client.search_mps(query, limit=limit)
    except YourGovClientError as e:
        return [{"error": str(e)}]


@mcp.tool()
def get_map_payload(mode: str = "vote-split", division_id: int | None = None) -> dict:
    """Get map-ready payload for a lens mode.

    Args:
        mode: One of vote-split, party-split, gender-split, rebel-rate.
        division_id: Optional division id for vote-split mode.
    """
    try:
        return _client.get_map_payload(mode=mode, division_id=division_id)
    except YourGovClientError as e:
        return {"error": str(e)}


@mcp.tool()
def list_global_countries(status: str = "", limit: int = 25) -> list:
    """List countries from global feasibility data.

    Args:
        status: Optional filter: green/orange/red.
        limit: Max rows to return.
    """
    try:
        return _client.list_global_countries(status=status or None, limit=limit)
    except YourGovClientError as e:
        return [{"error": str(e)}]


@mcp.tool()
def get_global_country(iso2: str) -> dict:
    """Get one country record from global feasibility data by ISO2 code."""
    try:
        return _client.get_global_country(iso2)
    except YourGovClientError as e:
        return {"error": str(e)}


@mcp.tool()
def get_deeplink(
    target: str,
    member_id: int | None = None,
    division_id: int | None = None,
    cc: str | None = None,
    lang: str | None = None,
    source: str | None = None,
    variant: str | None = None,
) -> dict:
    """Build canonical YourGov deep links for agent navigation.

    target values:
      - source-lens (optional: cc, lang, source)
      - global (optional: cc, lang)
      - mp (required: member_id)
      - ab-map (optional: variant a|b)
      - publicwhip-division (required: division_id)
    """
    try:
        kwargs: dict = {}
        if member_id is not None:
            kwargs["member_id"] = member_id
        if division_id is not None:
            kwargs["division_id"] = division_id
        if cc:
            kwargs["cc"] = cc
        if lang:
            kwargs["lang"] = lang
        if source:
            kwargs["source"] = source
        if variant:
            kwargs["variant"] = variant
        return _client.get_deeplink(target=target, **kwargs)
    except YourGovClientError as e:
        return {"error": str(e)}


if __name__ == "__main__":
    mcp.run()
