"""Entry point omnicaro (web dashboard)."""
from __future__ import annotations

import argparse
import logging

import uvicorn

from omnicaro.settings import BASE_DIR, DATA_DIR, ensure_dirs, load_config


def _setup_logging() -> None:
    """Log ke file, bukan stdout.

    Kalau stdout dialihkan ke pipe yang tidak dibaca (mis. proses background),
    penulisan log bisa memblokir event loop dan server tampak hang. File
    handler menghilangkan ketergantungan itu.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log_path = DATA_DIR / "server.log"
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def main() -> None:
    ap = argparse.ArgumentParser(description="omnicaro web dashboard")
    ap.add_argument("--host", default="")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--access-log", action="store_true",
                    help="tampilkan log akses HTTP di file log")
    args = ap.parse_args()

    ensure_dirs()
    _setup_logging()
    cfg = load_config()
    host = args.host or cfg["server"]["host"]
    port = args.port or int(cfg["server"]["port"])
    logging.getLogger("omnicaro").info("start http://%s:%s config=%s",
                                       host, port, BASE_DIR / "config.json")
    uvicorn.run("omnicaro.web.server:app", host=host, port=port,
                log_config=None, access_log=args.access_log,
                log_level="info")


if __name__ == "__main__":
    main()
