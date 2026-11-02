"""Penjadwal posting: klaim slot waktu lokal lalu submit job upload_all."""
from __future__ import annotations

import threading
import time
from datetime import datetime

from . import db

# Toleransi telat (mis. server baru hidup beberapa menit setelah jam slot).
WINDOW_SECONDS = 20 * 60


class Scheduler:
    def __init__(self, manager, interval: int = 20) -> None:
        self.manager = manager
        self.interval = interval
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._loop, name="omnicaro-scheduler", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while True:
            try:
                self.tick()
            except Exception:
                pass
            time.sleep(self.interval)

    def tick(self, now: datetime | None = None) -> list[str]:
        now = now or datetime.now()
        day = now.strftime("%Y-%m-%d")
        weekday = now.weekday()
        submitted: list[str] = []
        for sched in db.list_schedules():
            if not sched["enabled"] or not sched["times"]:
                continue
            if sched["days"] and weekday not in sched["days"]:
                continue
            quotas = {q["account_id"]: int(q["limit"])
                      for q in sched["quotas"]}
            if not any(value > 0 for value in quotas.values()):
                continue
            for slot in sched["times"]:
                try:
                    hour, minute = (int(x) for x in slot.split(":"))
                    slot_dt = now.replace(hour=hour, minute=minute,
                                          second=0, microsecond=0)
                except (ValueError, TypeError):
                    continue
                delta = (now - slot_dt).total_seconds()
                if delta < 0 or delta > WINDOW_SECONDS:
                    continue
                if not db.claim_schedule_run(sched["id"], day, slot):
                    continue
                job_id = self.manager.submit("upload_all", {
                    "quotas": quotas,
                    "category": sched["category"],
                    "fast": sched["fast"],
                    "rotate": sched["rotate"],
                    "proxy": sched["proxy"],
                })
                db.set_schedule_run_job(sched["id"], day, slot, job_id)
                db.touch_schedule(sched["id"],
                                  now.isoformat(timespec="seconds"))
                submitted.append(job_id)
        return submitted


_instance: Scheduler | None = None


def start(manager) -> Scheduler:
    global _instance
    if _instance is None:
        _instance = Scheduler(manager)
        _instance.start()
    return _instance
