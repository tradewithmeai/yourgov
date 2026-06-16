from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "update-data.yml"


def test_data_refresh_workflow_runs_update_at_4am_uk_and_validation_after_delay():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "YourGov Data Refresh" in workflow
    assert "workflow_dispatch:" in workflow
    assert "contents: write" in workflow
    # Dual cron + Europe/London gate keeps the active run at 04:00 UK year-round
    # despite GitHub cron having no DST handling.
    assert "0 3 * * *" in workflow
    assert "0 4 * * *" in workflow
    assert "TZ=Europe/London" in workflow
    assert "sleep 60" in workflow

    update_index = workflow.index("scripts/update_publicwhip_data.py")
    delay_index = workflow.index("sleep 60")
    validation_index = workflow.index("scripts/validate_production_ready.py")
    commit_index = workflow.index("git commit -m")

    assert update_index < delay_index < validation_index < commit_index
    # Validation must remain a real production check, never a skipped-freshness run.
    assert "--skip-network-freshness" not in workflow


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
