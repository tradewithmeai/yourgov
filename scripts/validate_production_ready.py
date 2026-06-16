#!/usr/bin/env python
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import unicodedata
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

BRANDING_ROUTES = (
    "/home",
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
VALID_DIVISION_VOTES = {"Aye", "No", "Absent/unknown", "Vacant seat"}
REQUIRED_MAP_ROW_KEYS = (
    "vote",
    "category",
    "legend_key",
    "color",
    "label",
    "constituency",
    "member_id",
    "name",
    "party",
    "source",
)

COMMONS_VOTES_LATEST_URL = (
    "https://commonsvotes-api.parliament.uk/data/divisions.json/search"
)
PARLIAMENT_MEMBERS_SEARCH_URL = "https://members-api.parliament.uk/api/Members/Search"
PARLIAMENT_CONSTITUENCY_SEARCH_URL = (
    "https://members-api.parliament.uk/api/Location/Constituency/Search"
)
FRESHNESS_THRESHOLD_DIVISIONS = 0
# A division is complete when its stored member rows reconcile with the announced
# aye+no tally. Two allowances absorb a verified upstream quirk: Parliament's
# announced AyeCount/NoCount can exceed the published member lists by a handful of
# votes (nods/corrections counted in the headline but not listed individually) —
# observed up to ~15 on ~550-vote divisions, e.g. division 1790 stores 541 = the
# live member list while the headline says 550. So: complete if stored is within
# COMPLETENESS_TELLER_TOLERANCE rows OR within COMPLETENESS_MIN_FRACTION of the
# announced total. This still flags genuine partial fetches (the old bug stored 1
# row of 632) while not false-flagging the upstream headline discrepancy.
COMPLETENESS_TELLER_TOLERANCE = 6
COMPLETENESS_MIN_FRACTION = 0.95
RECENT_COMPLETENESS_SAMPLE = 24


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
        and "YourGov" in visible
        and "MyGov Lens POC" not in visible
        and "MyGov Lens POC" not in body,
        "YourGov route copy present and old POC title absent",
    )
    v.check(
        "source-lens search widget",
        'id="map-search"' in body and 'id="mp-search-input"' in body,
        "single centre search widget present",
    )
    v.check(
        "source-lens division summary",
        'id="division-summary"' in body and 'id="division-summary-body"' in body,
        "first-party division summary overlay present",
    )
    v.check(
        "source-lens map frame",
        'id="map-frame"' in body and 'src="/map/relay"' in body,
        "map iframe contract present",
    )
    v.check(
        "source-lens PublicWhip retired",
        'id="source-view-select"' not in body
        and 'value="publicwhip-record"' not in body
        and 'id="source-frame-panel"' not in body,
        "PublicWhip source dropdown/frame removed from the lens",
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


def _legend_contract(payload: dict) -> tuple[bool, set, dict, list[str]]:
    if "legend" not in payload or payload.get("legend") is None:
        return False, set(), {}, []

    legend = payload.get("legend")
    if not isinstance(legend, list):
        return True, set(), {}, ["legend is not a list"]

    keys = set()
    colours = {}
    errors: list[str] = []
    for index, entry in enumerate(legend):
        if not isinstance(entry, dict):
            errors.append(f"legend entry {index} is not an object")
            continue
        key = entry.get("key")
        if key in (None, ""):
            errors.append(f"legend entry {index} key missing")
            continue
        keys.add(key)
        color = entry.get("color")
        if color not in (None, ""):
            colours[key] = color
    return True, keys, colours, errors


def _map_row_errors(
    payload: dict,
    mode: str,
    division_id: int,
) -> list[str]:
    errors: list[str] = []
    map_data = payload.get("map_data")
    if not isinstance(map_data, dict) or not map_data:
        return ["map_data missing or empty"]

    legend_present, legend_keys, legend_colours, legend_errors = _legend_contract(payload)
    payload_division = payload.get("division")
    division = payload_division if isinstance(payload_division, dict) else {}
    title = str(division.get("title") or payload.get("title") or "")

    for row_key, row in map_data.items():
        row_label = str(row_key)
        if not isinstance(row, dict):
            errors.append(f"{row_label}: row is not an object")
            continue

        row_errors: list[str] = []
        is_vacant = row.get("is_vacant") is True
        if row.get("mode") != mode:
            row_errors.append(f"mode {row.get('mode')!r} expected {mode!r}")

        division_vote = row.get("division_vote")
        if division_vote not in VALID_DIVISION_VOTES:
            row_errors.append(
                f"division_vote {division_vote!r} expected one of "
                f"{sorted(VALID_DIVISION_VOTES)}"
            )

        for required_key in REQUIRED_MAP_ROW_KEYS:
            if required_key == "member_id" and is_vacant:
                if row.get("member_id") is not None:
                    row_errors.append("vacant row member_id must be null")
                continue
            if row.get(required_key) in (None, ""):
                row_errors.append(f"{required_key} missing")

        if is_vacant:
            if row.get("name") != "Vacant seat":
                row_errors.append("vacant row name must be 'Vacant seat'")
            if row.get("party") != "Vacant":
                row_errors.append("vacant row party must be 'Vacant'")
            if row.get("vote") != "Vacant seat":
                row_errors.append("vacant row vote must be 'Vacant seat'")
            if division_vote != "Vacant seat":
                row_errors.append("vacant row division_vote must be 'Vacant seat'")

        legend_key = row.get("legend_key")
        if legend_present:
            row_errors.extend(legend_errors)
            if legend_key not in legend_keys:
                row_errors.append(f"legend_key {legend_key!r} missing from payload legend")
            expected_color = legend_colours.get(legend_key)
            if expected_color is not None and row.get("color") != expected_color:
                row_errors.append(
                    f"color {row.get('color')!r} expected {expected_color!r} "
                    f"for legend_key {legend_key!r}"
                )

        constituency = row.get("constituency")
        if isinstance(row_key, str) and row_key.strip():
            if constituency != row_key:
                row_errors.append(
                    f"constituency {constituency!r} expected map key {row_key!r}"
                )
        elif constituency in (None, ""):
            row_errors.append("constituency missing")

        label = str(row.get("label") or "")
        if mode != "vote-split":
            if not title:
                row_errors.append(f"selected division title missing for {division_id}")
            elif title not in label:
                row_errors.append(f"label missing selected division title {title!r}")
            if division_vote and str(division_vote) not in label:
                row_errors.append(f"label missing division_vote {division_vote!r}")

        if row_errors:
            errors.append(f"{row_label}: {', '.join(row_errors)}")

    return errors


def _validate_map_rows(
    v: Validation,
    payload: dict,
    mode: str,
    division_id: int,
) -> bool:
    errors = _map_row_errors(payload, mode, division_id)
    if errors:
        v.fail(f"division map rows {mode}", _format_errors(errors))
        return False
    v.pass_(f"division map rows {mode}", "ok")
    return True


def check_payloads(v: Validation, client, division_id: int) -> None:
    selected_ids: set[int] = set()
    payloads: dict[str, dict] = {}
    constituency_sets: dict[str, set[str]] = {}

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
        if isinstance(map_data, dict):
            constituency_sets[mode] = set(str(key) for key in map_data.keys())

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

        data_quality = payload.get("data_quality")
        map_constituency_rows = (
            _safe_int(data_quality.get("map_constituency_rows"))
            if isinstance(data_quality, dict)
            else None
        )
        current_member_rows = (
            _safe_int(data_quality.get("current_member_rows"))
            if isinstance(data_quality, dict)
            else None
        )
        vacant_constituency_rows = (
            _safe_int(data_quality.get("vacant_constituency_rows"))
            if isinstance(data_quality, dict)
            else None
        )
        actual_map_rows = len(map_data) if isinstance(map_data, dict) else None
        v.check(
            f"division map row count {mode}",
            map_constituency_rows == actual_map_rows and actual_map_rows is not None,
            f"map_constituency_rows {map_constituency_rows}, map rows {actual_map_rows}",
        )
        v.check(
            f"division constituency/member count {mode}",
            (
                current_member_rows is not None
                and vacant_constituency_rows is not None
                and map_constituency_rows is not None
                and current_member_rows + vacant_constituency_rows
                == map_constituency_rows
            ),
            (
                f"current {current_member_rows}, vacant {vacant_constituency_rows}, "
                f"map rows {map_constituency_rows}"
            ),
        )

        source_link_errors = _source_link_errors(payload, division_id)
        v.check(
            f"division source links {mode}",
            not source_link_errors,
            _format_errors(source_link_errors),
        )

        _validate_map_rows(v, payload, mode, division_id)

    v.check(
        "division map selected division consistency",
        selected_ids == {division_id},
        f"selected ids {sorted(selected_ids)}",
    )

    if constituency_sets:
        reference_mode = MAP_MODES[0]
        reference = constituency_sets.get(reference_mode, set())
        mismatched_modes = [
            mode
            for mode in MAP_MODES
            if constituency_sets.get(mode, set()) != reference
        ]
        v.check(
            "division map constituency consistency",
            not mismatched_modes,
            f"mismatched modes {mismatched_modes or 'none'}",
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


def _second_division_id(client, primary_id: int) -> int | None:
    response, payload = _json_response(client, "/api/lens/source-divisions?limit=12")
    divisions = payload.get("divisions") if isinstance(payload, dict) else None
    if not isinstance(divisions, list):
        return None
    for division in divisions:
        candidate = _safe_int(division.get("division_id")) if isinstance(division, dict) else None
        if candidate is not None and candidate != primary_id:
            return candidate
    return None


def _mode_category_map(client, division_id: int, mode: str) -> dict[str, str]:
    _response, payload = _json_response(
        client, f"/api/lens/division/{division_id}/map?mode={mode}"
    )
    map_data = payload.get("map_data") if isinstance(payload, dict) else None
    if not isinstance(map_data, dict):
        return {}
    return {
        str(key): str(row.get("category"))
        for key, row in map_data.items()
        if isinstance(row, dict)
    }


def check_division_derivation(v: Validation, client, division_id: int) -> None:
    """Prove the per-division map modes actually change with the selected division —
    not just that a label mentions the title. party-split and gender-split must differ
    across two distinct divisions (driven by who voted), or they are a constant
    national map masquerading as division-scoped."""
    other_id = _second_division_id(client, division_id)
    if other_id is None:
        v.pass_("division derivation", "only one division available to compare")
        return

    for mode in ("vote-split", "party-split", "gender-split", "rebel-split"):
        primary = _mode_category_map(client, division_id, mode)
        other = _mode_category_map(client, other_id, mode)
        shared = set(primary) & set(other)
        differing = sum(1 for key in shared if primary[key] != other[key])
        v.check(
            f"division derivation {mode}",
            bool(shared) and differing > 0,
            f"{differing} of {len(shared)} constituencies differ between "
            f"divisions {division_id} and {other_id}",
        )


def _map_constituency_names() -> set[str]:
    data_path = ROOT / "static" / "promap" / "data" / "constituencies-uk-2024-bgc.geojson"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    features = data.get("features") if isinstance(data, dict) else []
    names: set[str] = set()
    for feature in features if isinstance(features, list) else []:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties") or {}
        if not isinstance(properties, dict):
            continue
        name = properties.get("PCON24NM") or properties.get("name")
        if name:
            names.add(str(name))
    return names


def _normalise_constituency_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    ascii_text = text.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.replace("&", "and")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", ascii_text.lower())).strip()


def _normalised_constituency_names(values: set[str]) -> set[str]:
    return {_normalise_constituency_name(value) for value in values}


def check_local_data_coverage(v: Validation, division_id: int) -> None:
    conn = get_publicwhip_conn()
    try:
        member_row = conn.execute(
            """
            SELECT
                COUNT(*) AS current_members,
                COUNT(DISTINCT constituency) AS constituencies
            FROM members
            WHERE constituency IS NOT NULL
            """
        ).fetchone()
        constituency_row = conn.execute(
            """
            SELECT
                COUNT(*) AS constituencies,
                SUM(CASE WHEN current_member_id IS NOT NULL THEN 1 ELSE 0 END)
                    AS represented_constituencies,
                SUM(CASE WHEN current_member_id IS NULL THEN 1 ELSE 0 END)
                    AS vacant_constituencies
            FROM constituencies
            """
        ).fetchone()
        vote_row = conn.execute(
            """
            SELECT
                COUNT(*) AS vote_rows,
                SUM(CASE WHEN voted_aye = 1 THEN 1 ELSE 0 END) AS ayes,
                SUM(CASE WHEN voted_aye = 0 THEN 1 ELSE 0 END) AS noes
            FROM votes
            WHERE division_id = ?
            """,
            (division_id,),
        ).fetchone()
    finally:
        conn.close()

    current_members = int(member_row["current_members"] or 0)
    member_constituencies = int(member_row["constituencies"] or 0)
    constituencies = int(constituency_row["constituencies"] or 0)
    represented_constituencies = int(constituency_row["represented_constituencies"] or 0)
    vacant_constituencies = int(constituency_row["vacant_constituencies"] or 0)
    map_constituencies = len(_map_constituency_names())
    v.check(
        "local Commons constituency coverage",
        (
            constituencies == map_constituencies
            and represented_constituencies == current_members == member_constituencies
            and current_members + vacant_constituencies == constituencies
        ),
        (
            f"{constituencies} constituencies, {current_members} current MPs, "
            f"{vacant_constituencies} vacancies, {map_constituencies} map seats"
        ),
    )

    vote_rows = int(vote_row["vote_rows"] or 0)
    ayes = int(vote_row["ayes"] or 0)
    noes = int(vote_row["noes"] or 0)
    v.check(
        "selected division local vote coverage",
        vote_rows > 0 and ayes > 0 and noes > 0,
        f"{vote_rows} vote rows, {ayes} ayes, {noes} noes",
    )


def _division_completeness_rows() -> list[dict]:
    """Per-division stored member rows vs the announced aye+no tally."""
    conn = get_publicwhip_conn()
    try:
        rows = conn.execute(
            """
            SELECT
                division_id,
                COUNT(*) AS stored,
                MAX(aye_count) AS aye_count,
                MAX(no_count) AS no_count,
                MAX(division_date) AS division_date
            FROM votes
            WHERE aye_count > 0
            GROUP BY division_id
            """
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "division_id": row["division_id"],
            "stored": int(row["stored"] or 0),
            "reported": int(row["aye_count"] or 0) + int(row["no_count"] or 0),
            "division_date": row["division_date"] or "",
        }
        for row in rows
    ]


def _is_complete(row: dict, tolerance: int = COMPLETENESS_TELLER_TOLERANCE) -> bool:
    reported = row["reported"]
    if row["stored"] >= reported - tolerance:
        return True
    return reported > 0 and row["stored"] >= reported * COMPLETENESS_MIN_FRACTION


def check_recent_division_completeness(v: Validation) -> None:
    """The daily refresh pulls full member detail for recent divisions, so the most
    recent divisions must each store a complete member set. Guards the live refresh
    path without requiring the full historical backfill to have run."""
    rows = sorted(
        _division_completeness_rows(),
        key=lambda row: row["division_id"],
        reverse=True,
    )[:RECENT_COMPLETENESS_SAMPLE]
    if not rows:
        v.fail("recent division completeness", "no divisions with a recorded tally found")
        return

    incomplete = [row for row in rows if not _is_complete(row)]
    v.check(
        "recent division completeness",
        not incomplete,
        (
            f"{len(rows) - len(incomplete)}/{len(rows)} recent divisions complete"
            if not incomplete
            else "; ".join(
                f"division {row['division_id']} stored {row['stored']} of {row['reported']}"
                for row in incomplete[:5]
            )
        ),
    )


def check_full_history_completeness(v: Validation, require: bool) -> None:
    """Opt-in (--require-full-history) assertion that EVERY recorded division stores a
    complete member set. Fails until the historical backfill has run, so it is off by
    default and does not block the daily recent-division refresh."""
    rows = _division_completeness_rows()
    incomplete = [row for row in rows if not _is_complete(row)]
    missing_rows = sum(row["reported"] - row["stored"] for row in incomplete)
    detail = (
        f"{len(rows) - len(incomplete)}/{len(rows)} divisions complete; "
        f"{len(incomplete)} incomplete, ~{missing_rows} member rows missing"
    )
    if not require:
        if incomplete:
            v.pass_(
                "full history completeness not enforced",
                detail + " (run scripts/update_publicwhip_data.py --backfill)",
            )
        else:
            v.pass_("full history completeness", detail)
        return
    v.check("full history completeness", not incomplete, detail)


def _fetch_api_values(
    url: str,
    params: dict,
    *,
    page_size: int = 100,
) -> list[dict]:
    values: list[dict] = []
    skip = 0
    while True:
        page_params = dict(params)
        page_params.update({"skip": skip, "take": page_size})
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                response = httpx.get(
                    url,
                    params=page_params,
                    headers={"User-Agent": "YourGov production validation"},
                    timeout=20.0,
                )
                break
            except Exception as exc:
                last_exc = exc
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
        else:
            raise RuntimeError(f"{url} failed after 3 attempts: {last_exc}")
        response.raise_for_status()
        payload = response.json()
        items = payload.get("items", []) if isinstance(payload, dict) else []
        page_values = [
            item.get("value")
            for item in items
            if isinstance(item, dict) and isinstance(item.get("value"), dict)
        ]
        values.extend(page_values)
        received = len(items)
        if received == 0:
            break
        skip += received
        total_results = _safe_int(payload.get("totalResults")) if isinstance(payload, dict) else None
        if total_results is not None and skip >= total_results:
            break
        if total_results is None and received < page_size:
            break
    return values


def _constituency_current_member_id(constituency: dict) -> int | None:
    representation = constituency.get("currentRepresentation") or {}
    if not isinstance(representation, dict):
        return None
    member = representation.get("member") or {}
    if not isinstance(member, dict):
        return None
    value = member.get("value") or {}
    if not isinstance(value, dict):
        return None
    return _safe_int(value.get("id"))


def _local_commons_coverage() -> dict:
    conn = get_publicwhip_conn()
    try:
        constituency_rows = conn.execute(
            """
            SELECT name, current_member_id
            FROM constituencies
            """
        ).fetchall()
        member_row = conn.execute(
            """
            SELECT COUNT(*) AS current_members
            FROM members
            WHERE constituency IS NOT NULL
            """
        ).fetchone()
    finally:
        conn.close()

    local_vacancy_names = {
        row["name"]
        for row in constituency_rows
        if row["current_member_id"] is None
    }
    return {
        "constituency_names": {row["name"] for row in constituency_rows},
        "constituencies": len(constituency_rows),
        "current_members": int(member_row["current_members"] or 0),
        "vacancies": len(local_vacancy_names),
        "vacancy_names": local_vacancy_names,
    }


def _commons_coverage_result(
    *,
    official_constituencies: int,
    official_current_members: int,
    official_vacancies: int,
    local_constituencies: int,
    local_current_members: int,
    local_vacancies: int,
    map_constituencies: int,
    official_vacancy_names: set[str],
    local_vacancy_names: set[str],
) -> tuple[bool, str]:
    detail = (
        f"{official_constituencies} constituencies, "
        f"{official_current_members} current MPs, {official_vacancies} vacancies"
    )
    if official_current_members + official_vacancies != official_constituencies:
        return False, f"{detail}; official current MPs + vacancies do not reconcile"
    if local_current_members + local_vacancies != local_constituencies:
        return False, f"{detail}; local current MPs + vacancies do not reconcile"
    if local_constituencies != official_constituencies:
        return False, f"{detail}; local constituencies {local_constituencies}"
    if map_constituencies != official_constituencies:
        return False, f"{detail}; map constituencies {map_constituencies}"
    if local_current_members != official_current_members:
        return False, f"{detail}; local current MPs {local_current_members}"
    if local_vacancies != official_vacancies:
        return False, f"{detail}; local vacancies {local_vacancies}"
    if local_vacancy_names != official_vacancy_names:
        return False, (
            f"{detail}; local vacancy names {sorted(local_vacancy_names)} "
            f"expected {sorted(official_vacancy_names)}"
        )
    return True, detail


def check_official_commons_coverage(v: Validation, skip: bool) -> None:
    if skip:
        v.pass_("official Commons coverage skipped", "skip flag supplied")
        return

    try:
        official_members = _fetch_api_values(
            PARLIAMENT_MEMBERS_SEARCH_URL,
            {"House": 1, "IsCurrentMember": "true"},
        )
        official_constituencies = _fetch_api_values(
            PARLIAMENT_CONSTITUENCY_SEARCH_URL,
            {},
        )
    except Exception as exc:
        v.fail("official Commons coverage", f"Parliament API request failed: {exc}")
        return

    official_vacancy_names = {
        str(seat.get("name"))
        for seat in official_constituencies
        if seat.get("name") and _constituency_current_member_id(seat) is None
    }
    local = _local_commons_coverage()
    map_names = _map_constituency_names()

    coverage_ok, coverage_detail = _commons_coverage_result(
        official_constituencies=len(official_constituencies),
        official_current_members=len(official_members),
        official_vacancies=len(official_vacancy_names),
        local_constituencies=local["constituencies"],
        local_current_members=local["current_members"],
        local_vacancies=local["vacancies"],
        map_constituencies=len(map_names),
        official_vacancy_names=official_vacancy_names,
        local_vacancy_names=local["vacancy_names"],
    )
    v.check("official Commons coverage", coverage_ok, coverage_detail)

    official_names = {
        str(seat.get("name"))
        for seat in official_constituencies
        if seat.get("name")
    }
    normalised_official_names = _normalised_constituency_names(official_names)
    normalised_local_names = _normalised_constituency_names(local["constituency_names"])
    normalised_map_names = _normalised_constituency_names(map_names)
    v.check(
        "official constituency names",
        normalised_official_names == normalised_local_names == normalised_map_names,
        (
            f"official {len(official_names)}, local {len(local['constituency_names'])}, "
            f"map {len(map_names)}"
        ),
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
    for route in BRANDING_ROUTES:
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
        help=(
            "Skip the optional Commons Votes API division-freshness check only. The "
            "live count/coverage check still runs unless --skip-commons-coverage is set."
        ),
    )
    parser.add_argument(
        "--skip-commons-coverage",
        action="store_true",
        help=(
            "Skip the live Parliament Members/Constituency count + coverage check "
            "(the 650/647/vacancy reconciliation). Off by default."
        ),
    )
    parser.add_argument(
        "--require-full-history",
        action="store_true",
        help=(
            "Fail unless EVERY recorded division stores a complete member set. Off by "
            "default; enable after running --backfill so the daily refresh is not blocked."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
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
        check_local_data_coverage(v, int(division_id))
        check_payloads(v, client, int(division_id))
        check_division_derivation(v, client, int(division_id))
        check_recent_division_completeness(v)
        check_full_history_completeness(v, args.require_full_history)
        check_global_feasibility(v)
        check_branding(v, client)
        check_official_commons_coverage(v, args.skip_commons_coverage)
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
