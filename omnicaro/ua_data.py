"""Master list User Agent realistis (desktop), dibuat dari versi rilis nyata.

Snapshot versi stabil per Oktober 2026:
- Chrome 156 (rilis 20 Okt 2026)
- Edge 156 (156.0.4314.x)
- Firefox 159 (27 Okt 2026)
- Safari 26.6 (macOS 26 / Sequoia / Sonoma)

UA Chromium memakai format "reduced" (Chrome/156.0.0.0) seperti browser modern.
"""
from __future__ import annotations

WIN = "Windows NT 10.0; Win64; x64"
MAC = "Macintosh; Intel Mac OS X 10_15_7"
MAC_FIREFOX = "Macintosh; Intel Mac OS X 10.15"
LINUX = "X11; Linux x86_64"

CHROME_MAX = 156
EDGE_MAX = 156
FIREFOX_MAX = 159


def _chrome(os_token: str, ver: int) -> str:
    return (f"Mozilla/5.0 ({os_token}) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{ver}.0.0.0 Safari/537.36")


def _edge(os_token: str, ver: int) -> str:
    return _chrome(os_token, ver) + f" Edg/{ver}.0.0.0"


def _opera(os_token: str, chrome_ver: int, opr: int) -> str:
    return _chrome(os_token, chrome_ver) + f" OPR/{opr}.0.0.0"


def _vivaldi(os_token: str, chrome_ver: int, maj: int, minor: int) -> str:
    return _chrome(os_token, chrome_ver) + f" Vivaldi/{maj}.{minor}.3329.41"


def _firefox(os_token: str, ver: int, rv_plat: str = "") -> str:
    return (f"Mozilla/5.0 ({os_token}{rv_plat}; rv:{ver}.0) "
            f"Gecko/20100101 Firefox/{ver}.0")


def _safari(version: str) -> str:
    return (f"Mozilla/5.0 ({MAC}) AppleWebKit/605.1.15 "
            f"(KHTML, like Gecko) Version/{version} Safari/605.1.15")


def master_uas() -> list[tuple[str, str]]:
    """Kembalikan tepat 200 pasangan (label, user_agent) yang unik."""
    out: list[tuple[str, str]] = []

    # Chrome desktop: 22 (Win) + 22 (macOS) + 16 (Linux) = 60
    for ver in range(CHROME_MAX - 21, CHROME_MAX + 1):
        out.append((f"Chrome {ver} · Windows", _chrome(WIN, ver)))
    for ver in range(CHROME_MAX - 21, CHROME_MAX + 1):
        out.append((f"Chrome {ver} · macOS", _chrome(MAC, ver)))
    for ver in range(CHROME_MAX - 15, CHROME_MAX + 1):
        out.append((f"Chrome {ver} · Linux", _chrome(LINUX, ver)))

    # Edge desktop: 18 (Win) + 12 (macOS) = 30
    for ver in range(EDGE_MAX - 17, EDGE_MAX + 1):
        out.append((f"Edge {ver} · Windows", _edge(WIN, ver)))
    for ver in range(EDGE_MAX - 11, EDGE_MAX + 1):
        out.append((f"Edge {ver} · macOS", _edge(MAC, ver)))

    # Firefox: 18 (Win) + 14 (macOS) + 12 (Linux) = 44
    for ver in range(FIREFOX_MAX - 17, FIREFOX_MAX + 1):
        out.append((f"Firefox {ver} · Windows", _firefox(WIN, ver)))
    for ver in range(FIREFOX_MAX - 13, FIREFOX_MAX + 1):
        out.append((f"Firefox {ver} · macOS", _firefox(MAC_FIREFOX, ver)))
    for ver in range(FIREFOX_MAX - 11, FIREFOX_MAX + 1):
        out.append((f"Firefox {ver} · Linux", _firefox(LINUX, ver)))

    # Safari macOS: versi 18.0-18.6, 26.0-26.6, 25.x = 20
    safari_versions = [
        "18.0", "18.1", "18.2", "18.3", "18.4", "18.5", "18.6",
        "26.0", "26.1", "26.2", "26.3", "26.4", "26.5", "26.6",
        "17.6", "17.5", "17.4", "17.3", "17.2", "17.1",
    ]
    for sv in safari_versions:
        out.append((f"Safari {sv} · macOS", _safari(sv)))

    # Opera: 22 kombinasi (Win/macOS)
    for i, ver in enumerate(range(CHROME_MAX - 21, CHROME_MAX + 1)):
        opr = 135 + i
        os_token = WIN if i % 2 == 0 else MAC
        os_label = "Windows" if i % 2 == 0 else "macOS"
        out.append((f"Opera {opr} · {os_label}", _opera(os_token, ver, opr)))

    # Vivaldi: 24 kombinasi (Win/macOS), versi 8.0-8.4
    vivaldi_specs = []
    for chrome_ver in range(CHROME_MAX - 11, CHROME_MAX + 1):
        vivaldi_specs.append((chrome_ver, 8, (chrome_ver % 5)))
    for chrome_ver in range(CHROME_MAX - 11, CHROME_MAX + 1):
        vivaldi_specs.append((chrome_ver, 7, 9))
    for chrome_ver, maj, minor in vivaldi_specs:
        os_token = WIN if chrome_ver % 2 == 0 else MAC
        os_label = "Windows" if chrome_ver % 2 == 0 else "macOS"
        out.append((f"Vivaldi {maj}.{minor} · {os_label}",
                    _vivaldi(os_token, chrome_ver, maj, minor)))

    # Pastikan unik per UA string, lalu tepatkan jumlahnya.
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for label, ua in out:
        if ua in seen:
            continue
        seen.add(ua)
        unique.append((label, ua))

    assert len(unique) == 200, f"master UA harus 200, dapat {len(unique)}"
    return unique
