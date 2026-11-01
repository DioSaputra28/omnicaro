"""SQLite storage: akun, listing, klaim upload, event login, job."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .proxy_check import parse_proxy
from .settings import DB_PATH, ensure_dirs
from .ua_data import master_uas

_LOCK = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id          TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    nickname    TEXT DEFAULT '',
    niche       TEXT DEFAULT '',
    status      TEXT DEFAULT 'unknown',
    cookies     TEXT NOT NULL,
    note        TEXT DEFAULT '',
    last_check  TEXT DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS listings (
    id          TEXT PRIMARY KEY,
    category    TEXT NOT NULL,
    title       TEXT NOT NULL,
    price       TEXT DEFAULT '',
    condition   TEXT DEFAULT '',
    url         TEXT DEFAULT '',
    image_files TEXT DEFAULT '',
    size        TEXT DEFAULT 'M',
    scraped_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS uploads (
    listing_id  TEXT PRIMARY KEY,
    account_id  TEXT NOT NULL,
    status      TEXT NOT NULL,
    stage       TEXT DEFAULT '',
    error       TEXT DEFAULT '',
    posted_at   TEXT DEFAULT '',
    price       TEXT DEFAULT '',
    size        TEXT DEFAULT '',
    url_after   TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS login_events (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  TEXT NOT NULL,
    event       TEXT NOT NULL,
    name        TEXT DEFAULT '',
    at          TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS seen (
    listing_id  TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS image_hashes (
    digest      TEXT PRIMARY KEY,
    listing_id  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    params      TEXT DEFAULT '{}',
    status      TEXT DEFAULT 'queued',
    created_at  TEXT NOT NULL,
    started_at  TEXT DEFAULT '',
    finished_at TEXT DEFAULT '',
    log_file    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_agents (
    id          TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    ua          TEXT NOT NULL,
    enabled     INTEGER DEFAULT 1,
    created_at  TEXT NOT NULL,
    last_used_at TEXT DEFAULT '',
    use_count   INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS schedule_quotas (
    schedule_id TEXT NOT NULL,
    account_id  TEXT NOT NULL,
    quota       INTEGER NOT NULL DEFAULT 10,
    PRIMARY KEY (schedule_id, account_id)
);
CREATE TABLE IF NOT EXISTS schedule_runs (
    schedule_id TEXT NOT NULL,
    day         TEXT NOT NULL,
    slot        TEXT NOT NULL,
    job_id      TEXT DEFAULT '',
    ran_at      TEXT NOT NULL,
    PRIMARY KEY (schedule_id, day, slot)
);
CREATE TABLE IF NOT EXISTS schedules (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    times       TEXT NOT NULL DEFAULT '[]',
    days        TEXT NOT NULL DEFAULT '[]',
    category    TEXT DEFAULT '',
    fast        INTEGER DEFAULT 0,
    rotate      TEXT DEFAULT 'account',
    proxy       TEXT DEFAULT 'off',
    enabled     INTEGER DEFAULT 1,
    last_run_at TEXT DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proxies (
    id          TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    server      TEXT NOT NULL,
    username    TEXT DEFAULT '',
    password    TEXT DEFAULT '',
    enabled     INTEGER DEFAULT 1,
    status      TEXT DEFAULT 'unknown',
    latency_ms  INTEGER DEFAULT 0,
    exit_ip     TEXT DEFAULT '',
    last_error  TEXT DEFAULT '',
    checked_at  TEXT DEFAULT '',
    last_used_at TEXT DEFAULT '',
    use_count   INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL
);
"""

# UA master (200 entri) dipakai saat database belum punya UA sama sekali.
SEED_UAS = master_uas()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db() -> None:
    with _LOCK, connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        # Migrasi DB lama: tambah kolom use_count bila belum ada.
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(user_agents)")}
        if "use_count" not in cols:
            conn.execute("ALTER TABLE user_agents ADD COLUMN use_count"
                         " INTEGER DEFAULT 0")
        pcols = {r["name"] for r in conn.execute("PRAGMA table_info(proxies)")}
        if "use_count" not in pcols:
            conn.execute("ALTER TABLE proxies ADD COLUMN use_count"
                         " INTEGER DEFAULT 0")
        acols = {r["name"] for r in conn.execute("PRAGMA table_info(accounts)")}
        if "niche" not in acols:
            conn.execute("ALTER TABLE accounts ADD COLUMN niche"
                         " TEXT DEFAULT ''")
        count = conn.execute("SELECT COUNT(*) c FROM user_agents").fetchone()["c"]
        if count == 0:
            for label, ua in SEED_UAS:
                conn.execute(
                    "INSERT INTO user_agents(id,label,ua,enabled,created_at)"
                    " VALUES(?,?,?,1,?)",
                    (uuid.uuid4().hex[:10], label, ua, now()))


# ---------- akun ----------

def add_account(label: str, cookies: dict, nickname: str = "",
                status: str = "unknown", niche: str = "") -> str:
    aid = uuid.uuid4().hex[:12]
    with _LOCK, connect() as conn:
        conn.execute(
            "INSERT INTO accounts(id,label,nickname,niche,status,cookies,"
            " created_at) VALUES(?,?,?,?,?,?,?)",
            (aid, label.strip() or "akun", nickname, niche or "", status,
             json.dumps(cookies), now()))
    return aid


def list_accounts() -> list[dict]:
    with _LOCK, connect() as conn:
        rows = conn.execute(
            "SELECT id,label,nickname,niche,status,note,last_check,created_at"
            " FROM accounts ORDER BY created_at").fetchall()
    return [dict(r) for r in rows]


def set_account_niche(account_id: str, niche: str) -> None:
    with _LOCK, connect() as conn:
        conn.execute("UPDATE accounts SET niche=? WHERE id=?",
                     (niche or "", account_id))


def get_account(account_id: str) -> dict | None:
    with _LOCK, connect() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE id=?",
                           (account_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["cookies"] = json.loads(d["cookies"])
    return d


def update_account_status(account_id: str, status: str,
                          nickname: str = "") -> None:
    with _LOCK, connect() as conn:
        if nickname:
            conn.execute(
                "UPDATE accounts SET status=?,nickname=?,last_check=?"
                " WHERE id=?", (status, nickname, now(), account_id))
        else:
            conn.execute(
                "UPDATE accounts SET status=?,last_check=? WHERE id=?",
                (status, now(), account_id))


def delete_account(account_id: str) -> None:
    with _LOCK, connect() as conn:
        conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))


def record_login_event(account_id: str, logged: bool, name: str = "") -> None:
    ev = "login" if logged else "logout"
    with _LOCK, connect() as conn:
        last = conn.execute(
            "SELECT event FROM login_events WHERE account_id=?"
            " ORDER BY seq DESC LIMIT 1", (account_id,)).fetchone()
        if last and last["event"] == ev:
            return
        conn.execute(
            "INSERT INTO login_events(account_id,event,name,at)"
            " VALUES(?,?,?,?)", (account_id, ev, name, now()))


def login_stats(account_id: str) -> dict:
    with _LOCK, connect() as conn:
        evs = conn.execute(
            "SELECT event,at FROM login_events WHERE account_id=?"
            " ORDER BY seq", (account_id,)).fetchall()
        posted = conn.execute(
            "SELECT posted_at FROM uploads WHERE account_id=? AND"
            " status='posted' ORDER BY posted_at", (account_id,)).fetchall()
    times = [r["posted_at"] for r in posted if r["posted_at"]]
    sessions: list[int] = []
    start = None
    for e in evs:
        if e["event"] == "login":
            start = e["at"]
        elif e["event"] == "logout" and start:
            sessions.append(sum(1 for t in times if start <= t <= e["at"]))
            start = None
    open_posts = sum(1 for t in times if start and t >= start)
    return {
        "login_at": next((e["at"] for e in reversed(evs)
                          if e["event"] == "login"), ""),
        "logout_at": next((e["at"] for e in reversed(evs)
                           if e["event"] == "logout"), ""),
        "sessions": len(sessions),
        "per_session": sessions[-8:],
        "open": open_posts,
    }


# ---------- listing ----------

def seen_ids() -> set[str]:
    with _LOCK, connect() as conn:
        return {r["listing_id"] for r in conn.execute("SELECT listing_id FROM seen")}


def known_image(digest: str) -> str | None:
    with _LOCK, connect() as conn:
        row = conn.execute("SELECT listing_id FROM image_hashes WHERE digest=?",
                           (digest,)).fetchone()
    return row["listing_id"] if row else None


def save_listing(item: dict, digests: dict[str, str]) -> bool:
    """Simpan 1 listing + tandai seen + hash gambar (idempoten)."""
    with _LOCK, connect() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO listings(id,category,title,price,condition,"
            "url,image_files,size,scraped_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (item["id"], item["category"], item["title"], item.get("price", ""),
             item.get("condition", ""), item.get("url", ""),
             item.get("image_files", ""), item.get("size", "M"), now()))
        if cur.rowcount == 0:
            return False
        conn.execute("INSERT OR IGNORE INTO seen(listing_id) VALUES(?)",
                     (item["id"],))
        for digest in digests:
            conn.execute(
                "INSERT OR IGNORE INTO image_hashes(digest,listing_id) VALUES(?,?)",
                (digest, item["id"]))
            digests[digest] = item["id"]
    return True


def mark_image_digest(digest: str, listing_id: str) -> None:
    with _LOCK, connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO image_hashes(digest,listing_id) VALUES(?,?)",
            (digest, listing_id))


def list_listings(limit: int = 300, category: str = "") -> list[dict]:
    q = ("SELECT l.*, u.status AS upload_status, u.account_id AS upload_account"
         " FROM listings l LEFT JOIN uploads u ON u.listing_id=l.id")
    args: list = []
    if category:
        q += " WHERE l.category=?"
        args.append(category)
    q += " ORDER BY l.scraped_at DESC LIMIT ?"
    args.append(limit)
    with _LOCK, connect() as conn:
        return [dict(r) for r in conn.execute(q, args).fetchall()]


def count_listings() -> dict:
    with _LOCK, connect() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM listings").fetchone()["c"]
        posted = conn.execute(
            "SELECT COUNT(*) c FROM uploads WHERE status='posted'").fetchone()["c"]
        failed = conn.execute(
            "SELECT COUNT(*) c FROM uploads WHERE status='error'").fetchone()["c"]
        seen = conn.execute("SELECT COUNT(*) c FROM seen").fetchone()["c"]
    return {"listings": total, "posted": posted, "failed": failed,
            "seen": seen, "pending": max(0, total - posted)}


# ---------- antrean upload ----------

def uploadable(category: str, limit: int,
               exclude_accounts: set[str] | None = None) -> list[dict]:
    """Listing kategori ini yang belum pernah diposting (posted)."""
    excl = exclude_accounts or set()
    with _LOCK, connect() as conn:
        rows = conn.execute(
            "SELECT l.* FROM listings l LEFT JOIN uploads u ON u.listing_id=l.id"
            " WHERE l.category=? AND (u.status IS NULL OR u.status!='posted')"
            " ORDER BY l.scraped_at", (category,)).fetchall()
    out = [dict(r) for r in rows
           if r["id"] not in excl]
    return out[:limit]


def mark_upload(listing_id: str, account_id: str, status: str,
                stage: str = "", error: str = "", price: str = "",
                size: str = "", url_after: str = "") -> None:
    with _LOCK, connect() as conn:
        conn.execute(
            "INSERT INTO uploads(listing_id,account_id,status,stage,error,"
            "posted_at,price,size,url_after) VALUES(?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(listing_id) DO UPDATE SET account_id=excluded.account_id,"
            " status=excluded.status, stage=excluded.stage, error=excluded.error,"
            " posted_at=excluded.posted_at, price=excluded.price,"
            " size=excluded.size, url_after=excluded.url_after",
            (listing_id, account_id, status, stage, error,
             now() if status == "posted" else "", price, size, url_after))


# ---------- user agent ----------

def list_user_agents() -> list[dict]:
    with _LOCK, connect() as conn:
        rows = conn.execute(
            "SELECT id,label,ua,enabled,created_at,last_used_at,use_count"
            " FROM user_agents"
            " ORDER BY use_count DESC, created_at").fetchall()
    return [dict(r) for r in rows]


def add_user_agent(label: str, ua: str, enabled: bool = True) -> str:
    ua = (ua or "").strip()
    if not ua.lower().startswith("mozilla/"):
        raise ValueError("User agent harus diawali 'Mozilla/'")
    aid = uuid.uuid4().hex[:10]
    with _LOCK, connect() as conn:
        conn.execute(
            "INSERT INTO user_agents(id,label,ua,enabled,created_at)"
            " VALUES(?,?,?,?,?)",
            (aid, (label or "UA").strip(), ua, 1 if enabled else 0, now()))
    return aid


def set_user_agent_enabled(agent_id: str, enabled: bool) -> None:
    with _LOCK, connect() as conn:
        conn.execute("UPDATE user_agents SET enabled=? WHERE id=?",
                     (1 if enabled else 0, agent_id))


def delete_user_agent(agent_id: str) -> None:
    with _LOCK, connect() as conn:
        conn.execute("DELETE FROM user_agents WHERE id=?", (agent_id,))


def reseed_user_agents() -> int:
    """Ganti seluruh daftar UA dengan master 200 entri."""
    rows = master_uas()
    with _LOCK, connect() as conn:
        conn.execute("DELETE FROM user_agents")
        for label, ua in rows:
            conn.execute(
                "INSERT INTO user_agents(id,label,ua,enabled,created_at)"
                " VALUES(?,?,?,1,?)",
                (uuid.uuid4().hex[:10], label, ua, now()))
    return len(rows)


def next_user_agent() -> dict | None:
    """Ambil UA aktif yang paling lama tidak dipakai (rotasi LRU) + hitung pakai."""
    with _LOCK, connect() as conn:
        row = conn.execute(
            "SELECT id,label,ua,use_count FROM user_agents WHERE enabled=1"
            " ORDER BY CASE WHEN last_used_at='' THEN 0 ELSE 1 END,"
            " last_used_at LIMIT 1").fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE user_agents SET last_used_at=?, use_count=use_count+1"
            " WHERE id=?", (now(), row["id"]))
        used = row["use_count"] + 1
    return {"id": row["id"], "label": row["label"], "ua": row["ua"],
            "use_count": used}


# ---------- proxy ----------

def list_proxies() -> list[dict]:
    with _LOCK, connect() as conn:
        rows = conn.execute(
            "SELECT id,label,server,username,enabled,status,latency_ms,"
            " exit_ip,last_error,checked_at,last_used_at,use_count,created_at"
            " FROM proxies ORDER BY created_at").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["has_auth"] = bool(d.pop("username"))
        out.append(d)
    return out


def add_proxy(raw: str, label: str = "") -> str:
    p = parse_proxy(raw)
    pid = uuid.uuid4().hex[:10]
    with _LOCK, connect() as conn:
        conn.execute(
            "INSERT INTO proxies(id,label,server,username,password,enabled,"
            " created_at) VALUES(?,?,?,?,?,1,?)",
            (pid, (label or "").strip() or f"{p['host']}:{p['port']}",
             p["server"], p["username"], p["password"], now()))
    return pid


def delete_proxy(pid: str) -> None:
    with _LOCK, connect() as conn:
        conn.execute("DELETE FROM proxies WHERE id=?", (pid,))


def set_proxy_enabled(pid: str, enabled: bool) -> None:
    with _LOCK, connect() as conn:
        conn.execute("UPDATE proxies SET enabled=? WHERE id=?",
                     (1 if enabled else 0, pid))


def update_proxy_check(pid: str, ok: bool, latency_ms: int = 0,
                       exit_ip: str = "", error: str = "") -> None:
    with _LOCK, connect() as conn:
        conn.execute(
            "UPDATE proxies SET status=?, latency_ms=?, exit_ip=?,"
            " last_error=?, checked_at=? WHERE id=?",
            ("ok" if ok else "fail", max(0, int(latency_ms)),
             exit_ip or "", (error or "")[:200], now(), pid))


def get_proxy(pid: str) -> dict | None:
    with _LOCK, connect() as conn:
        row = conn.execute("SELECT * FROM proxies WHERE id=?", (pid,)).fetchone()
    return dict(row) if row else None


def next_proxy() -> dict | None:
    """Rotasi proxy: prioritaskan yang sehat, lalu paling lama tidak dipakai."""
    with _LOCK, connect() as conn:
        row = conn.execute(
            "SELECT * FROM proxies WHERE enabled=1"
            " ORDER BY CASE status WHEN 'ok' THEN 0 WHEN 'unknown' THEN 1"
            " ELSE 2 END, last_used_at LIMIT 1").fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE proxies SET last_used_at=?, use_count=use_count+1"
            " WHERE id=?", (now(), row["id"]))
        used = row["use_count"] + 1
    out = dict(row)
    out["use_count"] = used
    return out


# ---------- jadwal ----------

def _schedule_dict(conn, row) -> dict:
    d = dict(row)
    d["times"] = json.loads(d.get("times") or "[]")
    d["days"] = json.loads(d.get("days") or "[]")
    d["enabled"] = bool(d["enabled"])
    d["fast"] = bool(d["fast"])
    quotas = conn.execute(
        "SELECT account_id, quota FROM schedule_quotas"
        " WHERE schedule_id=? ORDER BY rowid", (d["id"],)).fetchall()
    d["quotas"] = [{"account_id": q["account_id"], "limit": q["quota"]}
                   for q in quotas]
    return d


def list_schedules() -> list[dict]:
    with _LOCK, connect() as conn:
        rows = conn.execute(
            "SELECT * FROM schedules ORDER BY created_at").fetchall()
        return [_schedule_dict(conn, r) for r in rows]


def get_schedule(schedule_id: str) -> dict | None:
    with _LOCK, connect() as conn:
        row = conn.execute("SELECT * FROM schedules WHERE id=?",
                           (schedule_id,)).fetchone()
        return _schedule_dict(conn, row) if row else None


def save_schedule(data: dict, schedule_id: str | None = None) -> str:
    times = json.dumps(sorted({t for t in (data.get("times") or [])}))
    days = json.dumps(sorted({int(d) for d in (data.get("days") or [])}))
    values = (
        (data.get("name") or "").strip() or "Jadwal",
        times, days, data.get("category") or "",
        1 if data.get("fast") else 0,
        data.get("rotate") or "account",
        data.get("proxy") or "off",
        1 if data.get("enabled", True) else 0,
    )
    with _LOCK, connect() as conn:
        if schedule_id:
            conn.execute(
                "UPDATE schedules SET name=?, times=?, days=?, category=?,"
                " fast=?, rotate=?, proxy=?, enabled=? WHERE id=?",
                values + (schedule_id,))
        else:
            schedule_id = uuid.uuid4().hex[:10]
            conn.execute(
                "INSERT INTO schedules(id,name,times,days,category,fast,"
                " rotate,proxy,enabled,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (schedule_id,) + values + (now(),))
        conn.execute("DELETE FROM schedule_quotas WHERE schedule_id=?",
                     (schedule_id,))
        for q in data.get("quotas") or []:
            conn.execute(
                "INSERT OR REPLACE INTO schedule_quotas"
                "(schedule_id,account_id,quota) VALUES(?,?,?)",
                (schedule_id, q["account_id"], max(0, int(q.get("limit", 0)))))
    return schedule_id


def delete_schedule(schedule_id: str) -> None:
    with _LOCK, connect() as conn:
        conn.execute("DELETE FROM schedule_quotas WHERE schedule_id=?",
                     (schedule_id,))
        conn.execute("DELETE FROM schedule_runs WHERE schedule_id=?",
                     (schedule_id,))
        conn.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))


def set_schedule_enabled(schedule_id: str, enabled: bool) -> None:
    with _LOCK, connect() as conn:
        conn.execute("UPDATE schedules SET enabled=? WHERE id=?",
                     (1 if enabled else 0, schedule_id))


def touch_schedule(schedule_id: str, when: str) -> None:
    with _LOCK, connect() as conn:
        conn.execute("UPDATE schedules SET last_run_at=? WHERE id=?",
                     (when, schedule_id))


def claim_schedule_run(schedule_id: str, day: str, slot: str) -> bool:
    """Kunci slot (jadwal, tanggal, jam); True hanya untuk klaim pertama."""
    with _LOCK, connect() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO schedule_runs(schedule_id,day,slot,ran_at)"
            " VALUES(?,?,?,?)", (schedule_id, day, slot, now()))
        return cur.rowcount > 0


def set_schedule_run_job(schedule_id: str, day: str, slot: str,
                         job_id: str) -> None:
    with _LOCK, connect() as conn:
        conn.execute(
            "UPDATE schedule_runs SET job_id=? WHERE schedule_id=?"
            " AND day=? AND slot=?", (job_id, schedule_id, day, slot))


def list_schedule_runs(limit: int = 50) -> list[dict]:
    with _LOCK, connect() as conn:
        rows = conn.execute(
            "SELECT r.*, s.name FROM schedule_runs r"
            " LEFT JOIN schedules s ON s.id = r.schedule_id"
            " ORDER BY r.ran_at DESC LIMIT ?", (int(limit),)).fetchall()
        return [dict(r) for r in rows]


# ---------- job ----------

def create_job(kind: str, params: dict) -> tuple[str, str]:
    """Buat job baru; kembalikan (job_id, path_log)."""
    from .settings import JOBS_DIR
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    jid = uuid.uuid4().hex[:10]
    log_file = JOBS_DIR / f"{jid}.log"
    with _LOCK, connect() as conn:
        conn.execute(
            "INSERT INTO jobs(id,kind,params,status,created_at,log_file)"
            " VALUES(?,?,?,?,?,?)",
            (jid, kind, json.dumps(params), "queued", now(), str(log_file)))
    return jid, str(log_file)


def update_job(job_id: str, status: str) -> None:
    field = "started_at" if status == "running" else "finished_at"
    with _LOCK, connect() as conn:
        conn.execute(f"UPDATE jobs SET status=?, {field}=? WHERE id=?",
                     (status, now(), job_id))


def get_job(job_id: str) -> dict | None:
    with _LOCK, connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?",
                           (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs(limit: int = 30) -> list[dict]:
    with _LOCK, connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
            (limit,)).fetchall()
    return [dict(r) for r in rows]


def prune_jobs(keep: int = 200) -> None:
    with _LOCK, connect() as conn:
        conn.execute(
            "DELETE FROM jobs WHERE id NOT IN (SELECT id FROM jobs"
            " ORDER BY created_at DESC LIMIT ?)", (keep,))
