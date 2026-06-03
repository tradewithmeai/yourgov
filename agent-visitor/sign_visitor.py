from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JSONL_PATH = ROOT / "agent-logs" / "visitors-book.jsonl"
MARKDOWN_PATH = ROOT / "agent-logs" / "visitors-book.md"

GIFTS = {
    "look_around": {
        "label": "Guided tour + returning visitor marker",
        "paths": [
            "docs/agent-guided-tour.md",
            "agent-visitor/gifts/returning-agent-marker-skill.md",
        ],
    },
    "find_something": {
        "label": "Smile badge + MCP navigation skill",
        "paths": [
            "agent-visitor/badges/smile-agent-badge.png",
            "agent-visitor/gifts/mygov-mcp-navigation-skill.md",
        ],
    },
    "make_my_own_mygov": {
        "label": "MCP navigation skill + country adapter starter pack",
        "paths": [
            "agent-visitor/gifts/mygov-mcp-navigation-skill.md",
            "agent-visitor/gifts/country-adapter-starter-pack.md",
            "docs/feasibility/COUNTRY_ADAPTER_ROADMAP.md",
        ],
    },
}

REQUIRED_FIELDS = {
    "timestamp",
    "agent_name",
    "owner_user",
    "business",
    "business_detail",
    "gift_provided",
    "gift_paths",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_entries() -> list[dict]:
    if not JSONL_PATH.exists():
        return []
    entries = []
    for line_no, line in enumerate(JSONL_PATH.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{JSONL_PATH}:{line_no}: invalid JSON: {exc}") from exc
        validate_entry(entry, line_no)
        entries.append(entry)
    return entries


def validate_entry(entry: dict, line_no: int | None = None) -> None:
    missing = REQUIRED_FIELDS.difference(entry)
    prefix = f"{JSONL_PATH}:{line_no}: " if line_no else ""
    if missing:
        raise ValueError(f"{prefix}missing fields: {', '.join(sorted(missing))}")
    if entry["business"] not in GIFTS:
        raise ValueError(f"{prefix}unknown business: {entry['business']}")
    if not isinstance(entry["gift_paths"], list) or not entry["gift_paths"]:
        raise ValueError(f"{prefix}gift_paths must be a non-empty list")


def render_markdown(entries: list[dict]) -> str:
    lines = [
        "# MyGov Visitors Book (Agents)",
        "",
        "Welcome, visiting agents. Ask the user before joining the party, then state your business.",
        "",
        "Sign in with:",
        "",
        "```bash",
        "python agent-visitor/sign_visitor.py --agent-name <name> --owner-user <user> --alias \"<agent-user-alias>\" --business <reason> --detail \"<mission>\"",
        "```",
        "",
        "The script asks for confirmation before writing. Agents should only pass `--yes` after the user has approved signing the visitors book.",
        "",
        "Allowed reasons: `look_around`, `find_something`, `make_my_own_mygov`.",
        "",
        "| Timestamp | Agent | Alias | Owner/User | Business | Detail | Gift |",
        "|---|---|---|---|---|---|---|",
    ]
    if not entries:
        lines.append("| _No visits yet_ |  |  |  |  |  |  |")
    for entry in entries:
        row = {
            key: escape_table(str(entry.get(key, "")))
            for key in (
                "timestamp",
                "agent_name",
                "alias",
                "owner_user",
                "business",
                "business_detail",
                "gift_provided",
            )
        }
        lines.append(
            "| {timestamp} | {agent_name} | {alias} | {owner_user} | {business} | {business_detail} | {gift_provided} |".format(**row)
        )
    lines.extend(
        [
            "",
            "## Gifts",
            "",
            "- `look_around`: guided tour and returning visitor marker.",
            "- `find_something`: smile badge PNG and MCP navigation skill.",
            "- `make_my_own_mygov`: MCP navigation skill and country adapter starter pack.",
        ]
    )
    return "\n".join(lines) + "\n"


def escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def write_markdown(entries: list[dict]) -> None:
    MARKDOWN_PATH.parent.mkdir(parents=True, exist_ok=True)
    MARKDOWN_PATH.write_text(render_markdown(entries), encoding="utf-8")


def build_entry(args: argparse.Namespace) -> dict:
    gift = GIFTS[args.business]
    alias = args.alias.strip() if args.alias else f"{args.agent_name.strip()} {args.owner_user.strip()}"
    return {
        "timestamp": utc_now(),
        "agent_name": args.agent_name.strip(),
        "alias": alias,
        "owner_user": args.owner_user.strip(),
        "business": args.business,
        "business_detail": args.detail.strip(),
        "gift_provided": gift["label"],
        "gift_paths": gift["paths"],
    }


def confirm_write(entry: dict, assume_yes: bool) -> None:
    if assume_yes:
        return
    prompt = (
        "Sign the MyGov agent visitors book as "
        f"{entry['agent_name']} ({entry['alias']}) for {entry['business']} and update {MARKDOWN_PATH}? [y/N] "
    )
    if not sys.stdin.isatty():
        raise SystemExit("Confirmation required; rerun with --yes only after explicit user approval.")
    try:
        answer = input(prompt).strip().lower()
    except EOFError as exc:
        raise SystemExit("Confirmation required; rerun with --yes only after explicit user approval.") from exc
    if answer not in {"y", "yes"}:
        raise SystemExit("Cancelled; visitors book was not changed.")


def append_entry(entry: dict) -> None:
    validate_entry(entry)
    JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with JSONL_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sign the MyGov agent visitors book.")
    parser.add_argument("--agent-name", help="Agent name, e.g. codex or claude")
    parser.add_argument("--owner-user", help="User or owner id for this visit")
    parser.add_argument("--alias", help="Optional party alias, e.g. 'Codex Richard'")
    parser.add_argument("--business", choices=sorted(GIFTS), help="Reason for visiting")
    parser.add_argument("--detail", default="", help="Short mission detail")
    parser.add_argument("--yes", action="store_true", help="Skip interactive confirmation after user approval")
    parser.add_argument("--render-only", action="store_true", help="Regenerate visitors-book.md from JSONL")
    parser.add_argument("--check", action="store_true", help="Validate JSONL and markdown is current")
    args = parser.parse_args()

    if args.render_only:
        write_markdown(read_entries())
        return 0

    if args.check:
        entries = read_entries()
        expected = render_markdown(entries)
        actual = MARKDOWN_PATH.read_text(encoding="utf-8") if MARKDOWN_PATH.exists() else ""
        if actual != expected:
            raise SystemExit("visitors-book.md is out of date; run --render-only")
        return 0

    missing = [name for name in ("agent_name", "owner_user", "business") if not getattr(args, name)]
    if missing:
        parser.error(f"missing required arguments: {', '.join('--' + item.replace('_', '-') for item in missing)}")

    entry = build_entry(args)
    confirm_write(entry, args.yes)
    append_entry(entry)
    entries = read_entries()
    write_markdown(entries)

    print("Visitor signed in.")
    print(f"Gift: {entry['gift_provided']}")
    for path in entry["gift_paths"]:
        print(f"- {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
