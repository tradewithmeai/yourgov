import importlib
import re
import subprocess
import sys
from html import unescape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


PUBLIC_ROUTES = (
    "/",
    "/source-lens",
    "/global",
    "/welcome",
    "/publicwhip",
    "/publicwhip/divisions",
    "/publicwhip/mps",
    "/publicwhip/division/2355",
    "/publicwhip/mp/206",
    "/map",
    "/map/pro",
)

# Every route in this branding slice carries a first-party identity strip or shell.
ROUTES_WITHOUT_FIRST_PARTY_BRAND = frozenset()

PUBLIC_SCAN_SPECS = (
    "app.py",
    "README.md",
    "docs",
    "templates",
    "static",
    "android-mygov/README.md",
    "android-mygov/app/src/main/res/values/strings.xml",
    "ios-mygov/README.md",
    "ios-mygov/project.yml",
    "ios-mygov/MyGov/ContentView.swift",
)

EXCLUDED_SCAN_PREFIXES = (
    "docs/project-chat-context.md",
    "docs/superpowers/specs/",
    "docs/superpowers/plans/",
    "static/map-assets/",
)

TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".svg",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

ALLOWED_COMPATIBILITY_PATTERNS = (
    r"\bmygov\.db\b",
    r"\bMYGOV_[A-Z0-9_]+\b",
    r"\bmygov:[a-z:*\-]+\b",
    r"\buk\.mygov[\w.]*\b",
    r"\bandroid-mygov\b",
    r"\bios-mygov\b",
    r"\bTheme\.MyGov\b",
    r"\bMyGov\.xcodeproj\b",
    r"\bMyGov\.xcarchive\b",
    r"\bMyGov/Info\.plist\b",
    r"\bMyGov-release\b",
    r"\bMyGov-iOS\b",
    r"\bMyGov_AppStore\b",
    r"\bstruct\s+MyGovApp\b",
    r"^\s*name:\s*MyGov\s*$",
    r"^\s*-\s*path:\s*MyGov\s*$",
)


def _client():
    appmod = importlib.import_module("app")
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _tracked_public_text_files():
    result = subprocess.run(
        ["git", "ls-files", "--", *PUBLIC_SCAN_SPECS],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    paths = []
    for rel_path in result.stdout.splitlines():
        normalized = rel_path.replace("\\", "/")
        if any(normalized == prefix.rstrip("/") or normalized.startswith(prefix) for prefix in EXCLUDED_SCAN_PREFIXES):
            continue
        path = ROOT / normalized
        if path.suffix.lower() in TEXT_SUFFIXES:
            paths.append(path)
    return paths


def _without_allowed_compatibility_tokens(line):
    scrubbed = line
    for pattern in ALLOWED_COMPATIBILITY_PATTERNS:
        scrubbed = re.sub(pattern, "", scrubbed)
    return scrubbed


def _normalized_visible_text(markup):
    without_invisible_blocks = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", markup)
    without_tags = re.sub(r"(?s)<[^>]+>", "", without_invisible_blocks)
    return re.sub(r"\s+", " ", unescape(without_tags)).strip()


def _local_script_asset_texts(markup):
    for src in re.findall(r"""<script\b[^>]*\bsrc=["']([^"']+)["']""", markup):
        if not src.startswith("/static/"):
            continue
        asset_path = ROOT / src.lstrip("/")
        if asset_path.suffix.lower() == ".js" and asset_path.is_file():
            yield asset_path.read_text(encoding="utf-8")


def _rendered_route_branding_text(route, body):
    chunks = [_normalized_visible_text(body)]
    if route == "/map/pro":
        chunks.extend(_local_script_asset_texts(body))
    return "\n".join(chunks)


def test_key_public_routes_use_yourgov_branding_without_old_product_copy():
    client = _client()

    for route in PUBLIC_ROUTES:
        response = client.get(route)
        assert response.status_code == 200, route
        body = response.get_data(as_text=True)
        visible_branding_text = _rendered_route_branding_text(route, body)

        assert "MyGov" not in visible_branding_text, route
        if route not in ROUTES_WITHOUT_FIRST_PARTY_BRAND:
            assert "YourGov" in visible_branding_text, route


def test_static_svg_assets_exist_and_avoid_official_styling():
    for asset_name in ("yourgov-logo.svg", "yourgov-mark.svg", "favicon.svg"):
        body = (ROOT / "static" / "img" / asset_name).read_text(encoding="utf-8")
        normalized = body.lower()

        assert "<svg" in normalized
        assert "yourgov" in normalized or "yg" in normalized
        assert "crown" not in normalized
        assert "gov.uk" not in normalized


def test_public_text_files_do_not_contain_visible_mygov_copy():
    violations = []

    for path in _tracked_public_text_files():
        rel_path = path.relative_to(ROOT).as_posix()
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "MyGov" in _without_allowed_compatibility_tokens(line):
                violations.append(f"{rel_path}:{line_no}: {line.strip()}")

    assert violations == []


def test_ios_release_workflow_uses_yourgov_scheme():
    workflow = (ROOT / ".github" / "workflows" / "ios-release.yml").read_text(encoding="utf-8")

    assert not re.search(r"(?m)^\s*SCHEME:\s*MyGov\s*$", workflow)
    assert re.search(r"(?m)^\s*SCHEME:\s*YourGov\s*$", workflow)
    assert 'name: "MyGov iOS' not in workflow
    assert 'name: "YourGov iOS' in workflow
