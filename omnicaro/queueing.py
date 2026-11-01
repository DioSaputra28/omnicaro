"""Pembagian antrean upload per akun tanpa overlap."""
from __future__ import annotations

from . import db


def build(account_id: str, limit: int, category: str = "") -> list[dict]:
    """Ambil listing yang belum pernah posted, urut kronologis."""
    rows = db.uploadable(category, limit) if category else _all_uploadable(limit)
    return rows[:max(0, limit)]


def _all_uploadable(limit: int) -> list[dict]:
    rows = db.list_listings(limit=5000)
    out = [r for r in rows if r.get("upload_status") != "posted"]
    out.sort(key=lambda r: r.get("scraped_at", ""))
    return out[:max(0, limit)]
