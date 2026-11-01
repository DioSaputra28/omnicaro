"""Posting listing ke Carousell Indonesia memakai cookie akun (storage_state)."""
from __future__ import annotations

import random
import re
import time
from pathlib import Path

from . import db
from .authcheck import is_challenge
from .settings import DATA_DIR, load_config


# ---------- helper UI ----------

def _sleep(page, ms: int, fast: bool) -> None:
    """Jeda: <=500ms dipertahankan (napas render), >500ms dipotong 30% saat fast."""
    try:
        page.wait_for_timeout(ms if (not fast or ms <= 500)
                              else max(300, ms * 3 // 10))
    except Exception:
        pass


def _visible(loc) -> bool:
    try:
        return loc.count() > 0 and loc.first.is_visible()
    except Exception:
        return False


def _fill(page, loc, value: str) -> bool:
    try:
        if not _visible(loc):
            return False
        loc.first.click()
        loc.first.fill(value)
        return True
    except Exception:
        return False


# Carousell menolak tautan & sebutan platform e-commerce/pesan di deskripsi.
CATEGORY_OPEN_TEXTS = ("Pilih kategori", "Select a category",
                       "Tambahkan kategori")
_BANNED_WORDS = (
    "shopee", "tokopedia", "lazada", "bukalapak", "blibli", "tiktok",
    "whatsapp", "wa.me", "telegram", "instagram", "facebook", "http://",
    "https://", "www.", "link",
)
SAFE_DELIVERY = "Silakan chat untuk opsi pengiriman & detail barang"
SAFE_DESCRIPTION = "barang second\nkondisi sesuai foto & deskripsi"

# Alias dua bahasa supaya form ID maupun EN sama-sama dikenali.
CATEGORY_ALIASES = {
    "Fesyen Pria": "Men's Clothes",
    "Men's Clothes": "Fesyen Pria",
    "Fesyen Wanita": "Women's Clothes",
    "Women's Clothes": "Fesyen Wanita",
    "Atasan": "Tops",
    "Tops": "Atasan",
    "Bawahan": "Bottoms",
    "Bottoms": "Bawahan",
}


def _category_pairs(search: str, leaf: str) -> list[tuple[str, str]]:
    pairs = [(search, leaf)]
    alt = (CATEGORY_ALIASES.get(search, search),
           CATEGORY_ALIASES.get(leaf, leaf))
    if alt != (search, leaf):
        pairs.append(alt)
    return pairs


def sanitize_text(text: str) -> str:
    lines = []
    for line in (text or "").splitlines():
        low = line.lower()
        if any(word in low for word in _BANNED_WORDS):
            continue
        if line.strip():
            lines.append(line.strip())
    return "\n".join(lines).strip() or SAFE_DESCRIPTION


def sanitize_delivery(text: str) -> str:
    """Delivery boleh memuat link Shopee (tidak difilter Carousell)."""
    return (text or "").strip() or SAFE_DELIVERY


def select_category(page, search: str, leaf: str, fast: bool = False) -> bool:
    """Buka modal kategori (ID/EN), cari leaf, pilih yang induknya cocok."""
    opened = False
    for text in CATEGORY_OPEN_TEXTS:
        try:
            loc = page.get_by_text(text, exact=True)
            if _visible(loc):
                loc.first.click()
                opened = True
                break
        except Exception:
            continue
    if not opened:
        try:
            btn = page.get_by_role("button",
                                   name=re.compile(r"kategori|categor", re.I))
            if btn.count():
                btn.first.click()
                opened = True
        except Exception:
            opened = False
    if not opened:
        return False
    _sleep(page, 1500, fast)

    box = None
    for cand in ('input[placeholder*="kategori" i]',
                 'input[placeholder*="categor" i]',
                 'input[type="search"]',
                 '#main input[type="text"]'):
        loc = page.locator(cand)
        if _visible(loc):
            box = loc.first
            break
    if box is None:
        return False

    for q_search, q_leaf in _category_pairs(search, leaf):
        for query in dict.fromkeys([q_leaf, q_search]):
            if not query:
                continue
            try:
                box.click()
                _sleep(page, 300, fast)
                box.fill("")
                box.fill(query)
                _sleep(page, 2200, fast)
            except Exception:
                return False

            candidates: list[tuple] = []
            try:
                res = page.get_by_text(q_leaf, exact=False)
                total = min(res.count(), 25)
            except Exception:
                total = 0
            for i in range(total):
                try:
                    el = res.nth(i)
                    if not el.is_visible():
                        continue
                    node, row = el, ""
                    for _ in range(5):
                        row = (node.inner_text() or "").replace("\n", " | ")
                        low = row.lower()
                        if ">" in row and (" di " in low or " in " in low):
                            break
                        parent = node.locator("xpath=..")
                        if parent.count() == 0:
                            break
                        node = parent
                    low = row.lower()
                    if q_leaf.lower() not in low:
                        continue
                    candidates.append((el, low))
                except Exception:
                    continue

            if not candidates:
                continue
            if q_search:
                for el, low in candidates:
                    if q_search.lower() in low:
                        el.click()
                        _sleep(page, 1800, fast)
                        return True
            try:
                candidates[0][0].click()
                _sleep(page, 1800, fast)
                return True
            except Exception:
                return False
    return False


def fill_title(page, title: str) -> bool:
    for loc in (page.locator('#main [name="field_title"]'),
                page.locator('#main input[placeholder*="title" i]'),
                page.locator('#main input[placeholder*="listing" i]'),
                page.locator('#main input[aria-label*="title" i]')):
        if _fill(page, loc, title):
            return True
    try:
        inputs = page.locator('#main input[type="text"], #main input:not([type])')
        for i in range(min(inputs.count(), 8)):
            el = inputs.nth(i)
            ph = (el.get_attribute("placeholder") or "").lower()
            nm = (el.get_attribute("name") or "").lower()
            tp = (el.get_attribute("type") or "").lower()
            if tp in ("file", "checkbox", "radio", "search", "number"):
                continue
            if any(k in ph or k in nm for k in
                   ("price", "harga", "search", "categor", "size")):
                continue
            if el.is_visible():
                el.fill(title)
                return True
    except Exception:
        pass
    return False


def fill_price(page, price: str) -> bool:
    for loc in (page.locator('#main [name="field_price"]'),
                page.locator('#main input[placeholder*="price" i]'),
                page.locator('#main input[placeholder*="harga" i]'),
                page.locator('#main input[inputmode="numeric"]'),
                page.locator('#main input[type="number"]')):
        if _fill(page, loc, price):
            return True
    return False


def fill_description(page, text: str) -> bool:
    for loc in (page.locator('#main textarea[name="field_description"]'),
                page.locator('#main textarea[placeholder*="descri" i]'),
                page.locator('#main textarea')):
        if _fill(page, loc, text):
            return True
    return False


def click_condition(page, condition: str) -> bool:
    mapping = {
        "Well used": "Digunakan dengan baik",
        "Like new": "Seperti baru",
        "Brand new": "Barang baru",
        "Lightly used": "Tidak terlalu sering digunakan",
        "Heavily used": "Sering digunakan",
        "Digunakan dengan baik": "Well used",
        "Seperti baru": "Like new",
        "Barang baru": "Brand new",
        "Tidak terlalu sering digunakan": "Lightly used",
        "Sering digunakan": "Heavily used",
    }
    for name in dict.fromkeys([condition, mapping.get(condition, "")]):
        if not name:
            continue
        try:
            btn = page.locator("#main").get_by_role(
                "button", name=name, exact=True)
            if btn.count():
                btn.first.click()
                page.wait_for_timeout(600)
                return True
        except Exception:
            continue
    return False


def _set_checkbox(page, name: str, want: bool, fast: bool = False) -> bool:
    loc = page.locator(f"#main [name='{name}']")
    try:
        if loc.count() == 0:
            return False
        if bool(loc.first.is_checked()) == want:
            return True
    except Exception:
        pass
    try:
        box = loc.first.bounding_box()
        if box:
            page.mouse.click(box["x"] + box["width"] / 2,
                             box["y"] + box["height"] / 2)
            _sleep(page, 900, fast)
            if bool(loc.first.is_checked()) == want:
                return True
    except Exception:
        pass
    try:
        if "meetup" in name:
            labels = ("Meet-up", "COD")
        else:
            labels = ("Mailing & Delivery", "Opsi pengiriman",
                      "Delivery options", "Shipping options")
        for label in labels:
            lbl = page.locator("#main").get_by_text(label, exact=False)
            if not lbl.count():
                continue
            lbl.first.scroll_into_view_if_needed()
            _sleep(page, 400, fast)
            lbl.first.click()
            _sleep(page, 900, fast)
            if bool(loc.first.is_checked()) == want:
                return True
    except Exception:
        pass
    try:
        if want:
            loc.first.check(force=True, timeout=4000)
        else:
            loc.first.uncheck(force=True, timeout=4000)
        return bool(loc.first.is_checked()) == want
    except Exception:
        return False


def set_deal_methods(page, delivery: str, fast: bool = False) -> dict:
    meetup_off = _set_checkbox(page, "field_meetup", False, fast)
    mailing = _set_checkbox(page, "field_mailing", True, fast)
    text_ok = False
    if mailing:
        _sleep(page, 1200, fast)
        ta = page.locator("#main textarea[name='field_mailing_details']")
        try:
            if ta.count() and ta.first.is_visible():
                ta.first.click()
                ta.first.fill(delivery)
                _sleep(page, 500, fast)
                text_ok = (ta.first.input_value() or "") == delivery
        except Exception:
            text_ok = False
    return {"meetup_off": meetup_off, "mailing": mailing, "text": text_ok}


def fill_size(page, size: str, fast: bool = False) -> bool:
    size = (size or "M").upper()
    clicked = False
    for label in ("Ukuran", "Size"):
        try:
            page.locator("#main").get_by_text(label, exact=True).first.click(
                timeout=4000)
            clicked = True
            break
        except Exception:
            continue
    if not clicked:
        return False
    _sleep(page, 1500, fast)
    sbox = page.locator("#main input[placeholder*='ari' i], "
                        "#main input[placeholder*='earch' i]")
    try:
        if sbox.count() and sbox.first.is_visible():
            sbox.first.fill(size)
            _sleep(page, 1200, fast)
    except Exception:
        pass
    for sel in ("[role='listbox'] [role='option']", "[role='option']",
                "#main button", "ul li"):
        try:
            for el in page.locator(sel).all():
                t = (el.inner_text() or "").strip()
                token = t.split("/")[0].strip().upper().split()[-1:]
                if token and token[0] == size and el.is_visible():
                    el.click()
                    _sleep(page, 600, fast)
                    return True
        except Exception:
            continue
    return False


# ---------- posting ----------

def post_one(page, listing: dict, cfg: dict, rng: random.Random,
             fast: bool = False, log=None) -> tuple[str, dict]:
    up = cfg.get("upload") or {}
    target = (up.get("target") or "https://id.carousell.com").rstrip("/")
    kategori = listing.get("category", "")
    search = (up.get("size_search") or {}).get(kategori) or "Fesyen Pria"
    leaf = (up.get("size_leaf") or {}).get(kategori) or "Atasan"
    price = rng.randrange(int(up.get("price_min", 40000)),
                          int(up.get("price_max", 60000)) + 1,
                          int(up.get("price_step", 1000)))
    title = (listing.get("title") or "").strip()
    size = (listing.get("size") or "M").upper()
    description = up.get("description") or ""
    delivery = up.get("delivery") or ""
    safe_description = sanitize_text(description)
    safe_delivery = sanitize_delivery(delivery)
    if safe_description != description.strip() or safe_delivery != delivery.strip():
        if log:
            log("  teks dibersihkan: tautan/sebutan e-commerce tidak diizinkan")
    description, delivery = safe_description, safe_delivery
    photos = [str(DATA_DIR / p) for p in
              (listing.get("image_files") or "").split(";") if p]

    page.goto(target + "/sell/", wait_until="domcontentloaded", timeout=60000)
    _sleep(page, 2000, fast)
    if is_challenge(page):
        return "blocked", {"stage": "blocked",
                           "err": "Cloudflare challenge di halaman jual"}

    if not photos or not all(Path(p).exists() for p in photos):
        return "error", {"stage": "foto", "err": "file gambar tidak lengkap"}
    try:
        page.set_input_files('input[type="file"]', photos)
    except Exception as e:
        return "error", {"stage": "foto", "err": str(e)[:200]}
    _sleep(page, 2500, fast)

    if not select_category(page, search, leaf, fast):
        stage = "blocked" if is_challenge(page) else "kategori"
        return "error" if stage == "kategori" else "blocked", {
            "stage": stage,
            "err": "Cloudflare challenge" if stage == "blocked"
                   else "kategori tidak terpilih"}
    _sleep(page, 1200, fast)

    ok_title = fill_title(page, title)
    click_condition(page, up.get("condition", "Digunakan dengan baik"))
    ok_size = fill_size(page, size, fast)
    ok_desc = fill_description(page, description)

    # Form baru sudah menampilkan harga langsung; form lama perlu "List now".
    ok_price = fill_price(page, str(price))
    if not ok_price:
        for label in ("List now", "Daftarkan"):
            try:
                btn = page.locator("#main").get_by_role(
                    "button", name=label, exact=True)
                if btn.count():
                    btn.first.click(timeout=8000)
                    _sleep(page, 2500, fast)
                    break
            except Exception:
                continue
        ok_price = fill_price(page, str(price))
    if not (ok_title or ok_price or ok_desc):
        body = ""
        try:
            body = (page.inner_text("body") or "")[:400]
        except Exception:
            pass
        return "error", {"stage": "form", "err": "form detail tidak muncul: " + body}

    deal = set_deal_methods(page, delivery, fast)
    if not deal.get("mailing") or not deal.get("text"):
        return "error", {"stage": "mailing", "price": price, "size": size,
                         "err": f"mailing gagal: {deal}"}

    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    except Exception:
        pass
    _sleep(page, 1200, fast)

    sub = page.locator(
        '#main [type="submit"],'
        ' #main button:has-text("Pasang sekarang"),'
        ' #main button:has-text("List now")')
    if sub.count():
        sub.first.click()
        if fast:
            ok = False
            for _ in range(16):
                page.wait_for_timeout(500)
                ok = _posted_ok(page)
                if ok:
                    break
        else:
            page.wait_for_timeout(7000)
            ok = _posted_ok(page)
    else:
        ok = _posted_ok(page)

    if not ok:
        if is_challenge(page):
            return "blocked", {"stage": "blocked", "price": price,
                               "size": size,
                               "err": "Cloudflare challenge saat submit"}
        body = ""
        try:
            body = (page.inner_text("body") or "")[:300]
        except Exception:
            pass
        return "error", {"stage": "submit", "price": price, "size": size,
                         "err": "submit tidak pindah halaman: " + body}

    return "posted", {"price": price, "size": size,
                      "folder": Path(listing.get("image_files", "").split(";")[0]).parent.as_posix()
                      if listing.get("image_files") else "",
                      "url": page.url or ""}


def _posted_ok(page) -> bool:
    url = page.url or ""
    if "/sell" not in url or "success" in url:
        return True
    try:
        body = (page.inner_text("body") or "")[:2500].lower()
    except Exception:
        return False
    for marker in ("successfully listed", "iklan anda", "berhasil dipasang",
                   "berhasil", "listed successfully"):
        if marker in body:
            return True
    return False
