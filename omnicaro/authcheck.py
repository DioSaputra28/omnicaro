"""Cek status login akun Carousell dari cookie (storage_state)."""
from __future__ import annotations

import re

from . import browser as bmod
from .settings import load_config


CHALLENGE = "challenge"
_CHALLENGE_TITLES = ("tunggu sebentar", "just a moment", "attention required",
                     "verifikasi", "verify you are human")


def is_challenge(page) -> bool:
    """True bila halaman yang tampil adalah challenge Cloudflare/Turnstile."""
    try:
        title = (page.title() or "").lower()
        if any(mark in title for mark in _CHALLENGE_TITLES):
            return True
        if page.query_selector(
                'iframe[src*="challenges.cloudflare.com"],'
                ' #challenge-form, #cf-challenge-running,'
                ' [data-testid="turnstile-widget"]'):
            return True
        body = (page.inner_text("body") or "").lower()[:2000]
        return any(mark in body for mark in (
            "verify you are human", "verifikasi anda",
            "checking your browser", "tunggu sebentar",
            "just a moment", "turnstile"))
    except Exception:
        return False


def _wait_challenge(page, rounds: int = 4, wait_ms: int = 2500) -> bool:
    """Beri kesempatan challenge lolos otomatis. True bila masih challenge."""
    for _ in range(rounds):
        page.wait_for_timeout(wait_ms)
        if not is_challenge(page):
            return False
    return True


def _account_from_html(html: str) -> str:
    """Ambil username dari aria-label tombol akun (ID: 'Akun:', EN: 'Account:')."""
    match = re.search(r'aria-label="(?:Akun|Account):\s*([^"]+)"', html or "")
    if not match:
        return ""
    return match.group(1).strip().split()[0].strip(",.!? ")


def _name_from_header(page) -> str:
    try:
        el = page.query_selector(
            '[aria-label^="Akun:"], [aria-label^="Account:"]')
        if el:
            label = el.get_attribute("aria-label") or ""
            if ":" in label:
                name = label.split(":", 1)[1].strip()
                if name:
                    return name
            text = (el.inner_text() or "").strip()
            if text:
                return text.splitlines()[0].strip()
    except Exception:
        pass
    return ""


def _parse(body: str, has_login_btn: bool) -> tuple[bool, str]:
    i = (body or "").find("Hello,")
    if i >= 0:
        name = (body[i + 6:].strip().split() or [""])[0].strip(",.!? ")
        if name:
            return True, name
    if has_login_btn:
        return False, ""
    return False, ""


def _detect(page) -> tuple[bool, str]:
    """Deteksi login dari beberapa sinyal (layout Carousell sering berubah)."""
    try:
        body = page.inner_text("body") or ""
    except Exception:
        body = ""
    try:
        has_btn = page.query_selector('a[href*="login"]') is not None
    except Exception:
        has_btn = False

    ok, name = _parse(body, has_btn)
    if ok:
        return True, name
    if has_btn:
        return False, ""

    try:
        inbox = page.query_selector('a[href^="/inbox"]') is not None
        likes = page.query_selector('a[href^="/likes"]') is not None
    except Exception:
        inbox = likes = False

    # Header akun login: ikon Inbox/Likes ada, tombol Masuk/Daftar tidak ada.
    if (inbox or likes) and "Masuk" not in body and "Daftar" not in body:
        return True, ""

    acct = _account_from_html(page.content()) or _name_from_header(page)
    if acct:
        return True, acct
    return False, ""


def _check_loaded(page, target: str) -> tuple[bool, str]:
    try:
        page.goto(target.rstrip("/") + "/",
                  wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(1500)
        if is_challenge(page):
            if _wait_challenge(page):
                return False, CHALLENGE
        for _ in range(2):
            try:
                page.wait_for_selector(
                    '#main, a[href*="login"], a[href^="/inbox"]',
                    timeout=15000)
            except Exception:
                pass
            ok, name = _detect(page)
            if ok:
                return True, name or _name_from_header(page)
            if page.query_selector('a[href*="login"]'):
                return False, ""
            try:
                page.reload(wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(1500)
            except Exception:
                break
        return False, ""
    except Exception as e:
        return False, f"cek gagal: {type(e).__name__}"


def check_page(page, cfg: dict | None = None) -> tuple[bool, str]:
    """Cek login memakai page yang SUDAH terbuka (tanpa browser baru)."""
    cfg = cfg or load_config()
    target = (cfg.get("upload") or {}).get("target", "https://id.carousell.com")
    return _check_loaded(page, target)


def check_state(state: dict | None, cfg: dict | None = None) -> tuple[bool, str]:
    """Buka Carousell dengan cookie apa pun (storage_state).

    Tidak pernah raise; error jaringan dianggap belum login.
    """
    from playwright.sync_api import sync_playwright

    cfg = cfg or load_config()
    target = (cfg.get("upload") or {}).get("target", "https://id.carousell.com")
    try:
        with sync_playwright() as p:
            br = bmod.launch(p, cfg)
            try:
                ctx = bmod.new_context(br, state)
                return _check_loaded(ctx.new_page(), target)
            finally:
                try:
                    br.close()
                except Exception:
                    pass
    except Exception as e:
        return False, f"cek gagal: {type(e).__name__}"


def check(account: dict, cfg: dict | None = None) -> tuple[bool, str]:
    """Cek login dari dict akun (key 'cookies' = storage_state)."""
    return check_state(account.get("cookies"), cfg)
