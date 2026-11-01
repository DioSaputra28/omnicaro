"""Scrape katalog Carousell (HTTP + foto penuh) dengan dedup di SQLite."""
from __future__ import annotations

import hashlib
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from . import db
from .settings import IMAGES_DIR, load_config

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "en-MY,en;q=0.9,id;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

CONDITIONS = {"Brand new", "Like new", "Lightly used", "Well used",
              "Heavily used", "Used"}


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:max_len].rstrip("-") or "produk"


def parse_cards(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out: dict[str, dict] = {}
    for card in soup.find_all("div", attrs={"data-testid": re.compile(r"^listing-card-\d+$")}):
        m = re.search(r"listing-card-(\d+)", card.get("data-testid", ""))
        if not m:
            continue
        pid = m.group(1)
        a = card.find("a", href=re.compile(r"^/p/"))
        if not a:
            continue
        url = base_url.rstrip("/") + a.get("href", "").split("?")[0]
        img = a.find("img")
        image_url = (img.get("src", "") if img else "").split("?")[0]
        title = (img.get("alt") or img.get("title") or "").strip() if img else ""
        if not title:
            p = card.find("p", style=re.compile(r"--max-line"))
            if p:
                title = p.get_text(strip=True)
        price = ""
        condition = ""
        for p in card.find_all("p"):
            t = p.get_text(strip=True)
            if not price and re.match(r"^(RM|S\$|PHP|Rp)\s?[\d,.]+", t):
                price = t
            if not condition and t in CONDITIONS:
                condition = t
        if not title or not image_url:
            continue
        out.setdefault(pid, {"id": pid, "title": title, "price": price,
                             "condition": condition, "url": url,
                             "image_url": image_url})
    return list(out.values())


def extract_photos(html: str, max_photos: int) -> list[str]:
    found = re.findall(
        r"https://media\.karousell\.com/media/photos/products/[^\"'\s<>]+?\.jpg",
        html)
    full = [u.split("?")[0] for u in found if "_thumbnail" not in u]
    return list(dict.fromkeys(full))[:max(1, max_photos)]


def extract_size(html: str) -> str:
    for m in re.findall(r'"size"\s*:\s*"([^"]+)"', html):
        if "/" in m:
            token = m.split("/")[0].strip().upper()
            if token:
                return token
    return ""


def size_from_title(title: str) -> str:
    m = re.search(r"(?i)(?:\bsize\b|\bsaiz\b|\bsz\b|ukuran)[\s:.\-]*([A-Za-z0-9]+)",
                  title or "")
    if m:
        return m.group(1).strip().upper()
    m = re.search(r"\b(XXXL|XXL|XXS|XL|XS|S|M|L)\b", title or "")
    return m.group(1).upper() if m else ""


def _fetch(session: requests.Session, url: str, timeout: int = 30,
           tries: int = 3) -> str | None:
    for i in range(max(1, tries)):
        try:
            r = session.get(url, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            return r.text
        except Exception:
            if i + 1 < tries:
                time.sleep(0.8 * (i + 1))
    return None


def _download(url: str, timeout: int = 30) -> bytes | None:
    for i in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            if r.content:
                return bytes(r.content)
        except Exception:
            time.sleep(0.5 * (i + 1))
    return None


def _log(log, msg: str) -> None:
    if log:
        log(msg)


def scrape_category(category: str, limit: int, log=None) -> int:
    """Scrape 1 kategori sampai `limit` item BARU. Kembalikan jumlah tersimpan."""
    cfg = load_config()
    sc = cfg.get("scrape") or {}
    cat = (sc.get("categories") or {}).get(category)
    if not cat:
        _log(log, f"kategori '{category}' tidak ada di config")
        return 0
    base_url = sc.get("base_url", "https://www.carousell.com.my")
    max_photos = int(sc.get("max_photos", 3))
    delay = max(0.0, int(sc.get("delay_ms", 300)) / 1000)

    seen = db.seen_ids()
    session = requests.Session()
    _log(log, f"{category}: ambil {cat.get('url')}")
    html = _fetch(session, cat["url"])
    if not html:
        _log(log, f"{category}: gagal ambil halaman kategori")
        return 0
    cards = parse_cards(html, base_url)
    fresh = [c for c in cards if c["id"] not in seen][:limit]
    _log(log, f"{category}: {len(cards)} kartu, {len(fresh)} baru")

    saved = 0
    for it in fresh:
        phtml = _fetch(session, it["url"])
        photos = extract_photos(phtml, max_photos) if phtml else []
        if not photos:
            photos = [it["image_url"]]
        size = ((extract_size(phtml) if phtml else "")
                or size_from_title(it["title"]) or "M").upper()

        folder_rel = Path("images") / category / f"{it['id']}-{slugify(it['title'])}"
        folder_abs = IMAGES_DIR.parent / folder_rel
        folder_abs.mkdir(parents=True, exist_ok=True)

        blobs = dict(zip(photos, ThreadPoolExecutor(max_workers=3).map(
            lambda u: _download(u), photos)))
        files: list[str] = []
        digests: dict[str, str] = {}
        n = 0
        for url in photos:
            blob = blobs.get(url)
            if not blob:
                continue
            digest = hashlib.sha256(blob).hexdigest()
            owner = db.known_image(digest)
            if owner:
                _log(log, f"  ~ foto duplikat (milik {owner}) dilewati")
                continue
            n += 1
            dest = folder_abs / f"{n}.jpg"
            dest.write_bytes(blob)
            rel = (folder_rel / f"{n}.jpg").as_posix()
            files.append(rel)
            digests[digest] = ""

        if not files:
            _log(log, f"  ! {it['id']} tanpa foto tersimpan, dilewati")
            continue

        ok = db.save_listing({
            "id": it["id"], "category": category, "title": it["title"],
            "price": it["price"], "condition": it["condition"], "url": it["url"],
            "image_files": ";".join(files), "size": size,
        }, digests)
        if ok:
            saved += 1
            _log(log, f"  + {it['id']} {it['title'][:45]} ({len(files)} foto, size {size})")
        time.sleep(delay)
    _log(log, f"{category}: selesai, {saved} item baru")
    return saved
