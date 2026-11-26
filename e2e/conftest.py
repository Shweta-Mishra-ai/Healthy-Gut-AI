"""Browser end-to-end suite: runs the real app and a fake WordPress server as
subprocesses and drives Chromium through every user flow.

Run:  python -m playwright install chromium   (once)
      python -m pytest e2e -q
In a sandbox with a preinstalled Chromium, point PLAYWRIGHT_CHROMIUM_EXECUTABLE at it.
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
API_KEY = "e2e-key"
REVIEWER = {"id": "rao", "name": "Dr. Anita Rao", "credential": "MD (Gastroenterology)", "registration": "DMC-4521"}
# Errors a test provokes on purpose (validation, missing key, rate limit) and
# web-font fetches that a sandbox without internet cannot make.
EXPECTED_CONSOLE = ("status of 401", "status of 403", "status of 404", "status of 422", "status of 429",
                    "ERR_CERT", "ERR_NAME_NOT_RESOLVED", "ERR_TUNNEL", "ERR_CONNECTION")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for(url: str, timeout: float = 40) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except OSError:
            time.sleep(0.25)
    raise RuntimeError(f"server at {url} did not start")


@pytest.fixture(scope="session")
def servers(tmp_path_factory):
    wp_port, app_port = _free_port(), _free_port()
    quiet = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    wp = subprocess.Popen([sys.executable, "-m", "uvicorn", "fake_wordpress:app", "--port", str(wp_port)],
                          cwd=Path(__file__).parent, **quiet)
    env = {
        **os.environ,
        "DATABASE_PATH": str(tmp_path_factory.mktemp("db") / "e2e.db"),
        "API_KEY": API_KEY,
        "REVIEWERS_JSON": json.dumps([REVIEWER]),
        "WORDPRESS_URL": f"http://127.0.0.1:{wp_port}",
        "WORDPRESS_USERNAME": "editor",
        "WORDPRESS_APP_PASSWORD": "x",
        "RATE_LIMIT_PER_MINUTE": "1000",
        "LOG_LEVEL": "WARNING",
    }
    for var in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "ALLOW_UNAUTHENTICATED", "REVIEWERS_FILE"):
        env.pop(var, None)
    app = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(app_port)],
                           cwd=ROOT, env=env, **quiet)
    try:
        _wait_for(f"http://127.0.0.1:{wp_port}/_posts")
        _wait_for(f"http://127.0.0.1:{app_port}/health")
        yield {"app": f"http://127.0.0.1:{app_port}", "wp": f"http://127.0.0.1:{wp_port}"}
    finally:
        for proc in (app, wp):
            proc.terminate()
            proc.wait(timeout=10)


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        executable = os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or None
        b = p.chromium.launch(executable_path=executable)
        yield b
        b.close()


def _open_page(browser, servers, *, with_key: bool, viewport=None):
    context = browser.new_context(accept_downloads=True, viewport=viewport or {"width": 1280, "height": 900})
    if with_key:
        context.add_init_script(f"localStorage.setItem('gutfolio.apiKey', {json.dumps(API_KEY)})")
    page = context.new_page()
    page.set_default_timeout(30000)
    page.base = servers["app"]
    page.unexpected_errors = []

    def on_console(message):
        if message.type == "error" and not any(s in message.text for s in EXPECTED_CONSOLE):
            page.unexpected_errors.append(message.text)

    page.on("console", on_console)
    page.on("pageerror", lambda exc: page.unexpected_errors.append(f"pageerror: {exc}\n{getattr(exc, 'stack', '')}"))
    return context, page


@pytest.fixture
def page(browser, servers):
    context, pg = _open_page(browser, servers, with_key=True)
    yield pg
    errors = list(pg.unexpected_errors)
    context.close()
    # Script errors and CSP violations ("Refused to ...") fail the test.
    assert not errors, errors


@pytest.fixture
def make_page(browser, servers):
    opened = []

    def factory(**kwargs):
        context, pg = _open_page(browser, servers, **kwargs)
        opened.append(context)
        return pg

    yield factory
    for context in opened:
        context.close()
