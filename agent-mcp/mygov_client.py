"""HTTP client for the MyGov Agent Control API (/api/agent/*)."""
import os
import httpx
from schemas import (
    HealthResult, DivisionSummary, DivisionDetail, ExplainResult, MpSummary
)

DEFAULT_BASE_URL = os.environ.get("MYGOV_APP_URL", "http://127.0.0.1:5050")
DEFAULT_TOKEN = os.environ.get("MYGOV_AGENT_API_TOKEN", "")


class MyGovClientError(Exception):
    pass


class MyGovClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, token: str = DEFAULT_TOKEN):
        if not token:
            raise MyGovClientError("MYGOV_AGENT_API_TOKEN is not set")
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}

    def _get(self, path: str, **params) -> dict:
        url = f"{self._base}{path}"
        try:
            r = httpx.get(url, headers=self._headers, params=params, timeout=15.0)
        except httpx.ConnectError as e:
            raise MyGovClientError(f"Cannot connect to MyGov at {self._base}: {e}") from e
        if r.status_code == 401:
            raise MyGovClientError("Unauthorized — check MYGOV_AGENT_API_TOKEN")
        if r.status_code == 429:
            raise MyGovClientError("Rate limit exceeded")
        if r.status_code == 404:
            raise MyGovClientError(f"Not found: {path}")
        if r.status_code >= 500:
            raise MyGovClientError(f"Server error {r.status_code} on {path}")
        return r.json()

    def _post(self, path: str, body: dict) -> dict:
        url = f"{self._base}{path}"
        try:
            r = httpx.post(url, headers=self._headers, json=body, timeout=30.0)
        except httpx.ConnectError as e:
            raise MyGovClientError(f"Cannot connect to MyGov at {self._base}: {e}") from e
        if r.status_code == 401:
            raise MyGovClientError("Unauthorized — check MYGOV_AGENT_API_TOKEN")
        if r.status_code == 429:
            raise MyGovClientError("Rate limit exceeded")
        if r.status_code == 404:
            raise MyGovClientError(f"Not found: {path}")
        if r.status_code >= 500:
            raise MyGovClientError(f"Server error {r.status_code} on {path}")
        return r.json()

    def health_check(self) -> HealthResult:
        resp = self._get("/api/agent/health")
        d = resp.get("data", {})
        return HealthResult(
            status=d.get("status", "unknown"),
            db=bool(d.get("db")),
            version=d.get("version", "?"),
        )

    def get_routes(self) -> list[dict]:
        resp = self._get("/api/agent/routes")
        return resp.get("data", {}).get("routes", [])

    def list_divisions(self, limit: int = 10) -> list[DivisionSummary]:
        resp = self._get("/api/agent/divisions", limit=limit)
        return [
            DivisionSummary(
                division_id=d["division_id"],
                title=d["title"],
                date=d["date"],
                aye_count=d["aye_count"],
                no_count=d["no_count"],
            )
            for d in resp.get("data", {}).get("divisions", [])
        ]

    def select_division(self, division_id: int) -> DivisionDetail:
        resp = self._get(f"/api/agent/division/{division_id}")
        d = resp.get("data", {})
        return DivisionDetail(
            division_id=d["division_id"],
            title=d["title"],
            date=d["date"],
            aye_count=d["aye_count"],
            no_count=d["no_count"],
            sample_voters=d.get("sample_voters", []),
            caveat=d.get("caveat", ""),
        )

    def explain_item(
        self,
        division_id: int,
        member_id: int,
        level: int | str = 1,
        context: str = "agent",
    ) -> ExplainResult:
        resp = self._post("/api/agent/explain", {
            "division_id": division_id,
            "member_id": member_id,
            "level": level,
            "context": context,
        })
        d = resp.get("data", {})
        return ExplainResult(
            explanation=d.get("explanation", ""),
            cached=bool(d.get("cached")),
            caveat=d.get("caveat", ""),
            fallback=bool(d.get("fallback")),
        )

    def get_mp_profile_summary(self, member_id: int) -> MpSummary:
        resp = self._get(f"/api/agent/mp/{member_id}")
        d = resp.get("data", {})
        return MpSummary(
            member_id=d["member_id"],
            name=d["name"],
            party=d["party"],
            constituency=d["constituency"],
            votes_recorded=d["votes_recorded"],
            questions_recorded=d["questions_recorded"],
            recent_votes=d.get("recent_votes", []),
        )
