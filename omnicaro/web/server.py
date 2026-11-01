"""Web server: dashboard + API."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .. import authcheck, cookies, db, jobs, proxy_check, queueing, scheduler
from .. import uploader
from ..settings import (CLI_DEFAULT_DELIVERY, CLI_DEFAULT_DESCRIPTION,
                        load_config, save_config)

STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="omnicaro")


class AccountIn(BaseModel):
    label: str = ""
    cookies_text: str = ""
    niche: str = ""


class AccountPatch(BaseModel):
    niche: str = ""


class CookieTestIn(BaseModel):
    cookies_text: str = ""


class ScrapeIn(BaseModel):
    categories: list[str] = []
    limit: int = 20


class UploadIn(BaseModel):
    account_id: str
    category: str = ""
    limit: int = 10
    fast: bool = False
    rotate: str = "account"   # off | account | listing
    proxy: str = "off"        # off | rotate


class UserAgentIn(BaseModel):
    label: str = ""
    ua: str


class ProxyIn(BaseModel):
    raw: str = ""
    label: str = ""


class ProxyCheckIn(BaseModel):
    ids: list[str] = []


class UploadSettingsIn(BaseModel):
    description: str = ""
    delivery: str = ""
    price_min: int = 40000
    price_max: int = 60000
    price_step: int = 1000
    condition: str = "Digunakan dengan baik"


class QuotaIn(BaseModel):
    account_id: str
    limit: int = 10


class ScheduleIn(BaseModel):
    name: str = ""
    times: list[str] = []
    days: list[int] = []
    category: str = ""
    fast: bool = False
    rotate: str = "account"
    proxy: str = "off"
    enabled: bool | None = None
    quotas: list[QuotaIn] = []


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    scheduler.start(jobs.manager)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/state")
def state():
    cfg = load_config()
    accounts = db.list_accounts()
    for a in accounts:
        a["stats"] = db.login_stats(a["id"])
    return {
        "accounts": accounts,
        "counts": db.count_listings(),
        "categories": cfg.get("scrape", {}).get("categories", {}),
        "jobs": db.list_jobs(15),
        "current_job": jobs.manager.current(),
        "user_agents": db.list_user_agents(),
        "proxies": db.list_proxies(),
        "schedules": db.list_schedules(),
        "browser": {
            "headless": bool((cfg.get("browser") or {}).get("headless", True)),
        },
    }


@app.post("/api/accounts/test")
async def test_account_cookie(payload: CookieTestIn):
    try:
        state = cookies.parse_text(payload.cookies_text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    ok, who = await run_in_threadpool(authcheck.check_state, state)
    blocked = (not ok and who == authcheck.CHALLENGE)
    if ok:
        message = f"Login OK: {who or 'akun'}"
    elif blocked:
        message = "Cloudflare Turnstile terdeteksi — akun gugur"
    elif who.startswith("cek gagal"):
        message = who
    else:
        message = "Cookie terbaca, tapi sesi login tidak terdeteksi"
    return {
        "login": ok,
        "blocked": blocked,
        "name": who,
        "cookie_count": len(state["cookies"]),
        "has_session": cookies.has_session_cookie(state),
        "message": message,
    }


@app.post("/api/accounts")
async def add_account(payload: AccountIn):
    try:
        state_cookies = cookies.parse_text(payload.cookies_text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    label = (payload.label or "").strip() or "akun"
    categories = (load_config().get("scrape") or {}).get("categories") or {}
    niche = payload.niche if payload.niche in categories else ""
    aid = db.add_account(label, state_cookies, status="unknown", niche=niche)

    def _validate() -> tuple[bool, str]:
        acc = db.get_account(aid)
        return authcheck.check(acc or {})

    ok, who = await run_in_threadpool(_validate)
    blocked = (not ok and who == authcheck.CHALLENGE)
    status = "login" if ok else ("blocked" if blocked else "logout")
    db.update_account_status(aid, status, "cloudflare" if blocked else who)
    db.record_login_event(aid, ok, who)
    if ok:
        message = "Login OK: " + (who or label)
    elif blocked:
        message = "Cloudflare Turnstile terdeteksi — akun ditandai gugur"
    else:
        message = "Cookie tersimpan, tapi login belum terdeteksi"
    return {"id": aid, "login": ok, "blocked": blocked, "name": who,
            "message": message}


@app.patch("/api/accounts/{account_id}")
def patch_account(account_id: str, payload: AccountPatch):
    if not db.get_account(account_id):
        raise HTTPException(status_code=404, detail="akun tidak ditemukan")
    categories = (load_config().get("scrape") or {}).get("categories") or {}
    niche = payload.niche if payload.niche in categories else ""
    db.set_account_niche(account_id, niche)
    return {"ok": True}


@app.delete("/api/accounts/{account_id}")
def delete_account(account_id: str):
    db.delete_account(account_id)
    return {"ok": True}


@app.get("/api/listings")
def listings(limit: int = 200, category: str = ""):
    return {"items": db.list_listings(limit=limit, category=category)}


@app.get("/api/jobs")
def list_jobs():
    return {"items": db.list_jobs(20), "current": jobs.manager.current()}


@app.post("/api/jobs/scrape")
def start_scrape(payload: ScrapeIn):
    if not payload.categories:
        raise HTTPException(status_code=400, detail="pilih minimal 1 kategori")
    job_id = jobs.manager.submit("scrape", {
        "categories": payload.categories,
        "limit": max(1, payload.limit),
    })
    return {"id": job_id}


@app.post("/api/jobs/upload")
def start_upload(payload: UploadIn):
    rotate = payload.rotate if payload.rotate in ("off", "account", "listing") \
        else "account"
    proxy = payload.proxy if payload.proxy in ("off", "rotate") else "off"
    common = {
        "category": payload.category,
        "limit": max(1, payload.limit),
        "fast": bool(payload.fast),
        "rotate": rotate,
        "proxy": proxy,
    }
    if payload.account_id == "__all__":
        if not db.list_accounts():
            raise HTTPException(status_code=400, detail="belum ada akun")
        return {"id": jobs.manager.submit("upload_all", common)}
    if not db.get_account(payload.account_id):
        raise HTTPException(status_code=400, detail="akun tidak ditemukan")
    job_id = jobs.manager.submit("upload", {
        "account_id": payload.account_id, **common})
    return {"id": job_id}


@app.get("/api/user-agents")
def user_agents():
    return {"items": db.list_user_agents()}


@app.post("/api/user-agents")
def add_user_agent(payload: UserAgentIn):
    try:
        agent_id = db.add_user_agent(payload.label, payload.ua)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": agent_id}


@app.patch("/api/user-agents/{agent_id}")
def toggle_user_agent(agent_id: str, enabled: bool = True):
    db.set_user_agent_enabled(agent_id, enabled)
    return {"ok": True}


@app.delete("/api/user-agents/{agent_id}")
def remove_user_agent(agent_id: str):
    db.delete_user_agent(agent_id)
    return {"ok": True}


# ---------- pengaturan template ----------

def _settings_payload() -> dict:
    cfg = load_config()
    up = cfg.get("upload") or {}
    categories = (cfg.get("scrape") or {}).get("categories") or {}
    search = up.get("size_search") or {}
    leaf = up.get("size_leaf") or {}
    mapping = [{"category": key,
                "label": (info or {}).get("label", key),
                "search": search.get(key, ""),
                "leaf": leaf.get(key, "")}
               for key, info in categories.items()]
    return {
        "upload": up,
        "preview": {
            "description": uploader.sanitize_text(up.get("description") or ""),
            "delivery": uploader.sanitize_delivery(up.get("delivery") or ""),
        },
        "defaults": {
            "description": CLI_DEFAULT_DESCRIPTION,
            "delivery": CLI_DEFAULT_DELIVERY,
        },
        "mapping": mapping,
    }


@app.get("/api/settings")
def get_settings():
    return _settings_payload()


@app.put("/api/settings/upload")
def put_settings(payload: UploadSettingsIn):
    price_min = int(payload.price_min)
    price_max = int(payload.price_max)
    price_step = max(1, int(payload.price_step))
    if price_min < 0 or price_max < price_min:
        raise HTTPException(status_code=400,
                            detail="rentang harga tidak valid")
    cfg = load_config()
    up = cfg.setdefault("upload", {})
    up["description"] = payload.description or ""
    up["delivery"] = payload.delivery or ""
    up["price_min"] = price_min
    up["price_max"] = price_max
    up["price_step"] = price_step
    up["condition"] = (payload.condition or "Digunakan dengan baik").strip()
    save_config(cfg)
    return _settings_payload()


@app.post("/api/settings/preview")
def preview_settings(payload: UploadSettingsIn):
    return {
        "preview": {
            "description": uploader.sanitize_text(payload.description),
            "delivery": uploader.sanitize_delivery(payload.delivery),
        }
    }


# ---------- jadwal ----------

def _clean_schedule(payload: ScheduleIn, existing: dict | None = None) -> dict:
    times: list[str] = []
    for raw in payload.times[:12]:
        text = (raw or "").strip()
        try:
            hour_text, minute_text = text.split(":")
            hour, minute = int(hour_text), int(minute_text)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400,
                                detail=f"jam tidak valid: {raw}")
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise HTTPException(status_code=400,
                                detail=f"jam tidak valid: {raw}")
        times.append(f"{hour:02d}:{minute:02d}")
    times = sorted(set(times))
    if not times:
        raise HTTPException(status_code=400, detail="isi minimal satu jam")

    days = sorted({int(d) for d in payload.days if 0 <= int(d) <= 6})

    valid_accounts = {a["id"] for a in db.list_accounts()}
    quotas: list[dict] = []
    seen: set[str] = set()
    for q in payload.quotas:
        if q.account_id not in valid_accounts or q.account_id in seen:
            continue
        limit = max(0, int(q.limit))
        if limit <= 0:
            continue
        seen.add(q.account_id)
        quotas.append({"account_id": q.account_id, "limit": limit})
    if not quotas:
        raise HTTPException(status_code=400,
                            detail="isi kuota minimal satu akun")

    rotate = payload.rotate if payload.rotate in ("off", "account", "listing") \
        else "account"
    proxy = payload.proxy if payload.proxy in ("off", "rotate") else "off"
    if payload.enabled is not None:
        enabled = bool(payload.enabled)
    elif existing is not None:
        enabled = bool(existing["enabled"])
    else:
        enabled = True
    return {
        "name": payload.name,
        "times": times,
        "days": days,
        "category": payload.category,
        "fast": bool(payload.fast),
        "rotate": rotate,
        "proxy": proxy,
        "enabled": enabled,
        "quotas": quotas,
    }


@app.get("/api/schedules")
def schedules():
    return {"items": db.list_schedules()}


@app.get("/api/schedule-runs")
def schedule_runs():
    return {"items": db.list_schedule_runs(50)}


@app.post("/api/schedules")
def create_schedule(payload: ScheduleIn):
    return {"id": db.save_schedule(_clean_schedule(payload))}


@app.put("/api/schedules/{schedule_id}")
def update_schedule(schedule_id: str, payload: ScheduleIn):
    existing = db.get_schedule(schedule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="jadwal tidak ditemukan")
    return {"id": db.save_schedule(_clean_schedule(payload, existing),
                                   schedule_id)}


@app.patch("/api/schedules/{schedule_id}")
def toggle_schedule(schedule_id: str, enabled: bool = True):
    if not db.get_schedule(schedule_id):
        raise HTTPException(status_code=404, detail="jadwal tidak ditemukan")
    db.set_schedule_enabled(schedule_id, enabled)
    return {"ok": True}


@app.delete("/api/schedules/{schedule_id}")
def remove_schedule(schedule_id: str):
    db.delete_schedule(schedule_id)
    return {"ok": True}


@app.post("/api/schedules/{schedule_id}/run")
def run_schedule_now(schedule_id: str):
    sched = db.get_schedule(schedule_id)
    if not sched:
        raise HTTPException(status_code=404, detail="jadwal tidak ditemukan")
    quotas = {q["account_id"]: q["limit"] for q in sched["quotas"]}
    if not quotas:
        raise HTTPException(status_code=400, detail="kuota akun kosong")
    job_id = jobs.manager.submit("upload_all", {
        "quotas": quotas,
        "category": sched["category"],
        "fast": sched["fast"],
        "rotate": sched["rotate"],
        "proxy": sched["proxy"],
    })
    db.touch_schedule(schedule_id, db.now())
    return {"id": job_id}


# ---------- proxy ----------

@app.get("/api/proxies")
def proxies():
    return {"items": db.list_proxies()}


@app.post("/api/proxies/test")
async def test_proxies(payload: ProxyIn):
    lines = [ln.strip() for ln in (payload.raw or "").splitlines() if ln.strip()]
    if not lines:
        raise HTTPException(status_code=400, detail="proxy kosong")
    lines = lines[:20]
    results = await asyncio.gather(
        *(run_in_threadpool(proxy_check.check, ln) for ln in lines))
    out = [{"raw": ln, **res} for ln, res in zip(lines, results)]
    ok = sum(1 for r in out if r["ok"])
    return {"ok": ok, "fail": len(out) - ok, "results": out}


@app.post("/api/proxies")
def add_proxies(payload: ProxyIn):
    lines = [ln.strip() for ln in (payload.raw or "").splitlines() if ln.strip()]
    if not lines:
        raise HTTPException(status_code=400, detail="proxy kosong")
    added, errors = 0, []
    for line in lines:
        try:
            db.add_proxy(line, payload.label if len(lines) == 1 else "")
            added += 1
        except ValueError as e:
            errors.append(f"{line}: {e}")
    if not added:
        raise HTTPException(status_code=400, detail="; ".join(errors[:5]))
    return {"added": added, "errors": errors}


@app.delete("/api/proxies/{proxy_id}")
def remove_proxy(proxy_id: str):
    db.delete_proxy(proxy_id)
    return {"ok": True}


@app.patch("/api/proxies/{proxy_id}")
def toggle_proxy(proxy_id: str, enabled: bool = True):
    db.set_proxy_enabled(proxy_id, enabled)
    return {"ok": True}


def _check_one(proxy_id: str) -> dict:
    row = db.get_proxy(proxy_id)
    if not row:
        return {"id": proxy_id, "ok": False, "error": "proxy tidak ditemukan"}
    result = proxy_check.check(row)
    db.update_proxy_check(proxy_id, result["ok"], result["latency_ms"],
                          result["exit_ip"], result["error"])
    return {"id": proxy_id, **result}


@app.post("/api/proxies/{proxy_id}/check")
async def check_proxy(proxy_id: str):
    return await run_in_threadpool(_check_one, proxy_id)


@app.post("/api/proxies/check")
async def check_proxies(payload: ProxyCheckIn):
    ids = payload.ids or [p["id"] for p in db.list_proxies()]
    ids = ids[:60]
    results = await asyncio.gather(
        *(run_in_threadpool(_check_one, pid) for pid in ids))
    ok = sum(1 for r in results if r.get("ok"))
    return {"checked": len(results), "ok": ok, "fail": len(results) - ok,
            "results": results}


@app.post("/api/jobs/check-all")
def check_all():
    return {"id": jobs.manager.submit("check_all", {})}


@app.post("/api/jobs/check/{account_id}")
def check_one(account_id: str):
    if not db.get_account(account_id):
        raise HTTPException(status_code=400, detail="akun tidak ditemukan")
    return {"id": jobs.manager.submit("check_account",
                                      {"account_id": account_id})}


@app.get("/api/jobs/{job_id}/log")
def job_log(job_id: str, offset: int = 0):
    text, new_offset = jobs.tail(job_id, offset)
    job = db.get_job(job_id) or {}
    return {"text": text, "offset": new_offset, "status": job.get("status", "")}


@app.get("/api/jobs/{job_id}/stream")
async def job_stream(job_id: str):
    async def gen():
        offset = 0
        idle = 0
        while True:
            text, offset = await run_in_threadpool(jobs.tail, job_id, offset)
            if text:
                idle = 0
                yield "data: " + json.dumps({"text": text}) + "\n\n"
            job = await run_in_threadpool(db.get_job, job_id)
            status = (job or {}).get("status", "")
            if status in ("done", "error"):
                text, offset = await run_in_threadpool(jobs.tail, job_id, offset)
                if text:
                    yield "data: " + json.dumps({"text": text}) + "\n\n"
                yield "data: " + json.dumps({"status": status}) + "\n\n"
                break
            idle += 1
            if idle > 3600:
                yield "data: " + json.dumps({"status": "timeout"}) + "\n\n"
                break
            await asyncio.sleep(0.6)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
