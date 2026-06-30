"""The agent guided tour must stay real — every manifest stop must point to a
file/dir/script/route that exists. Guards against the tour decaying into "just
words" (the exact problem this artifact was built to fix).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import verify_agent_tour

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_every_tour_stop_points_to_something_real():
    problems = verify_agent_tour.verify()
    assert problems == [], "Dead tour pointers:\n" + "\n".join(problems)


def test_contributing_and_todo_exist_and_link_each_other():
    contributing = open(os.path.join(ROOT, "CONTRIBUTING.md"), encoding="utf-8").read()
    todo = open(os.path.join(ROOT, "docs", "AGENT_TODO.md"), encoding="utf-8").read()
    # The contribution on-ramp and the work list must cross-reference.
    assert "AGENT_TODO.md" in contributing
    assert "CONTRIBUTING.md" in todo
    # PR guidance must actually be present (not just promised).
    assert "pull request" in contributing.lower()
    assert "pytest" in contributing.lower()


def test_tour_covers_the_required_themes():
    tour = open(os.path.join(ROOT, "docs", "agent-guided-tour.md"), encoding="utf-8").read().lower()
    # The themes the tour must teach (ethos, contribution, education, operate).
    for theme in ("build by the public", "ethos", "contribute", "educational",
                  "self-check", "report back"):
        assert theme in tour, f"tour missing theme: {theme!r}"
