from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _read_safe(path: Path, max_chars: int) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars].strip()
    except Exception:
        return ""


def _section(title: str, body: str) -> str:
    if not body:
        return ""
    return f"## {title}\n\n{body}\n"


def _project_chat_context(max_chars: int) -> str:
    p = ROOT / "docs" / "project-chat-context.md"
    return _read_safe(p, max_chars)


def _key_docs(max_chars: int) -> str:
    docs_dir = ROOT / "docs"
    if not docs_dir.exists():
        return ""
    priority = [
        docs_dir / "DATA_SOURCES.md",
        docs_dir / "ETHICS_GUARDRAILS.md",
        docs_dir / "DEPLOY.md",
        docs_dir / "feasibility" / "README.md",
    ]
    blocks = []
    for p in priority:
        if p.exists():
            text = _read_safe(p, max_chars // 2)
            if text:
                blocks.append(f"[{p.relative_to(ROOT).as_posix()}]\n{text}")
    return "\n\n".join(blocks)


def _agent_latest(max_chars: int) -> str:
    p = ROOT / "agent-logs" / "latest.md"
    if not p.exists():
        return ""
    text = _read_safe(p, max_chars)
    return text[-max_chars:]


def _routes() -> str:
    p = ROOT / "app.py"
    if not p.exists():
        return ""
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    matches = re.findall(r'@app\.route\("([^"]+)"', text)
    if not matches:
        return ""
    lines = sorted(set(matches))
    return "\n".join(f"- `{r}`" for r in lines)


def build_context(max_chars: int = 4000, sections: list[str] | None = None) -> str:
    enabled = set(sections or ["project_chat", "docs", "agent_logs", "routes"])
    parts = []
    if "project_chat" in enabled:
        parts.append(_section("Project Chat Context", _project_chat_context(max_chars)))
    if "docs" in enabled:
        parts.append(_section("Key Docs", _key_docs(max_chars)))
    if "agent_logs" in enabled:
        parts.append(_section("Agent Latest Log", _agent_latest(max_chars)))
    if "routes" in enabled:
        parts.append(_section("App Routes", _routes()))
    return "\n".join(p for p in parts if p).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build prompt-ready YourGov context.")
    parser.add_argument("--max-chars", type=int, default=4000, help="Max chars per loaded source.")
    parser.add_argument(
        "--sections",
        type=str,
        default="project_chat,docs,agent_logs,routes",
        help="Comma-separated sections: project_chat,docs,agent_logs,routes",
    )
    parser.add_argument("--out", type=str, default="", help="Optional output file path.")
    args = parser.parse_args()

    sections = [s.strip() for s in args.sections.split(",") if s.strip()]
    output = build_context(max_chars=args.max_chars, sections=sections)

    if args.out:
        out_path = (ROOT / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"Wrote context to {out_path}")
    else:
        print(output)


if __name__ == "__main__":
    main()

