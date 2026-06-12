#!/usr/bin/env python
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import app, get_publicwhip_conn  # noqa: E402


CORE_ROUTES = (
    "/",
    "/source-lens",
    "/global",
    "/publicwhip",
    "/publicwhip/divisions",
    "/publicwhip/mps",
)

MAP_MODES = (
    "vote-split",
    "party-split",
    "gender-split",
    "rebel-split",
)
VALID_DIVISION_VOTES = {"Aye", "No", "Absent/unknown"}

COMMONS_VOTES_LATEST_URL = (
    "https://commonsvotes-api.parliament.uk/data/divisions.json/search"
)
FRESHNESS_THRESHOLD_DIVISIONS = 5


class Validation:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def pass_(self, label: str, detail: str = "") -> None:
        suffix = f" - {detail}" if detail else ""
        print(f"PASS {label}{suffix}")

    def fail(self, label: str, detail: str) -> None:
        message = f"{label}: {detail}"
        self.failures.append(message)
        print(f"FAIL {message}")

    def check(self, label: str, condition: bool, detail: str) -> bool:
        if condition:
            self.pass_(label, detail)
            return True
        self.fail(label, detail)
        return False

    def finish(self) -> int:
        if self.failures:
            print(f"VALIDATION FAIL - {len(self.failures)} failure(s)")
            for failure in self.failures:
                print(f" - {failure}")
            return 1
        print("VALIDATION PASS")
        return 0


def _client():
    app.config["TESTING"] = True
    return app.test_client()


def _visible_text(markup: str) -> str:
    without_invisible = re.sub(
        r"(?is)<(script|style|noscript)\b.*?</\1>",
        " ",
        markup,
    )
    without_tags = re.sub(r"(?s)<[^>]+>", " ", without_invisible)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def _json_response(client, path: str):
    response = client.get(path)
    try:
        payload = response.get_json()
    except Exception:
        payload = None
    return response, payload


def latest_local_division_id() -> int:
    conn = get_publicwhip_conn()
    try:
        row = conn.execute(
            """
            SELECT MAX(division_id) AS latest_id
            FROM votes
            WHERE title IS NOT NULL
              AND aye_count > 0
            """
        ).fetchone()
    finally:
        conn.close()

    latest_id = row["latest_id"] if row else None
    if not latest_id:
        raise RuntimeError("No local PublicWhip divisions were found.")
    return int(latest_id)


def check_routes(v: Validation, client) -> None:
    for route in CORE_ROUTES:
        response = client.get(route)
        v.check(
            f"route {route}",
            response.status_code in {200, 301, 302, 303, 307, 308},
            f"status {response.status_code}",
        )


def check_source_lens(v: Validation, client) -> None:
    response = client.get("/source-lens")
    body = response.get_data(as_text=True)
    visible = _visible_text(body)

    v.check(
        "source-lens brand",
        response.status_code == 200
        and "YourGov Source Lens" in visible
        and "MyGov Lens POC" not in visible
        and "MyGov Lens POC" not in body,
        "YourGov primary product present and old POC title absent",
    )
    v.check(
        "source dropdown",
        'id="source-view-select"' in body
        and 'value="yourgov-summary"' in body
        and 'value="publicwhip-record"' in body
        and "PublicWhip" in visible,
        "YourGov Summary and PublicWhip Record options available",
    )
    v.check(
        "source-lens map frame",
        'id="map-frame"' in body and 'src="/map/relay"' in body,
        "map iframe contract present",
    )
    v.check(
        "source dropdown PublicWhip contract",
        re.search(
            r"<option[^>]+value=[\"']publicwhip-record[\"'][^>]*>\s*PublicWhip Record\s*</option>",
            body,
            re.IGNORECASE,
        )
        is not None,
        "PublicWhip Record is selectable through source dropdown",
    )


def check_source_divisions(v: Validation, client) -> None:
    response, payload = _json_response(client, "/api/lens/source-divisions")
    divisions = payload.get("divisions") if isinstance(payload, dict) else None
    v.check(
        "source divisions",
        response.status_code == 200 and isinstance(divisions, list) and len(divisions) > 0,
        f"status {response.status_code}, count {len(divisions or [])}",
    )


def _safe_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _payload_division_id(payload: dict) -> int | None:
    division = payload.get("division")
    if isinstance(division, dict) and division.get("division_id") is not None:
        return _safe_int(division["division_id"])
    if payload.get("division_id") is not None:
        return _safe_int(payload["division_id"])
    return None


def _items_have_selected_context(payload: dict) -> bool:
    division = payload.get("division") or {}
    title = str(division.get("title") or payload.get("title") or "")
    map_data = payload.get("map_data") or {}
    if not title or not map_data:
        return False
    for item in map_data.values():
        if not isinstance(item, dict):
            return False
        label = str(item.get("label") or "")
        vote_context = str(item.get("division_vote") or item.get("vote") or "")
        if title not in label:
            return False
        if vote_context and vote_context not in label:
            return False
    return True


def _format_errors(errors: list[str]) -> str:
    return "; ".join(errors) if errors else "ok"


def _map_payload_metadata_errors(payload: dict, mode: str, division_id: int) -> list[str]:
    errors: list[str] = []

    if payload.get("mode") != mode:
        errors.append(f"mode {payload.get('mode')!r} expected {mode!r}")
    if payload.get("map_mode") != mode:
        errors.append(f"map_mode {payload.get('map_mode')!r} expected {mode!r}")

    data_quality = payload.get("data_quality")
    if not isinstance(data_quality, dict):
        errors.append("data_quality missing or not an object")
    else:
        if data_quality.get("division_scoped") is not True:
            errors.append(
                f"data_quality.division_scoped {data_quality.get('division_scoped')!r} "
                "expected True"
            )
        selected_division_id = _safe_int(data_quality.get("selected_division_id"))
        if selected_division_id != division_id:
            errors.append(
                "data_quality.selected_division_id "
                f"{data_quality.get('selected_division_id')!r} expected {division_id}"
            )

    division = payload.get("division")
    division_payload_id = (
        _safe_int(division.get("division_id")) if isinstance(division, dict) else None
    )
    if division_payload_id != division_id:
        errors.append(
            "division.division_id "
            f"{division.get('division_id') if isinstance(division, dict) else None!r} "
            f"expected {division_id}"
        )

    return errors


def _source_link_errors(payload: dict, division_id: int) -> list[str]:
    expected_url_fragment = f"/publicwhip/division/{division_id}"
    source_links = payload.get("source_links")
    if not isinstance(source_links, list) or not source_links:
        return [f"source_links missing expected URL containing {expected_url_fragment}"]

    urls = [
        str(link.get("url") or "")
        for link in source_links
        if isinstance(link, dict)
    ]
    if not any(expected_url_fragment in url for url in urls):
        return [
            f"source_links missing expected URL containing {expected_url_fragment}; "
            f"urls {urls or 'none'}"
        ]
    return []


def _representative_row_errors(
    payload: dict,
    mode: str,
    division_id: int,
) -> list[str]:
    errors: list[str] = []
    map_data = payload.get("map_data")
    if not isinstance(map_data, dict) or not map_data:
        return ["map_data missing or empty"]

    row_key, row = next(iter(map_data.items()))
    if not isinstance(row, dict):
        return [f"representative row {row_key!r} is not an object"]

    if row.get("mode") != mode:
        errors.append(f"mode {row.get('mode')!r} expected {mode!r}")

    division_vote = row.get("division_vote")
    if division_vote not in VALID_DIVISION_VOTES:
        errors.append(
            f"division_vote {division_vote!r} expected one of "
            f"{sorted(VALID_DIVISION_VOTES)}"
        )

    for required_key in ("vote", "category", "legend_key"):
        if row.get(required_key) in (None, ""):
            errors.append(f"{required_key} missing")

    if mode != "vote-split":
        payload_division = payload.get("division")
        division = payload_division if isinstance(payload_division, dict) else {}
        title = str(division.get("title") or payload.get("title") or "")
        label = str(row.get("label") or "")
        if not title:
            errors.append(f"selected division title missing for {division_id}")
        elif title not in label:
            errors.append(f"label missing selected division title {title!r}")

    return errors


def check_payloads(v: Validation, client, division_id: int) -> None:
    selected_ids: set[int] = set()
    payloads: dict[str, dict] = {}

    for mode in MAP_MODES:
        response, payload = _json_response(
            client,
            f"/api/lens/division/{division_id}/map?mode={mode}",
        )
        payload = payload if isinstance(payload, dict) else {}
        map_data = payload.get("map_data")
        selected_id = _payload_division_id(payload)
        if selected_id is not None:
            selected_ids.add(selected_id)
        payloads[mode] = payload

        v.check(
            f"division map payload {mode}",
            response.status_code == 200
            and payload.get("ok") is True
            and selected_id == division_id
            and isinstance(map_data, dict)
            and len(map_data) > 0,
            (
                f"status {response.status_code}, selected division {selected_id}, "
                f"map rows {len(map_data or {})}"
            ),
        )
        metadata_errors = _map_payload_metadata_errors(payload, mode, division_id)
        v.check(
            f"division map metadata {mode}",
            not metadata_errors,
            _format_errors(metadata_errors),
        )

        source_link_errors = _source_link_errors(payload, division_id)
        v.check(
            f"division source links {mode}",
            not source_link_errors,
            _format_errors(source_link_errors),
        )

        representative_row_errors = _representative_row_errors(
            payload,
            mode,
            division_id,
        )
        v.check(
            f"division map representative row {mode}",
            not representative_row_errors,
            _format_errors(representative_row_errors),
        )

    v.check(
        "division map selected division consistency",
        selected_ids == {division_id},
        f"selected ids {sorted(selected_ids)}",
    )

    for mode in ("party-split", "gender-split", "rebel-split"):
        v.check(
            f"division label context {mode}",
            _items_have_selected_context(payloads.get(mode, {})),
            "labels include selected division title and vote context",
        )

    source_links_ok = all(
        not _source_link_errors(payload, division_id)
        for payload in payloads.values()
    )
    v.check(
        "division source links",
        source_links_ok,
        f"source_links include /publicwhip/division/{division_id}",
    )


def check_global_feasibility(v: Validation) -> None:
    data_path = ROOT / "static" / "data" / "global_feasibility.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    countries = data.get("countries") if isinstance(data, dict) else None
    countries = countries if isinstance(countries, list) else []

    v.check(
        "global feasibility country count",
        len(countries) >= 190,
        f"{len(countries)} countries",
    )

    iso2_values = [
        str(country.get("iso2") or "").upper()
        for country in countries
        if isinstance(country, dict) and country.get("iso2")
    ]
    duplicates = sorted(
        iso2 for iso2 in set(iso2_values) if iso2_values.count(iso2) > 1
    )
    v.check(
        "global feasibility ISO2 uniqueness",
        len(duplicates) == 0 and len(iso2_values) == len(countries),
        f"duplicates {duplicates or 'none'}",
    )

    gb = next(
        (
            country
            for country in countries
            if isinstance(country, dict) and str(country.get("iso2", "")).upper() == "GB"
        ),
        None,
    )
    v.check(
        "global feasibility UK adapter",
        isinstance(gb, dict) and gb.get("working_adapter") is True,
        "GB working_adapter true",
    )


def check_branding(v: Validation, client) -> None:
    for route in CORE_ROUTES:
        response = client.get(route)
        visible = _visible_text(response.get_data(as_text=True))
        v.check(
            f"public branding {route}",
            response.status_code in {200, 301, 302}
            and "MyGov" not in visible
            and "YourGov" in visible,
            "visible copy uses YourGov and avoids old MyGov public copy",
        )


def _extract_remote_division_id(row: dict) -> int | None:
    for key in ("DivisionId", "divisionId", "division_id"):
        value = row.get(key)
        if value is not None:
            return _safe_int(value)
    return None


def _freshness_result(
    local_latest_id: int,
    remote_latest_id: int,
    threshold: int,
) -> tuple[bool, int, str]:
    trail = remote_latest_id - local_latest_id
    if trail < 0:
        return False, trail, "local ahead of upstream"
    if trail > threshold:
        return False, trail, "local trails upstream"
    return True, trail, "fresh enough"


def check_network_freshness(v: Validation, local_latest_id: int, skip: bool) -> None:
    if skip:
        v.pass_("network freshness skipped", "skip flag supplied")
        return

    try:
        response = httpx.get(
            COMMONS_VOTES_LATEST_URL,
            params={"take": 1},
            headers={"User-Agent": "YourGov production validation"},
            timeout=20.0,
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload if isinstance(payload, list) else payload.get("items", [])
        if not rows:
            v.fail("network freshness", "Commons Votes API returned no divisions")
            return
        remote_latest_id = _extract_remote_division_id(rows[0])
        if remote_latest_id is None:
            v.fail(
                "network freshness",
                f"Commons Votes API payload missing DivisionId: {rows[0]}",
            )
            return
    except Exception as exc:
        v.fail("network freshness", f"Commons Votes API request failed: {exc}")
        return

    passes, trail, reason = _freshness_result(
        local_latest_id,
        remote_latest_id,
        FRESHNESS_THRESHOLD_DIVISIONS,
    )
    v.check(
        "network freshness",
        passes,
        (
            f"local latest {local_latest_id}, upstream latest {remote_latest_id}, "
            f"trail {trail}, threshold {FRESHNESS_THRESHOLD_DIVISIONS}, {reason}"
        ),
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate local YourGov production readiness contracts.",
    )
    parser.add_argument(
        "--division-id",
        type=int,
        default=None,
        help="Division id to validate. Defaults to the latest local division.",
    )
    parser.add_argument(
        "--skip-network-freshness",
        action="store_true",
        help="Skip the optional Commons Votes API freshness check.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    v = Validation()
    client = _client()

    try:
        local_latest_id = latest_local_division_id()
        v.pass_("latest local division", str(local_latest_id))
    except Exception as exc:
        v.fail("latest local division", str(exc))
        local_latest_id = args.division_id

    division_id = args.division_id or local_latest_id
    if division_id is None:
        v.fail("division id", "No --division-id supplied and local latest lookup failed.")
        return v.finish()

    try:
        check_routes(v, client)
        check_source_lens(v, client)
        check_source_divisions(v, client)
        check_payloads(v, client, int(division_id))
        check_global_feasibility(v)
        check_branding(v, client)
        check_network_freshness(
            v,
            int(local_latest_id or division_id),
            args.skip_network_freshness,
        )
    except Exception as exc:
        v.fail("validation error", str(exc))

    return v.finish()


if __name__ == "__main__":
    raise SystemExit(main())
