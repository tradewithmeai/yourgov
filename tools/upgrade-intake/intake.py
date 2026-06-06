"""
Multi-channel intake -> append-only upgrade-request queue.

Channels: telegram, whatsapp, email. All three normalise into the SAME
append-only queue schema (see schema.json). Public feedback is data only.

Safety model (read this before changing anything):

- Polling / file consumption only. We never expose an inbound webhook.
- Allowlist enforced per channel. Anything outside is silently dropped.
- Message text is NEVER executed, eval'd, exec'd, shell'd, or passed to a
  template engine. It is a data string.
- We only ever APPEND to the queue file. We never edit, delete, rewrite,
  commit, push, or open PRs.
- If a selected channel's config is missing/placeholder, we FAIL CLOSED
  (exit non-zero) and write nothing.
- Dedupe by stable content hash; per-channel cursors avoid re-fetching.
- The raw message body is preserved verbatim for audit.

Run:
    python tools/upgrade-intake/intake.py --once --channels telegram,email,whatsapp
    python tools/upgrade-intake/intake.py --poll --channels telegram,email
    python tools/upgrade-intake/intake.py --once --whatsapp-jsonl <path>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import core
from adapters import email_imap, telegram, whatsapp_jsonl

CONFIG_FILE = core.HERE / "config.json"
VALID_CHANNELS = ("telegram", "whatsapp", "email")


def load_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        print(
            f"[intake] config not found at {CONFIG_FILE}. "
            f"Copy config.example.json -> config.json and fill it in.",
            file=sys.stderr,
        )
        sys.exit(2)
    try:
        # utf-8-sig tolerates a UTF-8 BOM, which Windows editors / PowerShell
        # often prepend when a user hand-creates config.json.
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        print(f"[intake] config.json is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(2)


def check_channel_config(channel: str, cfg: dict[str, Any], whatsapp_jsonl_path: str | None) -> None:
    """Fail closed if a selected channel lacks required config."""
    if channel == "telegram":
        ok, why = telegram.required_config_ok(cfg)
    elif channel == "email":
        ok, why = email_imap.required_config_ok(cfg)
    elif channel == "whatsapp":
        ok, why = whatsapp_jsonl.required_config_ok(cfg, whatsapp_jsonl_path)
    else:
        ok, why = False, f"unknown channel {channel!r}"
    if not ok:
        print(f"[intake] channel '{channel}' not configured: {why}. Refusing to start.", file=sys.stderr)
        sys.exit(2)


def run_channel(channel: str, cfg: dict[str, Any], whatsapp_jsonl_path: str | None) -> list[dict[str, Any]]:
    if channel == "telegram":
        return telegram.poll(cfg)
    if channel == "email":
        return email_imap.poll(cfg)
    if channel == "whatsapp":
        return whatsapp_jsonl.poll(cfg, whatsapp_jsonl_path)
    return []


def run_once(channels: list[str], cfg: dict[str, Any], whatsapp_jsonl_path: str | None) -> None:
    seen = core.load_seen_ids()
    to_write: list[dict[str, Any]] = []
    per_channel: dict[str, int] = {}
    dropped_dupe = 0

    for channel in channels:
        records = run_channel(channel, cfg, whatsapp_jsonl_path)
        kept = 0
        for rec in records:
            if rec["id"] in seen:
                dropped_dupe += 1
                continue
            seen.add(rec["id"])
            to_write.append(rec)
            kept += 1
        per_channel[channel] = kept

    written = core.append_records(to_write)
    junk = sum(1 for r in to_write if r.get("status") == "junk")
    by_channel = " ".join(f"{c}={n}" for c, n in per_channel.items())
    print(f"[intake] queued={written} junk={junk} dropped_dupe={dropped_dupe} ({by_channel})")


def run_poll(channels: list[str], cfg: dict[str, Any], whatsapp_jsonl_path: str | None) -> None:
    interval = max(5, int(cfg.get("poll_interval_seconds") or 60))
    print(f"[intake] polling channels={','.join(channels)} every {interval}s. Ctrl+C to stop.")
    try:
        while True:
            run_once(channels, cfg, whatsapp_jsonl_path)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("[intake] stopped by user.")


def parse_channels(raw: str) -> list[str]:
    channels = [c.strip().lower() for c in raw.split(",") if c.strip()]
    bad = [c for c in channels if c not in VALID_CHANNELS]
    if bad:
        print(f"[intake] unknown channel(s): {', '.join(bad)}. Valid: {', '.join(VALID_CHANNELS)}", file=sys.stderr)
        sys.exit(2)
    if not channels:
        print("[intake] no channels selected.", file=sys.stderr)
        sys.exit(2)
    return channels


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Multi-channel -> append-only upgrade queue.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="Poll/consume once and exit.")
    mode.add_argument("--poll", action="store_true", help="Poll forever on an interval.")
    parser.add_argument(
        "--channels",
        default=None,
        help="Comma-separated channels to run: telegram,whatsapp,email. "
        "Defaults to telegram, or to whatsapp alone when --whatsapp-jsonl is given.",
    )
    parser.add_argument(
        "--whatsapp-jsonl",
        default=None,
        help="Path to the WhatsApp bridge JSONL. Implies the whatsapp channel.",
    )
    args = parser.parse_args(argv)

    cfg = load_config()

    # Channel selection: explicit --channels wins; otherwise default to
    # whatsapp alone when a JSONL path is given, else telegram (back-compat).
    if args.channels:
        channels = parse_channels(args.channels)
    elif args.whatsapp_jsonl:
        channels = ["whatsapp"]
    else:
        channels = ["telegram"]
    if args.whatsapp_jsonl and "whatsapp" not in channels:
        channels.append("whatsapp")

    for channel in channels:
        check_channel_config(channel, cfg, args.whatsapp_jsonl)

    if args.once:
        run_once(channels, cfg, args.whatsapp_jsonl)
    else:
        run_poll(channels, cfg, args.whatsapp_jsonl)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
