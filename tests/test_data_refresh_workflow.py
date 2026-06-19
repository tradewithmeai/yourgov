from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "update-data.yml"


def test_data_refresh_workflow_runs_daily_and_validates_after_delay():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "YourGov Data Refresh" in workflow
    assert "workflow_dispatch:" in workflow
    assert "contents: write" in workflow
    # Two daily UTC crons cover the ~04:00 UK quiet window year-round and add
    # redundancy if GitHub drops a run.
    assert "0 3 * * *" in workflow
    assert "0 4 * * *" in workflow
    assert "sleep 60" in workflow

    update_index = workflow.index("scripts/update_publicwhip_data.py")
    delay_index = workflow.index("sleep 60")
    validation_index = workflow.index("scripts/validate_production_ready.py")
    commit_index = workflow.index("git commit -m")

    assert update_index < delay_index < validation_index < commit_index
    # Validation must remain a real production check, never a skipped-freshness run.
    assert "--skip-network-freshness" not in workflow


def test_data_refresh_has_no_brittle_exact_clock_gate():
    """Regression guard: GitHub scheduled runs drift by hours on shared runners,
    so an "only proceed at exactly 04:00 Europe/London" gate skipped every run
    and froze the data. The updater must run on every trigger, not behind a
    wall-clock gate."""
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "date +%H" not in workflow
    assert "needs: gate" not in workflow
    assert "Gate to 04:00" not in workflow


def test_data_refresh_workflow_commits_gzipped_seed_after_validation():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    # The full-history seed is too large for GitHub raw, so it ships gzipped: the
    # workflow restores it before the updater and re-commits the archive.
    assert "gunzip -kf mygov.db.gz" in workflow
    assert "gzip -9 -n -c mygov.db > mygov.db.gz" in workflow
    assert "git add mygov.db.gz" in workflow
    assert "git diff --quiet -- mygov.db.gz" in workflow
    assert "chore: refresh parliamentary data" in workflow
    assert "concurrency:" in workflow

    # Restore must happen before the updater so history is topped up, not lost.
    restore_index = workflow.index("gunzip -kf mygov.db.gz")
    update_index = workflow.index("scripts/update_publicwhip_data.py")
    assert restore_index < update_index


def test_data_refresh_workflow_triggers_live_deploy_and_alerts_on_failure():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    # Fresh data committed here must trigger the separate solvx-website deploy,
    # otherwise the live site keeps serving the stale bundled database.
    assert "repos/tradewithmeai/solvx-website/dispatches" in workflow
    assert "yourgov-data-refresh" in workflow
    assert "DEPLOY_DISPATCH_TOKEN" in workflow
    # The deploy fires only when a refresh actually committed new data.
    deploy_index = workflow.index("solvx-website/dispatches")
    commit_index = workflow.index("git commit -m")
    assert commit_index < deploy_index

    # A failed scheduled run must surface, not fail silently.
    assert "if: failure()" in workflow
    assert "gh issue create" in workflow
    # A missing deploy token must FAIL loudly (firing the alert), never pass green
    # while production silently serves stale data.
    assert "::error::DEPLOY_DISPATCH_TOKEN not set" in workflow
