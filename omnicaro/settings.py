"""Path, config, dan helper umum (cross-platform)."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent      # folder omnicaro/
CONFIG_PATH = BASE_DIR / "config.json"
EXAMPLE_PATH = BASE_DIR / "config.example.json"
DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
STATE_DIR = DATA_DIR / "states"
DB_PATH = DATA_DIR / "omnicaro.db"
JOBS_DIR = DATA_DIR / "jobs"


def ensure_dirs() -> None:
    for d in (DATA_DIR, IMAGES_DIR, STATE_DIR, JOBS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists() and EXAMPLE_PATH.exists():
        shutil.copyfile(EXAMPLE_PATH, CONFIG_PATH)


# Default template dari project CLI utama (upload.py) — teks diobfuscate agar
# tidak kena filter tautan/e-commerce Carousell.
CLI_DEFAULT_DESCRIPTION = """barang second
kondisi sesuai foto & deskripsi
nego lewat 🆂hope
siapa cepat dia dapat
yang minat langsung checkout oren
tanya tanya bisa lewat 🆂hope aja
lebih resposif di sana
l!nk cek bio
detail barang + opsi pengiriman ada disitu"""

CLI_DEFAULT_DELIVERY = "check out here: https://s.shopee.co.id/BTOWco76c"


DEFAULT_CONFIG: dict = {
    "server": {"host": "127.0.0.1", "port": 8080},
    "browser": {"executable": "", "headless": True},
    "scrape": {
        "base_url": "https://www.carousell.com.my",
        "max_photos": 3,
        "delay_ms": 300,
        "categories": {},
    },
    "upload": {
        "target": "https://id.carousell.com",
        "price_min": 40000,
        "price_max": 60000,
        "price_step": 1000,
        "condition": "Digunakan dengan baik",
        "delay_min": 8,
        "delay_max": 20,
        "description": CLI_DEFAULT_DESCRIPTION,
        "delivery": CLI_DEFAULT_DELIVERY,
        "size_search": {},
        "size_leaf": {},
    },
}


def _merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> dict:
    ensure_dirs()
    raw: dict = {}
    if CONFIG_PATH.exists():
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raw = {}
    return _merge(DEFAULT_CONFIG, raw)


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")


def env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}
