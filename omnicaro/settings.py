"""Path, config dua arah (MY→ID / ID→MY), dan helper umum (cross-platform)."""
from __future__ import annotations

import copy
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

MARKET_BASE = {
    "id": "https://id.carousell.com",
    "my": "https://www.carousell.com.my",
}
MARKET_LABEL = {"id": "Indonesia", "my": "Malaysia"}
MODE_TARGET = {"my_to_id": "id", "id_to_my": "my"}
TARGET_MODE = {value: key for key, value in MODE_TARGET.items()}
MODE_LABELS = {
    "my_to_id": "Malaysia → Indonesia",
    "id_to_my": "Indonesia → Malaysia",
}


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

MY_DEFAULT_DESCRIPTION = """barang second
keadaan seperti dalam gambar & deskripsi
boleh nego melalui 🆂hope
siapa cepat dia dapat
yang berminat terus checkout oren
boleh tanya-tanya melalui 🆂hope
lebih responsif di sana
l!nk di bio
detail barang + pilihan penghantaran ada di situ"""

MY_CATEGORIES = {
    "atasan_cowo": {
        "label": "Atasan Cowo",
        "url": "https://www.carousell.com.my/categories/"
               "men-s-fashion-3/tops-sets-1848/",
    },
    "bawahan_cowo": {
        "label": "Bawahan Cowo",
        "url": "https://www.carousell.com.my/categories/"
               "men-s-fashion-3/bottoms-1849/",
    },
    "atasan_cewe": {
        "label": "Atasan Cewe",
        "url": "https://www.carousell.com.my/categories/"
               "women-s-fashion-4/tops-1261/",
    },
    "bawahan_cewe": {
        "label": "Bawahan Cewe",
        "url": "https://www.carousell.com.my/categories/"
               "women-s-fashion-4/bottoms-1262/",
    },
}

ID_CATEGORIES = {
    "atasan_cowo": {
        "label": "Atasan Cowo",
        "url": "https://id.carousell.com/categories/"
               "mens-fashion-3/mens-clothes-363/tops-1848/",
    },
    "bawahan_cowo": {
        "label": "Bawahan Cowo",
        "url": "https://id.carousell.com/categories/"
               "mens-fashion-3/mens-clothes-363/bottoms-1849/",
    },
    "atasan_cewe": {
        "label": "Atasan Cewe",
        "url": "https://id.carousell.com/categories/"
               "womens-fashion-4/womens-clothes-346/tops-1278/",
    },
    "bawahan_cewe": {
        "label": "Bawahan Cewe",
        "url": "https://id.carousell.com/categories/"
               "womens-fashion-4/womens-clothes-346/bottoms-1279/",
    },
}

ID_UPLOAD_SEARCH = {
    "atasan_cowo": "Fesyen Pria",
    "bawahan_cowo": "Fesyen Pria",
    "atasan_cewe": "Fesyen Wanita",
    "bawahan_cewe": "Fesyen Wanita",
}
ID_UPLOAD_LEAF = {
    "atasan_cowo": "Atasan",
    "bawahan_cowo": "Bawahan",
    "atasan_cewe": "Atasan",
    "bawahan_cewe": "Bawahan",
}
MY_UPLOAD_SEARCH = {
    "atasan_cowo": "Men's Clothes",
    "bawahan_cowo": "Men's Clothes",
    "atasan_cewe": "Women's Clothes",
    "bawahan_cewe": "Women's Clothes",
}
MY_UPLOAD_LEAF = {
    "atasan_cowo": "Tops",
    "bawahan_cowo": "Bottoms",
    "atasan_cewe": "Tops",
    "bawahan_cewe": "Bottoms",
}
CONDITION_MAP = {
    "Well used": "Digunakan dengan baik",
    "Like new": "Seperti baru",
    "Brand new": "Barang baru",
    "Lightly used": "Tidak terlalu sering digunakan",
    "Heavily used": "Sering digunakan",
}

DEFAULT_MODES: dict = {
    "my_to_id": {
        "label": MODE_LABELS["my_to_id"],
        "scrape": {
            "base_url": MARKET_BASE["my"],
            "max_photos": 3,
            "delay_ms": 300,
            "categories": MY_CATEGORIES,
        },
        "upload": {
            "target": MARKET_BASE["id"],
            "price_min": 40000,
            "price_max": 60000,
            "price_step": 1000,
            "condition": "Digunakan dengan baik",
            "delay_min": 8,
            "delay_max": 20,
            "description": CLI_DEFAULT_DESCRIPTION,
            "delivery": CLI_DEFAULT_DELIVERY,
            "size_search": ID_UPLOAD_SEARCH,
            "size_leaf": ID_UPLOAD_LEAF,
            "condition_map": CONDITION_MAP,
        },
    },
    "id_to_my": {
        "label": MODE_LABELS["id_to_my"],
        "scrape": {
            "base_url": MARKET_BASE["id"],
            "max_photos": 3,
            "delay_ms": 300,
            "categories": ID_CATEGORIES,
        },
        "upload": {
            "target": MARKET_BASE["my"],
            "price_min": 10,
            "price_max": 30,
            "price_step": 1,
            "condition": "Well used",
            "delay_min": 8,
            "delay_max": 20,
            "description": MY_DEFAULT_DESCRIPTION,
            "delivery": CLI_DEFAULT_DELIVERY,
            "size_search": MY_UPLOAD_SEARCH,
            "size_leaf": MY_UPLOAD_LEAF,
            "condition_map": CONDITION_MAP,
        },
    },
}

DEFAULT_CONFIG: dict = {
    "server": {"host": "127.0.0.1", "port": 8080},
    "browser": {"executable": "", "headless": True},
    "mode": "my_to_id",
    "modes": DEFAULT_MODES,
}


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _read_raw() -> dict:
    ensure_dirs()
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _normalize(raw: dict) -> dict:
    """Gabungkan config lama (scrape/upload top-level) ke struktur modes."""
    base = copy.deepcopy(DEFAULT_CONFIG)
    raw = raw or {}
    modes = base["modes"]
    if "modes" not in raw:
        legacy_scrape = raw.get("scrape")
        legacy_upload = raw.get("upload")
        if isinstance(legacy_scrape, dict):
            modes["my_to_id"]["scrape"] = _merge(
                modes["my_to_id"]["scrape"], legacy_scrape)
        if isinstance(legacy_upload, dict):
            modes["my_to_id"]["upload"] = _merge(
                modes["my_to_id"]["upload"], legacy_upload)
    else:
        for key, block in (raw.get("modes") or {}).items():
            if isinstance(block, dict):
                modes[key] = _merge(modes.get(key, {}), block)
    out = _merge({k: v for k, v in base.items()
                  if k not in ("modes", "scrape", "upload")},
                 {k: v for k, v in raw.items()
                  if k not in ("modes", "scrape", "upload")})
    out["modes"] = modes
    out["mode"] = (raw.get("mode") if raw.get("mode") in modes
                   else "my_to_id")
    return out


def load_config(mode: str | None = None) -> dict:
    """Config aktif. `mode` memaksa arah tertentu tanpa mengubah config file."""
    data = _normalize(_read_raw())
    chosen = mode if mode in data["modes"] else data["mode"]
    if chosen not in data["modes"]:
        chosen = "my_to_id"
    active = data["modes"][chosen]
    out = dict(data)
    out["mode"] = chosen
    out["scrape"] = copy.deepcopy(active.get("scrape") or {})
    out["upload"] = copy.deepcopy(active.get("upload") or {})
    return out


def save_config(cfg: dict) -> None:
    """Simpan config normalized; scrape/upload top-level diturunkan dari modes."""
    payload = {k: v for k, v in (cfg or {}).items()
               if k not in ("scrape", "upload")}
    payload["modes"] = (cfg or {}).get("modes") or DEFAULT_MODES
    payload["mode"] = (cfg or {}).get("mode") or "my_to_id"
    CONFIG_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")


def mode_target(mode: str) -> str:
    return MODE_TARGET.get(mode, "id")


def env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}
