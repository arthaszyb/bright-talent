"""Browser smoke tests for the console SPA (the only untested surface).

Guards the rendering contract end to end: the fleet view must render the
repo's single instance exactly once (a startup double-render once
duplicated every card), and the detail view must show the instance
identity. Runs the real FastAPI app against this repo with a throwaway DB.

Kept in tests_e2e/ (not tests/) so the plain pytest suite stays
browser-free; CI runs this via the frontend-e2e job after
`playwright install chromium`. Locally, a preinstalled chromium is picked
up from $PLAYWRIGHT_BROWSERS_PATH/chromium when present.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

REPO_ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def console_url(tmp_path_factory):
    port = _free_port()
    db_path = tmp_path_factory.mktemp("db") / "console.db"
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "console.app",
            "--repo", str(REPO_ROOT), "--port", str(port), "--db-path", str(db_path),
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(f"{url}/api/health", timeout=1)
                break
            except OSError:
                time.sleep(0.2)
        else:
            pytest.fail("console app did not become healthy")
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture(scope="module")
def page(console_url):
    launch_kwargs = {}
    browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    wrapper = Path(browsers_path) / "chromium" if browsers_path else None
    if wrapper is not None and wrapper.is_file():
        launch_kwargs["executable_path"] = str(wrapper)
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch(**launch_kwargs)
        except Exception as exc:  # no browser in this environment -> skip, not fail
            pytest.skip(f"chromium unavailable: {exc}")
        page = browser.new_page()
        yield page
        browser.close()


def test_fleet_renders_single_instance_card_exactly_once(page, console_url):
    page.goto(f"{console_url}/#/fleet")
    page.wait_for_selector(".card")
    # Regression guard: a double route() on startup once rendered two copies
    # of every fleet card.
    assert page.locator(".card").count() == 1
    assert "acme-checkout-sre" in page.locator(".card h3").inner_text()


def test_header_and_tabs_present(page, console_url):
    page.goto(f"{console_url}/#/fleet")
    page.wait_for_selector("header, nav.tabs")
    assert "Staff Fleet Governance Console" in page.content()


def test_instance_detail_shows_identity(page, console_url):
    page.goto(f"{console_url}/#/instances/acme-checkout-sre")
    page.wait_for_selector("table")
    body = page.content()
    assert "DE-ACME-CHECKOUT-001" in body
    assert "acme.storefront.checkout" in body
