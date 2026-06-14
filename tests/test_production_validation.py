import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_production_ready.py"


def _load_validation_script():
    spec = importlib.util.spec_from_file_location("validate_production_ready", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


validation_script = _load_validation_script()


class _FakeJsonResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def get_json(self):
        return self._payload


class _FakeMapClient:
    def __init__(self, payloads):
        self.payloads = payloads

    def get(self, path):
        mode = path.rsplit("mode=", 1)[1]
        return _FakeJsonResponse(self.payloads[mode])


def _valid_map_payload(mode, division_id=2355):
    title = "Selected Division Title"
    division_vote = "Aye"
    constituency = "Example Constituency"
    color = "#0087dc"
    return {
        "ok": True,
        "mode": mode,
        "map_mode": mode,
        "data_quality": {
            "division_scoped": True,
            "selected_division_id": division_id,
            "mapped_member_rows": 1,
            "current_member_rows": 1,
            "map_constituency_rows": 1,
            "vacant_constituency_rows": 0,
        },
        "division": {
            "division_id": division_id,
            "title": title,
        },
        "source_links": [
            {
                "label": "PublicWhip division",
                "url": f"/publicwhip/division/{division_id}",
            },
        ],
        "legend": [
            {
                "key": division_vote,
                "label": division_vote,
                "color": color,
            },
        ],
        "map_data": {
            constituency: {
                "mode": mode,
                "division_vote": division_vote,
                "vote": division_vote,
                "category": "Labour",
                "legend_key": division_vote,
                "color": color,
                "label": f"{title} - {division_vote} - example member",
                "constituency": constituency,
                "member_id": 123,
                "name": "Example Member",
                "party": "Labour",
                "source": "PublicWhip",
            },
        },
    }


def _valid_payloads(division_id=2355):
    return {
        mode: _valid_map_payload(mode, division_id)
        for mode in validation_script.MAP_MODES
    }


def test_production_validation_script_passes_local_contracts():
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--skip-network-freshness",
            "--skip-commons-coverage",
            "--division-id",
            "2355",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS source-lens brand" in result.stdout
    assert "PASS source dropdown" in result.stdout
    assert "PASS division map payload vote-split" in result.stdout
    assert "PASS division map payload party-split" in result.stdout
    assert "PASS division map payload gender-split" in result.stdout
    assert "PASS division map payload rebel-split" in result.stdout
    assert "PASS division derivation party-split" in result.stdout
    assert "PASS recent division completeness" in result.stdout
    assert "PASS global feasibility UK adapter" in result.stdout
    assert "PASS network freshness skipped" in result.stdout
    assert "VALIDATION PASS" in result.stdout


def test_freshness_result_requires_local_not_ahead_and_within_threshold():
    freshness_result = getattr(validation_script, "_freshness_result", None)

    assert callable(freshness_result)
    assert freshness_result(100, 102, 5) == (True, 2, "fresh enough")
    assert freshness_result(100, 106, 5) == (False, 6, "local trails upstream")
    assert freshness_result(105, 100, 5) == (False, -5, "local ahead of upstream")


def test_main_records_unexpected_check_exceptions_as_failures(monkeypatch, capsys):
    def raising_check(_validation, _client):
        raise RuntimeError("synthetic check failure")

    monkeypatch.setattr(validation_script, "_client", lambda: object())
    monkeypatch.setattr(validation_script, "latest_local_division_id", lambda: 2355)
    monkeypatch.setattr(validation_script, "check_routes", raising_check)

    try:
        result = validation_script.main(
            ["--skip-network-freshness", "--division-id", "2355"],
        )
    except RuntimeError as exc:
        pytest.fail(f"main raised instead of recording a FAIL line: {exc}")

    captured = capsys.readouterr()
    assert result == 1
    assert "FAIL validation error" in captured.out
    assert "synthetic check failure" in captured.out
    assert "VALIDATION FAIL" in captured.out


def test_main_empty_argv_does_not_read_sys_argv(monkeypatch, capsys):
    def noop_check(*_args, **_kwargs):
        return None

    monkeypatch.setattr(sys, "argv", ["validate_production_ready.py", "--pytest-leaked-arg"])
    monkeypatch.setattr(validation_script, "_client", lambda: object())
    monkeypatch.setattr(validation_script, "latest_local_division_id", lambda: 2355)
    monkeypatch.setattr(validation_script, "check_routes", noop_check)
    monkeypatch.setattr(validation_script, "check_source_lens", noop_check)
    monkeypatch.setattr(validation_script, "check_source_divisions", noop_check)
    monkeypatch.setattr(validation_script, "check_payloads", noop_check)
    monkeypatch.setattr(validation_script, "check_division_derivation", noop_check)
    monkeypatch.setattr(validation_script, "check_recent_division_completeness", noop_check)
    monkeypatch.setattr(validation_script, "check_full_history_completeness", noop_check)
    monkeypatch.setattr(validation_script, "check_global_feasibility", noop_check)
    monkeypatch.setattr(validation_script, "check_branding", noop_check)
    monkeypatch.setattr(validation_script, "check_network_freshness", noop_check)
    monkeypatch.setattr(validation_script, "check_official_commons_coverage", noop_check)

    try:
        result = validation_script.main([])
    except SystemExit as exc:
        pytest.fail(f"main([]) inspected sys.argv and exited: {exc}")

    captured = capsys.readouterr()
    assert result == 0
    assert "PASS latest local division" in captured.out
    assert "VALIDATION PASS" in captured.out


def test_check_payloads_requires_publicwhip_source_link_for_selected_division():
    payloads = _valid_payloads()
    for payload in payloads.values():
        payload["source_links"] = [
            {"label": "wrong division", "url": "/publicwhip/division/9999"},
        ]
    validation = validation_script.Validation()

    validation_script.check_payloads(validation, _FakeMapClient(payloads), 2355)

    assert any(
        "division source links" in failure and "/publicwhip/division/2355" in failure
        for failure in validation.failures
    )


def test_check_payloads_requires_mode_and_division_scoped_quality():
    payloads = _valid_payloads()
    payloads["party-split"]["mode"] = "vote-split"
    payloads["party-split"]["data_quality"]["division_scoped"] = False
    payloads["party-split"]["data_quality"]["selected_division_id"] = 9999
    validation = validation_script.Validation()

    validation_script.check_payloads(validation, _FakeMapClient(payloads), 2355)

    assert any(
        "division map metadata party-split" in failure
        and "data_quality" in failure
        for failure in validation.failures
    )


def test_validate_map_rows_checks_every_map_data_row():
    payloads = _valid_payloads()
    payload = payloads["vote-split"]
    valid_row = next(iter(payload["map_data"].values()))
    payload["map_data"]["Second Constituency"] = {
        **valid_row,
        "constituency": "Second Constituency",
        "mode": "party-split",
        "division_vote": "Maybe",
    }
    validation = validation_script.Validation()

    validation_script._validate_map_rows(validation, payload, "vote-split", 2355)

    assert any(
        "division map rows vote-split" in failure
        and "Second Constituency" in failure
        and "mode" in failure
        and "division_vote" in failure
        for failure in validation.failures
    )


def test_check_payloads_requires_representative_row_contract():
    payloads = _valid_payloads()
    row = next(iter(payloads["vote-split"]["map_data"].values()))
    row.pop("legend_key")
    row["division_vote"] = "Maybe"
    validation = validation_script.Validation()

    validation_script.check_payloads(validation, _FakeMapClient(payloads), 2355)

    assert any(
        "division map rows vote-split" in failure
        and "legend_key" in failure
        and "division_vote" in failure
        for failure in validation.failures
    )


def test_check_payloads_requires_consistent_constituency_set_across_modes():
    payloads = _valid_payloads()
    row = next(iter(payloads["party-split"]["map_data"].values()))
    payloads["party-split"]["map_data"] = {
        "Different Constituency": {
            **row,
            "constituency": "Different Constituency",
            "label": "Selected Division Title - Aye - different member",
        }
    }
    validation = validation_script.Validation()

    validation_script.check_payloads(validation, _FakeMapClient(payloads), 2355)

    assert any(
        "division map constituency consistency" in failure
        and "party-split" in failure
        for failure in validation.failures
    )


def test_check_payloads_requires_map_constituency_rows_to_match_map_data():
    payloads = _valid_payloads()
    payloads["gender-split"]["data_quality"]["map_constituency_rows"] = 999
    validation = validation_script.Validation()

    validation_script.check_payloads(validation, _FakeMapClient(payloads), 2355)

    assert any(
        "division map row count gender-split" in failure
        and "999" in failure
        for failure in validation.failures
    )


def test_check_payloads_requires_current_members_plus_vacancies_to_match_map_rows():
    payloads = _valid_payloads()
    payloads["rebel-split"]["data_quality"]["current_member_rows"] = 1
    payloads["rebel-split"]["data_quality"]["vacant_constituency_rows"] = 2
    payloads["rebel-split"]["data_quality"]["map_constituency_rows"] = 1
    validation = validation_script.Validation()

    validation_script.check_payloads(validation, _FakeMapClient(payloads), 2355)

    assert any(
        "division constituency/member count rebel-split" in failure
        and "current 1" in failure
        and "vacant 2" in failure
        for failure in validation.failures
    )


def test_commons_coverage_result_reconciles_official_members_and_vacancies():
    coverage_result = getattr(validation_script, "_commons_coverage_result", None)

    assert callable(coverage_result)
    assert coverage_result(
        official_constituencies=650,
        official_current_members=647,
        official_vacancies=3,
        local_constituencies=650,
        local_current_members=647,
        local_vacancies=3,
        map_constituencies=650,
        official_vacancy_names={"Aberdeen South", "Makerfield", "Arbroath and Broughty Ferry"},
        local_vacancy_names={"Aberdeen South", "Makerfield", "Arbroath and Broughty Ferry"},
    ) == (True, "650 constituencies, 647 current MPs, 3 vacancies")
    assert coverage_result(
        official_constituencies=650,
        official_current_members=647,
        official_vacancies=3,
        local_constituencies=650,
        local_current_members=647,
        local_vacancies=2,
        map_constituencies=650,
        official_vacancy_names={"Aberdeen South", "Makerfield", "Arbroath and Broughty Ferry"},
        local_vacancy_names={"Aberdeen South", "Makerfield"},
    )[0] is False
