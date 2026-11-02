"""Runner job background + log yang bisa ditail dari web."""
from __future__ import annotations

import queue
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

from . import authcheck, db, queueing, scraper, uploader
from .settings import JOBS_DIR, load_config


def _close_quietly(obj) -> None:
    if obj is None:
        return
    try:
        obj.close()
    except Exception:
        pass


class JobManager:
    def __init__(self) -> None:
        self._q: queue.Queue[tuple[str, str, dict, Path]] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()
        self._current: str = ""

    # ---------- API ----------

    def submit(self, kind: str, params: dict) -> str:
        job_id, log_file = db.create_job(kind, params)
        self._q.put((job_id, kind, params, Path(log_file)))
        self._ensure_worker()
        return job_id

    def current(self) -> str:
        return self._current

    # ---------- internals ----------

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker and self._worker.is_alive():
                return
            self._worker = threading.Thread(target=self._loop, daemon=True,
                                            name="omnicaro-jobs")
            self._worker.start()

    def _loop(self) -> None:
        while True:
            job_id, kind, params, log_file = self._q.get()
            self._current = job_id
            db.update_job(job_id, "running")
            writer = _LogWriter(log_file)

            def log(msg: str) -> None:
                writer.write(msg)

            try:
                log(f"job {job_id} ({kind}) mulai")
                handler = {
                    "scrape": self._run_scrape,
                    "upload": self._run_upload,
                    "upload_all": self._run_upload_all,
                    "check_account": self._run_check_account,
                    "check_all": self._run_check_all,
                }.get(kind)
                if not handler:
                    raise ValueError(f"jenis job tidak dikenal: {kind}")
                result = handler(params, log)
                log(f"selesai: {result}")
                db.update_job(job_id, "done")
            except Exception as e:
                log(f"ERROR: {e}")
                log(traceback.format_exc())
                db.update_job(job_id, "error")
            finally:
                writer.close()
                self._current = ""
                self._q.task_done()

    # ---------- handlers ----------

    def _run_scrape(self, params: dict, log) -> str:
        categories = params.get("categories") or []
        limit = max(0, int(params.get("limit", 20)))
        if not categories:
            raise ValueError("pilih minimal 1 kategori")
        total = 0
        for cat in categories:
            total += scraper.scrape_category(cat, limit, log)
        return f"{total} listing baru"

    def _run_upload(self, params: dict, log) -> str:
        cfg = load_config()
        account_id = params.get("account_id", "")
        account = db.get_account(account_id)
        if not account:
            raise ValueError("akun tidak ditemukan")
        if account.get("status") == "blocked":
            log("akun ditandai GUGUR (Cloudflare), dilewati")
            return "akun gugur (Cloudflare), dilewati"
        if params.get("category") == "__account__":
            one = dict(params)
            one["category"] = account.get("niche") or ""
            log(f"kategori ikut akun: {one['category'] or 'semua kategori'}")
            params = one
        result = self._upload_account(cfg, account, params, log)
        return result["summary"]

    def _run_upload_all(self, params: dict, log) -> str:
        """Posting semua akun berurutan; satu akun gagal tidak menghentikan sisanya."""
        cfg = load_config()
        accounts = db.list_accounts()
        if not accounts:
            return "tidak ada akun"
        limit = max(0, int(params.get("limit", 10)))
        quotas = {k: int(v) for k, v in (params.get("quotas") or {}).items()}
        log(f"posting semua akun: {len(accounts)} akun,"
            f" {limit} listing/akun (default)")
        log(f"kategori: {params.get('category') or 'semua kategori'}")
        total_posted = total_failed = 0
        done = skipped = 0
        for idx, acc in enumerate(accounts, 1):
            full = db.get_account(acc["id"])
            if not full:
                continue
            if full.get("status") == "blocked":
                log(f"akun {full['label']}: GUGUR (Cloudflare), dilewati")
                skipped += 1
                continue
            quota = quotas.get(full["id"], limit) if quotas else limit
            if quota <= 0:
                log(f"=== akun [{idx}/{len(accounts)}] {full['label']}"
                    f" — kuota 0, dilewati ===")
                skipped += 1
                continue
            log(f"=== akun [{idx}/{len(accounts)}] {full['label']}"
                f" ({quota} posting) ===")
            one = dict(params)
            one["limit"] = quota
            if params.get("category") == "__account__":
                one["category"] = full.get("niche") or ""
                log(f"kategori ikut akun: {one['category'] or 'semua kategori'}")
            try:
                result = self._upload_account(cfg, full, one, log)
            except Exception as e:
                log(f"akun {full['label']} error: {str(e)[:200]}")
                skipped += 1
                continue
            if result["skipped"]:
                log(f"akun {full['label']} dilewati: {result['skipped']}")
                skipped += 1
                continue
            done += 1
            total_posted += result["posted"]
            total_failed += result["failed"]
            log(f"selesai {full['label']}: {result['posted']} posted,"
                f" {result['failed']} gagal")
        summary = (f"total posted {total_posted}, gagal {total_failed},"
                   f" akun selesai {done}, dilewati {skipped}")
        log(summary)
        return summary

    def _upload_account(self, cfg: dict, account: dict, params: dict,
                        log) -> dict:
        """Satu akun: bangun antrean, cek login, lalu posting berurutan."""
        account_id = account["id"]
        limit = max(0, int(params.get("limit", 10)))
        category = params.get("category", "")
        fast = bool(params.get("fast", False))
        rotate = params.get("rotate", "account")   # off | account | listing
        proxy_mode = params.get("proxy", "off")    # off | rotate
        items = queueing.build(account_id, limit, category)
        if not items:
            return {"posted": 0, "failed": 0, "skipped": "tidak ada listing",
                    "summary": "tidak ada listing untuk diposting"}
        up = cfg.get("upload") or {}
        delay_min = 1.0 if fast else float(up.get("delay_min", 8))
        delay_max = 1.0 if fast else float(up.get("delay_max", 20))

        from playwright.sync_api import sync_playwright
        from . import browser as bmod

        def open_ctx(br):
            """Context baru + UA/proxy hasil rotasi (None bila dimatikan)."""
            row = db.next_user_agent() if rotate != "off" else None
            ua = row["ua"] if row else None
            proxy = db.next_proxy() if proxy_mode != "off" else None
            ctx = bmod.new_context(br, account.get("cookies"), ua, proxy)
            return ctx, row, proxy

        log(f"{account['label']}: {len(items)} listing antre")
        log(f"rotasi user agent: {rotate} | proxy: {proxy_mode}")
        posted = failed = 0
        with sync_playwright() as p:
            br = bmod.launch(p, cfg)
            ctx = None
            try:
                ctx, ua_row, proxy_row = open_ctx(br)
                if ua_row:
                    log(f"UA aktif: {ua_row['label']} "
                        f"(dipakai {ua_row['use_count']}x)")
                if proxy_row:
                    log(f"proxy aktif: {proxy_row['label']}"
                        f" ({proxy_row['server']},"
                        f" dipakai {proxy_row['use_count']}x)")
                elif proxy_mode != "off":
                    log("tidak ada proxy aktif, lanjut tanpa proxy")
                page = ctx.new_page()
                # validasi login memakai page yang sama (tanpa browser kedua)
                ok, who = authcheck.check_page(page, cfg)
                if not ok:
                    if who == authcheck.CHALLENGE:
                        db.update_account_status(account_id, "blocked")
                        db.record_login_event(account_id, False, "cloudflare")
                        log("akun GUGUR: Cloudflare Turnstile, dilewati")
                        return {"posted": 0, "failed": 0,
                                "skipped": "cloudflare",
                                "summary": "akun gugur (Cloudflare)"}
                    db.update_account_status(account_id, "logout")
                    db.record_login_event(account_id, False)
                    log("akun BELUM login, dilewati")
                    return {"posted": 0, "failed": 0, "skipped": "belum login",
                            "summary": "akun belum login"}
                db.update_account_status(account_id, "login", who)
                db.record_login_event(account_id, True, who)
                log(f"login OK: {who or account['label']}")

                import random
                rng = random.Random(f"{account_id}-{time.time()}")
                blocked = False
                logged_out = False
                for idx, item in enumerate(items):
                    if rotate == "listing" and idx > 0:
                        _close_quietly(ctx)
                        ctx, ua_row, proxy_row = open_ctx(br)
                        page = ctx.new_page()
                        log(f"  UA ganti: "
                            f"{ua_row['label'] if ua_row else 'default'}"
                            + (f" (dipakai {ua_row['use_count']}x)"
                               if ua_row else ""))
                        if proxy_row:
                            log(f"  proxy ganti: {proxy_row['label']}"
                                f" ({proxy_row['server']},"
                                f" dipakai {proxy_row['use_count']}x)")
                    log(f"[{idx+1}/{len(items)}] {item['id']} {item['title'][:50]}")
                    try:
                        status, info = uploader.post_one(page, item, cfg, rng,
                                                         fast=fast, log=log)
                    except Exception as e:
                        status, info = "error", {"stage": "crash", "err": str(e)[:200]}
                    db.mark_upload(item["id"], account_id, status,
                                   stage=info.get("stage", ""),
                                   error=info.get("err", ""),
                                   price=str(info.get("price", "")),
                                   size=str(info.get("size", "")),
                                   url_after=info.get("url", ""))
                    if status == "logout":
                        logged_out = True
                        db.update_account_status(account_id, "logout")
                        db.record_login_event(account_id, False)
                        log("  akun LOGOUT di tengah proses —"
                            " sisa listing dilewati")
                        break
                    if status == "blocked":
                        blocked = True
                        db.update_account_status(account_id, "blocked")
                        db.record_login_event(account_id, False, "cloudflare")
                        log("  akun GUGUR: Cloudflare Turnstile —"
                            " sisa listing dilewati")
                        break
                    if status == "posted":
                        posted += 1
                        log(f"  posted (Rp{info.get('price')})")
                    else:
                        failed += 1
                        log(f"  GAGAL [{info.get('stage','?')}] {info.get('err','')[:120]}")
                    if idx + 1 < len(items):
                        time.sleep(rng.uniform(delay_min, delay_max))
            finally:
                _close_quietly(ctx)
                try:
                    br.close()
                except Exception:
                    pass
        skipped_reason = "cloudflare" if blocked else (
            "logout" if logged_out else "")
        summary = ("akun gugur (Cloudflare)" if blocked else
                   "akun logout di tengah proses" if logged_out else
                   f"posted {posted}, gagal {failed}")
        return {"posted": posted, "failed": failed,
                "skipped": skipped_reason, "summary": summary}

    def _run_check_account(self, params: dict, log) -> str:
        account = db.get_account(params.get("account_id", ""))
        if not account:
            raise ValueError("akun tidak ditemukan")
        ok, who = authcheck.check(account)
        if ok:
            status = "login"
        elif who == authcheck.CHALLENGE:
            status = "blocked"
        else:
            status = "logout"
        db.update_account_status(account["id"], status,
                                 "cloudflare" if status == "blocked" else who)
        db.record_login_event(account["id"], ok, who)
        if status == "blocked":
            log(f"{account['label']}: GUGUR (Cloudflare Turnstile)")
        else:
            log(f"{account['label']}: {'LOGIN' if ok else 'LOGOUT'} {who}")
        return status

    def _run_check_all(self, params: dict, log) -> str:
        accounts = db.list_accounts()
        for acc in accounts:
            full = db.get_account(acc["id"])
            if not full:
                continue
            ok, who = authcheck.check(full)
            if ok:
                status = "login"
            elif who == authcheck.CHALLENGE:
                status = "blocked"
            else:
                status = "logout"
            db.update_account_status(acc["id"], status,
                                     "cloudflare" if status == "blocked" else who)
            db.record_login_event(acc["id"], ok, who)
            if status == "blocked":
                log(f"{acc['label']}: GUGUR (Cloudflare Turnstile)")
            else:
                log(f"{acc['label']}: {'LOGIN' if ok else 'LOGOUT'} {who}")
        return f"{len(accounts)} akun dicek"


class _LogWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._fh = open(path, "a", encoding="utf-8", buffering=1)

    def write(self, msg: str) -> None:
        line = f"{datetime.now().strftime('%H:%M:%S')}  {msg}"
        with self._lock:
            self._fh.write(line + "\n")
            self._fh.flush()

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass


manager = JobManager()


def tail(job_id: str, offset: int = 0) -> tuple[str, int]:
    job = db.get_job(job_id)
    if not job or not job.get("log_file"):
        return "", offset
    p = Path(job["log_file"])
    if not p.exists():
        return "", offset
    data = p.read_text(encoding="utf-8", errors="replace")
    chunk = data[offset:]
    return chunk, len(data)
