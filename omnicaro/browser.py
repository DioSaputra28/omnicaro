"""Peluncuran browser cross-platform.

Urutan pemilihan executable:
1. `browser.executable` di config (path eksplisit)
2. env `OMNICARO_BROWSER`
3. deteksi otomatis Brave/Chrome/Chromium/Edge sesuai OS
4. None -> pakai Chromium bawaan Playwright
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .settings import load_config


def _candidates() -> list[str]:
    home = Path.home()
    if sys.platform.startswith("win"):
        return [
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ]
    if sys.platform == "darwin":
        return [
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    return [
        "/usr/bin/brave-browser",
        "/usr/bin/brave",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        str(home / ".local/bin/brave"),
    ]


def detect_executable(cfg: dict | None = None) -> str | None:
    cfg = cfg or load_config()
    explicit = (cfg.get("browser") or {}).get("executable") or ""
    if explicit and Path(explicit).exists():
        return explicit
    env = os.environ.get("OMNICARO_BROWSER", "")
    if env and Path(env).exists():
        return env
    for cand in _candidates():
        if Path(cand).exists():
            return cand
    return None


DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36")

STEALTH_JS = (
    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
)


def browser_options(cfg: dict | None = None, headless: bool | None = None) -> dict:
    """Argumen launch yang dipakai SEMUA jalur browser."""
    cfg = cfg or load_config()
    cfg_headless = bool((cfg.get("browser") or {}).get("headless", True))
    exe = detect_executable(cfg)
    opts: dict = {
        "headless": cfg_headless if headless is None else headless,
        "args": [
            "--disable-quic",
            "--no-first-run",
            # UA default Playwright "HeadlessChrome" memicu challenge Cloudflare
            "--disable-blink-features=AutomationControlled",
        ],
    }
    if exe:
        opts["executable_path"] = exe
    return opts


def launch(p, cfg: dict | None = None, headless: bool | None = None):
    """Luncurkan browser non-persistent (siap untuk banyak context/cookie)."""
    return p.chromium.launch(**browser_options(cfg, headless))


def new_context(browser, state: dict | None = None,
                user_agent: str | None = None, proxy: dict | None = None):
    """Context baru dengan cookie akun (storage_state), UA, dan proxy opsional."""
    kw: dict = {
        "viewport": {"width": 1366, "height": 1000},
        "locale": "id-ID",
        "timezone_id": "Asia/Jakarta",
        "user_agent": user_agent or DEFAULT_UA,
    }
    if state:
        kw["storage_state"] = state
    if proxy and proxy.get("server"):
        item = {"server": proxy["server"]}
        if proxy.get("username"):
            item["username"] = proxy["username"]
        if proxy.get("password"):
            item["password"] = proxy["password"]
        kw["proxy"] = item
    ctx = browser.new_context(**kw)
    try:
        ctx.add_init_script(STEALTH_JS)
    except Exception:
        pass
    return ctx
