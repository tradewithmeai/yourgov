"""Thin client for the public UK Parliament APIs (Members + Commons Votes).

Error contract: every call is BEST-EFFORT. Network/HTTP errors are logged and
swallowed, returning None / [] rather than raising — so an ingest run over
hundreds of members degrades gracefully (skips the failures) instead of crashing
the whole refresh.
"""
import httpx

MEMBERS_BASE = "https://members-api.parliament.uk/api"
VOTES_BASE = "https://commonsvotes-api.parliament.uk/data"

TIMEOUT = 15.0


def get_member(member_id: int) -> dict | None:
    # detailsForDate pins the member's party + seat AS AT the 2024-07-04 general
    # election, not any later mid-term change (defection, by-election), so the
    # dataset reflects how the current Parliament was elected.
    url = f"{MEMBERS_BASE}/Members/{member_id}?detailsForDate=2024-07-04T00:00:00"
    try:
        r = httpx.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json().get("value")
    except Exception as e:
        print(f"  [error] get_member({member_id}): {e}")
        return None


def get_votes(member_id: int, max_votes: int = 250) -> list[dict]:
    """Fetch an MP's division votes, paginating at 25/request (the API's page
    size) until `max_votes` is reached or a short page signals the end. The cap
    bounds work per member during a full-roster ingest."""
    page_size = 25
    all_votes: list[dict] = []
    skip = 0
    while len(all_votes) < max_votes:
        url = (
            f"{VOTES_BASE}/divisions.json/membervoting"
            f"?queryParameters.memberId={member_id}"
            f"&queryParameters.skip={skip}&queryParameters.take={page_size}"
        )
        try:
            r = httpx.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            page = r.json()
            if not isinstance(page, list) or not page:
                break
            all_votes.extend(page)
            if len(page) < page_size:
                break
            skip += page_size
        except Exception as e:
            print(f"  [error] get_votes({member_id}) skip={skip}: {e}")
            break
    return all_votes[:max_votes]


def search_members(query: str, take: int = 8) -> list[dict]:
    url = (
        f"{MEMBERS_BASE}/Members/Search"
        f"?Name={query}&House=1&IsEligible=true&skip=0&take={take}"
    )
    try:
        r = httpx.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        return [item.get("value", {}) for item in items if item.get("value")]
    except Exception as e:
        print(f"  [error] search_members({query}): {e}")
        return []


def get_questions(member_id: int, page: int = 1) -> list[dict]:
    url = f"{MEMBERS_BASE}/Members/{member_id}/WrittenQuestions?page={page}"
    try:
        r = httpx.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        return [item.get("value", {}) for item in items if item.get("value")]
    except Exception as e:
        print(f"  [error] get_questions({member_id}): {e}")
        return []
