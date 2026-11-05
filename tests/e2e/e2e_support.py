"""E2E テスト共通：アプリを別プロセスで起動し、Chrome で操作する。"""
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AI_PASSWORD = "e2e-password"  # テスト用の値（公開サイトのパスワードではない）


@pytest.fixture(autouse=True)
def no_paid_api():
    """E2E は別プロセスのアプリを操作するので、conftest の API 差し替えを使わない（この上書きで無効にする）。"""


@pytest.fixture
def ai_password():
    return AI_PASSWORD


@pytest.fixture(scope="module")
def app_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    exe = os.path.join(os.path.dirname(sys.executable), "streamlit")
    proc = subprocess.Popen([exe, "run", "app.py", "--server.port", str(port), "--server.headless", "true"], cwd=ROOT,
                            env={**os.environ, "RP_ACCESS_CODES": AI_PASSWORD}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://localhost:{port}"
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(url + "/_stcore/health", timeout=2)
                break
            except OSError:
                time.sleep(1)
        yield url
    finally:
        proc.terminate()


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        yield b
        b.close()
