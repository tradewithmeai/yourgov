#!/usr/bin/env python3
"""YourGov demo walkthrough — a runnable script that DRIVES the site through the
core user journey, end to end: land -> search a postcode -> see the MP + record
-> explain a vote in plain English -> contact the MP.

It uses postcode CO3 4ED (returns Pam Cox, Labour, Colchester) so the run is
reproducible. It narrates each step to the console and saves a screenshot per
step, so you can watch the journey happen and keep the frames.

Usage:
    pip install playwright && playwright install chromium     # one-time
    python scripts/demo_walkthrough.py                        # watch it live (headed)
    python scripts/demo_walkthrough.py --headless             # no window (for CI / screenshots only)
    python scripts/demo_walkthrough.py --base http://127.0.0.1:5050   # run against a local app
    python scripts/demo_walkthrough.py --postcode "SW1A 1AA"  # try a different postcode

Flags:
    --headed/--headless   show the browser window (default: headed, so you can watch)
    --slow <ms>           per-action delay so steps are visible (default: 700)
    --base <url>          site to drive (default: https://yourgov.solvx.uk)
    --postcode <pc>       postcode to search (default: CO3 4ED)
    --shots <dir>         screenshot output dir (default: ./demo-shots)
"""
from __future__ import annotations

import argparse
import os
import sys
import time

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

STEP = 0


def banner(msg: str) -> None:
    global STEP
    STEP += 1
    print(f"\n=== STEP {STEP} — {msg} ===", flush=True)


def shot(page, shots_dir: str, name: str) -> None:
    path = os.path.join(shots_dir, f"{STEP:02d}-{name}.png")
    page.screenshot(path=path)
    print(f"   [screenshot] {path}")


def run(base: str, postcode: str, headed: bool, slow: int, shots_dir: str) -> int:
    os.makedirs(shots_dir, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed, slow_mo=slow)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.set_default_timeout(20000)
        try:
            # ── STEP 1: Landing ──────────────────────────────────────────────
            banner("Landing — the site opens on the UK map")
            page.goto(f"{base}/", wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle")
            print(f"   landed on: {page.url}")
            # Suppress the optional tour so it doesn't intercept demo clicks.
            page.evaluate("() => { try { sessionStorage.setItem('mygov:lensTourSeen','1'); } catch(e){} "
                          "document.querySelectorAll('#tour-overlay,.tour-overlay').forEach(e=>e.remove()); }")
            intro = page.locator(".yg-intro").first
            if intro.count():
                print("   left panel shows the YourGov intro:",
                      page.locator(".yg-intro-lead").first.inner_text()[:80])
            shot(page, shots_dir, "landing")

            # ── STEP 2: Search the postcode ──────────────────────────────────
            banner(f"Search — type the postcode {postcode!r}")
            trigger = page.locator("#map-search-trigger")
            if trigger.count():
                trigger.click()
            box = page.locator("#mp-search-input")
            box.click()
            box.type(postcode, delay=90)          # typed, so the inline completion shows
            print(f"   typed '{postcode}' into the centre search")
            # Wait for the inline autocomplete (debounce 250ms + postcode lookup)
            # to populate the ghost completion before accepting it. Pressing Enter
            # too early just runs a plain search with nothing to accept.
            try:
                page.wait_for_function(
                    "() => { const t=document.querySelector('.map-search-ghost .tail');"
                    " return t && t.textContent && t.textContent.trim().length > 0; }",
                    timeout=8000,
                )
                print("   inline completion populated — accepting it")
            except PWTimeout:
                print("   (no inline completion yet — pressing Enter to search anyway)")
            shot(page, shots_dir, "search-typed")
            box.press("Enter")

            # ── STEP 3: Meet the MP ──────────────────────────────────────────
            banner("Meet your MP — the pinned card + voting record load")
            page.wait_for_selector("#mp-info-card:not([hidden]) .mp-info-name", timeout=25000)
            mp_name = page.locator(".mp-info-name").first.inner_text().strip()
            mp_meta = page.locator(".mp-info-meta").first.inner_text().strip()
            print(f"   MP card: {mp_name}  ({mp_meta})")
            votes = page.locator(".mp-info-votes").first
            if votes.count():
                print(f"   {votes.inner_text().strip()}")
            shot(page, shots_dir, "mp-card")

            # ── STEP 4: A real vote ──────────────────────────────────────────
            banner("A real vote — pick a division from the record")
            row = page.locator(".division-rows .division-row, #source-lens-list .division-row").first
            page.wait_for_selector(".division-rows .division-row, #source-lens-list .division-row", timeout=15000)
            vote_text = " ".join(row.inner_text().split())[:120]
            print(f"   first vote on the record: {vote_text}")
            row.scroll_into_view_if_needed()
            shot(page, shots_dir, "vote-row")

            # ── STEP 5: Explain it ───────────────────────────────────────────
            banner("Explain Mode — plain-English explanation of the vote")
            # Collapse the expanded search pill first — while expanded it overlaps
            # the Explain toggle at the centre of the map menu.
            try:
                page.locator("#mp-search-input").press("Escape")
                page.wait_for_selector("#map-search.is-collapsed", timeout=4000)
            except PWTimeout:
                page.mouse.click(1200, 450)  # click the map to blur/collapse
                time.sleep(0.3)
            # The Explain toggle is a ring concentric with the centre search "S",
            # so a positional click lands on the S. Fire its handler directly.
            explained = page.evaluate(
                "() => { const b=document.querySelector(\"[data-action='explain']\");"
                " if(b){ b.click(); return true; } return false; }"
            )
            print(f"   Explain Mode toggled: {explained}")
            time.sleep(0.5)
            try:
                row.click()
                page.wait_for_selector("#explain-drawer.open #ed-meaning, #ed-meaning", timeout=20000)
                # Let the explanation populate (it replaces the 'Loading…' text).
                page.wait_for_function(
                    "() => { const m=document.getElementById('ed-meaning');"
                    " return m && m.textContent && !m.classList.contains('loading'); }",
                    timeout=25000,
                )
                meaning = page.locator("#ed-meaning").first.inner_text().strip()
                print(f"   explanation: {meaning[:200]}")
                shot(page, shots_dir, "explain-drawer")
            except PWTimeout:
                print("   (explainer drawer did not open in time — skipping, non-fatal)")

            # ── STEP 6: Contact the MP ───────────────────────────────────────
            banner("Contact — the Email/Contact action on the MP card")
            # Close the drawer if open so the card is clickable.
            page.keyboard.press("Escape")
            contact = page.locator(".mp-info-contact").first
            page.wait_for_selector(".mp-info-contact", timeout=10000)
            label = contact.inner_text().strip()
            href = contact.get_attribute("href") or ""
            print(f"   contact action: '{label}'  ->  {href}")
            shot(page, shots_dir, "contact")

            # ── STEP 7: Explore the map ──────────────────────────────────────
            banner("Explore — switch the map to Party mode (Reform is in the legend)")
            # Close the explain drawer + its backdrop if still open, else the
            # backdrop intercepts clicks on the map controls.
            page.evaluate(
                "() => { const d=document.getElementById('explain-drawer');"
                " const b=document.getElementById('explain-drawer-backdrop');"
                " if(d) d.classList.remove('open'); if(b) b.classList.remove('visible'); }"
            )
            time.sleep(0.3)
            # Party wedge sits in the radial menu (overlaps the centre S), so fire
            # its handler directly, as with the Explain toggle.
            switched = page.evaluate(
                "() => { const b=document.getElementById('topic-party-split');"
                " if(b){ b.click(); return true; } return false; }"
            )
            print(f"   switched to Party mode: {switched}")
            time.sleep(1.0)
            legend = page.locator("#map-legend").first
            if legend.count():
                print("   legend:", " ".join(legend.inner_text().split())[:120])
            shot(page, shots_dir, "map-party-mode")

            print("\n=== DEMO COMPLETE — journey driven end to end ===")
            print(f"   postcode {postcode} -> {mp_name} -> a real vote -> explained -> contact ready")
            print(f"   {STEP} screenshots saved in {shots_dir}/")
            if headed:
                print("   (window stays open 4s so you can see the final frame)")
                time.sleep(4)
            return 0
        except Exception as exc:
            print(f"\n!!! demo step failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            try:
                shot(page, shots_dir, "error")
            except Exception:
                pass
            return 1
        finally:
            browser.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Drive the YourGov user journey as a live demo.")
    ap.add_argument("--base", default="https://yourgov.solvx.uk")
    ap.add_argument("--postcode", default="CO3 4ED")
    ap.add_argument("--slow", type=int, default=700, help="per-action delay in ms (visibility)")
    ap.add_argument("--shots", default="demo-shots")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--headed", dest="headed", action="store_true", default=True)
    g.add_argument("--headless", dest="headed", action="store_false")
    a = ap.parse_args()
    print(f"YourGov demo walkthrough — driving {a.base} with postcode {a.postcode}")
    print(f"mode: {'headed (watch it)' if a.headed else 'headless'} · slow_mo {a.slow}ms")
    return run(a.base, a.postcode, a.headed, a.slow, a.shots)


if __name__ == "__main__":
    raise SystemExit(main())
