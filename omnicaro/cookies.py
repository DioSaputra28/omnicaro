"""Normalisasi cookie akun -> objek storage_state Playwright.

Mendukung format yang biasa diekspor extension Chrome:
- Cookie-Editor / EditThisCookie JSON (expirationDate, hostOnly, session,
  sameSite: no_restriction/lax/strict/unspecified)
- Netscape cookies.txt (export .txt Cookie-Editor)
- Header string "name=value; name2=value2" (copy dari DevTools)
- storage_state Playwright {"cookies": [...], "origins": [...]}
"""
from __future__ import annotations

import json
from typing import Any

CARO_DOMAINS = ("carousell.com", "carousell.com.my", "carousell.sg",
                "carousell.hk", "carousell.ph", "carousell.tw")

DEFAULT_DOMAIN = ".carousell.com"

_SAME_SITE = {
    "no_restriction": "None",
    "none": "None",
    "lax": "Lax",
    "strict": "Strict",
    "unspecified": "Lax",
    "": "Lax",
}


def _valid_domain(domain: str) -> bool:
    d = (domain or "").lstrip(".").lower()
    return any(d == c or d.endswith("." + c) for c in CARO_DOMAINS)


def _expires(c: dict) -> float:
    """Chrome extension pakai 'expirationDate'; Playwright pakai 'expires'.

    Nilai <= 0 (termasuk session cookie ala Get-cookies.txt LOCALLY) -> -1.
    """
    if c.get("session"):
        return -1
    for key in ("expires", "expirationDate", "expiry"):
        value = c.get(key)
        if value in (None, ""):
            continue
        try:
            stamp = float(value)
        except (TypeError, ValueError):
            continue
        return stamp if stamp > 0 else -1
    return -1


def _same_site(value: Any) -> str:
    key = str(value or "").strip().lower()
    return _SAME_SITE.get(key, "Lax")


def _ok_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def normalize(raw: Any) -> dict:
    """Terima JSON cookie dari berbagai sumber, hasilkan storage_state."""
    origins: list = []
    cookies_in = raw
    if isinstance(raw, dict) and "cookies" in raw:
        cookies_in = raw.get("cookies") or []
        origins = raw.get("origins") or []
    elif isinstance(raw, dict):
        cookies_in = [{"name": k, "value": v} for k, v in raw.items()]

    if not isinstance(cookies_in, list):
        raise ValueError("format cookie tidak dikenali")

    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for c in cookies_in:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").strip()
        value = _ok_value(c.get("value"))
        if not name or value is None:
            continue
        domain = str(c.get("domain") or DEFAULT_DOMAIN)
        path = str(c.get("path") or "/")
        if not _valid_domain(domain):
            continue
        key = (name, domain, path)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "name": name,
            "value": value,
            "domain": domain,
            "path": path,
            "expires": _expires(c),
            "httpOnly": bool(c.get("httpOnly", False)),
            "secure": bool(c.get("secure", True)),
            "sameSite": _same_site(c.get("sameSite")),
        })

    if not out:
        raise ValueError("tidak ada cookie carousell.com yang valid")

    return {"cookies": out, "origins": origins}


def parse_netscape(text: str) -> list[dict]:
    """Parse cookies.txt (format Netscape, 7 kolom dipisah TAB)."""
    items: list[dict] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r\n")
        http_only = False
        if line.startswith("#HttpOnly_"):
            http_only = True
            line = line[len("#HttpOnly_"):]
        elif line.startswith("#") or not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _flag, path, secure, expires, name, value = parts[:7]
        name = name.strip()
        if not name:
            continue
        try:
            exp = float(expires)
        except ValueError:
            exp = -1
        if exp <= 0:
            exp = -1   # cookie sesi (Get-cookies.txt LOCALLY menulis "0")
        items.append({
            "name": name,
            "value": value,
            "domain": domain,
            "path": path or "/",
            "expires": exp,
            "httpOnly": http_only,
            "secure": str(secure).strip().upper() == "TRUE",
        })
    return items


def parse_header(text: str) -> list[dict]:
    """Parse header string 'name=value; name2=value2'."""
    text = text.strip()
    if text.lower().startswith("cookie:"):
        text = text.split(":", 1)[1]
    items: list[dict] = []
    for chunk in text.replace("\n", " ").split(";"):
        if "=" not in chunk:
            continue
        name, value = chunk.split("=", 1)
        name = name.strip()
        if not name:
            continue
        items.append({"name": name, "value": value.strip(),
                      "domain": DEFAULT_DOMAIN, "path": "/"})
    return items


def has_session_cookie(state: dict) -> bool:
    names = {c.get("name", "").lower() for c in state.get("cookies", [])}
    return bool(names & {"_session", "session", "sid", "auth_token",
                         "access_token", "carousell_session", "jwt"})


def parse_text(text: str) -> dict:
    text = (text or "").strip().lstrip("\ufeff")
    if not text:
        raise ValueError("cookie kosong")

    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        raw = None

    if raw is not None:
        return normalize(raw)

    if "\t" in text:
        return normalize(parse_netscape(text))

    if "=" in text:
        return normalize(parse_header(text))

    raise ValueError(
        "format tidak dikenali. Dukung: JSON Cookie-Editor/EditThisCookie, "
        "cookies.txt Netscape, atau header 'name=value; ...'")
