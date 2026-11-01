"""Parser dan pengecek konektivitas proxy (HTTP/HTTPS/SOCKS)."""
from __future__ import annotations

import time
import urllib.parse

import requests

CHECK_URL = "https://api.ipify.org?format=json"
SUPPORTED = {"http", "https", "socks4", "socks5"}


def parse_proxy(raw: str) -> dict:
    """Terima 'host:port', 'user:pass@host:port', atau 'scheme://...'.

    Kembalikan dict: server, username, password, host, port, scheme.
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("proxy kosong")

    scheme = "http"
    if "://" in text:
        scheme, text = text.split("://", 1)
        scheme = scheme.lower()
    if scheme not in SUPPORTED:
        raise ValueError(f"skema '{scheme}' tidak didukung")

    text = text.strip().rstrip("/")
    if "/" in text:
        text = text.split("/", 1)[0]   # buang path, mis. host:port/

    username = password = ""
    if "@" in text:
        auth, text = text.rsplit("@", 1)
        if ":" in auth:
            username, password = auth.split(":", 1)
        else:
            username = auth
        username = urllib.parse.unquote(username)
        password = urllib.parse.unquote(password)

    text = text.strip().rstrip("/")
    if text.count(":") != 1:
        raise ValueError("format harus host:port")
    host, port_text = text.rsplit(":", 1)
    host = host.strip()
    if not host:
        raise ValueError("host kosong")
    try:
        port = int(port_text)
    except ValueError:
        raise ValueError("port tidak valid")
    if not 1 <= port <= 65535:
        raise ValueError("port di luar rentang")

    return {
        "scheme": scheme,
        "host": host,
        "port": port,
        "server": f"{scheme}://{host}:{port}",
        "username": username,
        "password": password,
    }


def _requests_proxy_url(p: dict) -> str:
    auth = ""
    if p.get("username"):
        user = urllib.parse.quote(p["username"], safe="")
        pwd = urllib.parse.quote(p.get("password", ""), safe="")
        auth = f"{user}:{pwd}@"
    return f"{p['scheme']}://{auth}{p['host']}:{p['port']}"


def check(raw_or_row: str | dict, timeout: float = 12.0) -> dict:
    """Cek proxy dengan request HTTP nyata ke api.ipify.org."""
    try:
        if isinstance(raw_or_row, str):
            p = parse_proxy(raw_or_row)
        else:
            row = dict(raw_or_row)
            p = parse_proxy(row.get("server") or "")
            if row.get("username"):
                p["username"] = row["username"]
            if row.get("password"):
                p["password"] = row["password"]
    except ValueError as e:
        return {"ok": False, "latency_ms": 0, "exit_ip": "",
                "error": str(e)}

    if p["scheme"] in ("socks4", "socks5"):
        try:
            import socks  # noqa: F401
        except ImportError:
            return {"ok": False, "latency_ms": 0, "exit_ip": "",
                    "error": "butuh PySocks untuk cek SOCKS"}

    url = _requests_proxy_url(p)
    proxies = {"http": url, "https": url}
    started = time.perf_counter()
    try:
        r = requests.get(CHECK_URL, proxies=proxies, timeout=timeout)
        latency = int((time.perf_counter() - started) * 1000)
        if r.status_code != 200:
            return {"ok": False, "latency_ms": latency, "exit_ip": "",
                    "error": f"HTTP {r.status_code}"}
        try:
            ip = r.json().get("ip", "")
        except ValueError:
            ip = r.text.strip()[:64]
        if not ip:
            return {"ok": False, "latency_ms": latency, "exit_ip": "",
                    "error": "respons tanpa IP"}
        return {"ok": True, "latency_ms": latency, "exit_ip": ip, "error": ""}
    except requests.exceptions.ProxyError as e:
        text = str(e)
        if "Connection refused" in text or "refused" in text.lower():
            reason = "koneksi ditolak"
        elif "timed out" in text.lower() or "timeout" in text.lower():
            reason = "timeout"
        elif "Tunnel connection failed" in text:
            reason = "tunnel gagal"
        elif "407" in text:
            reason = "butuh auth (407)"
        else:
            reason = "gagal lewat proxy"
        return {"ok": False, "latency_ms": 0, "exit_ip": "",
                "error": reason}
    except requests.exceptions.ConnectTimeout:
        return {"ok": False, "latency_ms": 0, "exit_ip": "",
                "error": "timeout koneksi"}
    except requests.exceptions.ReadTimeout:
        return {"ok": False, "latency_ms": 0, "exit_ip": "",
                "error": "timeout baca"}
    except requests.RequestException as e:
        return {"ok": False, "latency_ms": 0, "exit_ip": "",
                "error": str(e)[:140]}
