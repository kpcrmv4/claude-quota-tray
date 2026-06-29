"""
Snapshot history persisted to a small SQLite database.

Used for:
  - the 'Show history' chart window
  - burn-rate / ETA calculation
"""

from __future__ import annotations

import csv
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

from settings import SETTINGS_DIR


DB_PATH = SETTINGS_DIR / "history.db"

_lock = threading.RLock()
_conn: Optional[sqlite3.Connection] = None


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(
            str(DB_PATH), check_same_thread=False, timeout=10.0
        )
        # WAL keeps the chart window's reads from blocking the poller's writes;
        # busy_timeout lets a brief lock resolve itself instead of erroring.
        try:
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA busy_timeout=5000")
        except sqlite3.Error:
            pass
        _conn.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                ts REAL NOT NULL,
                account_id TEXT NOT NULL,
                session_pct INTEGER,
                weekly_pct INTEGER,
                session_reset INTEGER,
                weekly_reset INTEGER
            )
            """
        )
        # Additive migration for the separate weekly Opus limit. Old DBs gain
        # the column; rows written before this stay NULL. Ignored if present.
        try:
            _conn.execute("ALTER TABLE snapshots ADD COLUMN opus_pct INTEGER")
        except sqlite3.OperationalError:
            pass
        _conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(ts)"
        )
        _conn.commit()
    return _conn


def record(account_id: str, snapshot) -> None:
    """Persist a UsageSnapshot. Errors are swallowed (history is best-effort)."""
    if not getattr(snapshot, "ok", False):
        return
    if (
        snapshot.session_pct is None
        and snapshot.weekly_pct is None
        and getattr(snapshot, "opus_pct", None) is None
    ):
        return
    try:
        with _lock:
            conn = _connect()
            conn.execute(
                "INSERT INTO snapshots "
                "(ts, account_id, session_pct, weekly_pct, "
                " session_reset, weekly_reset, opus_pct) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    snapshot.fetched_at or time.time(),
                    account_id,
                    snapshot.session_pct,
                    snapshot.weekly_pct,
                    snapshot.session_reset_seconds,
                    snapshot.weekly_reset_seconds,
                    getattr(snapshot, "opus_pct", None),
                ),
            )
            conn.commit()
    except sqlite3.Error:
        pass


def recent(hours: float = 24, account_id: Optional[str] = None) -> list[tuple]:
    """Return rows from the last N hours, ordered by timestamp."""
    cutoff = time.time() - hours * 3600
    try:
        with _lock:
            conn = _connect()
            if account_id:
                cur = conn.execute(
                    "SELECT ts, session_pct, weekly_pct FROM snapshots "
                    "WHERE ts >= ? AND account_id = ? ORDER BY ts",
                    (cutoff, account_id),
                )
            else:
                cur = conn.execute(
                    "SELECT ts, session_pct, weekly_pct FROM snapshots "
                    "WHERE ts >= ? ORDER BY ts",
                    (cutoff,),
                )
            return cur.fetchall()
    except sqlite3.Error:
        return []


# Minimum growth (pct/hour) before we trust an ETA. Below this the value is
# essentially flat and any projected "time to full" would be meaningless.
_MIN_RATE_FOR_ETA = 0.5
# Never project an ETA further out than this — beyond it the number is noise,
# and the quota window will have reset long before then anyway.
_MAX_ETA_SECONDS = 14 * 86400


def burn_rate(window_minutes: float = 60, account_id: Optional[str] = None) -> dict:
    """
    Compute usage growth rate (% per hour) over the recent window for both
    session and weekly limits. Returns {session: {rate, eta_seconds}, weekly: ...}.

    Rate is None unless we have at least two points that are actually growing.
    A quota reset (the percentage dropping) is detected and only the samples
    *after* the most recent reset are used, so the rate isn't dragged negative
    or the ETA hallucinated when a window rolls over mid-sample.
    """
    rows = recent(window_minutes / 60.0, account_id)
    if len(rows) < 2:
        return {"session": _empty_rate(), "weekly": _empty_rate()}

    def _rate_for(idx_pct: int) -> dict:
        # Non-null (ts, pct) points in chronological order.
        points = [(r[0], r[idx_pct]) for r in rows if r[idx_pct] is not None]
        if len(points) < 2:
            return _empty_rate()

        # Drop everything up to and including the last reset (a drop in pct):
        # only the current monotonic-ish run reflects the active window.
        start = 0
        for i in range(1, len(points)):
            if points[i][1] < points[i - 1][1]:
                start = i
        segment = points[start:]
        if len(segment) < 2:
            return _empty_rate()

        first_ts, first_pct = segment[0]
        last_ts, current_pct = segment[-1]
        dt_hours = (last_ts - first_ts) / 3600.0
        if dt_hours <= 0:
            return _empty_rate()

        rate = (current_pct - first_pct) / dt_hours  # pct/hour
        if rate <= 0:
            # Flat or recovering — report no growth, no ETA.
            return {"rate": max(0.0, rate), "eta_seconds": None}

        eta = None
        if rate >= _MIN_RATE_FOR_ETA and current_pct < 100:
            remaining = 100 - current_pct
            projected = int((remaining / rate) * 3600)
            if projected <= _MAX_ETA_SECONDS:
                eta = projected
        return {"rate": rate, "eta_seconds": eta}

    return {
        "session": _rate_for(1),
        "weekly": _rate_for(2),
    }


def _empty_rate() -> dict:
    return {"rate": None, "eta_seconds": None}


def export_csv(path: str | Path, hours: float = 24,
               account_id: Optional[str] = None) -> int:
    """Write recent snapshots to CSV. Returns row count."""
    rows = recent(hours, account_id)
    p = Path(path)
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp_iso", "unix_ts", "session_pct", "weekly_pct"])
        for ts, session_pct, weekly_pct in rows:
            from datetime import datetime
            iso = datetime.fromtimestamp(ts).isoformat(sep=" ", timespec="seconds")
            w.writerow([iso, ts, session_pct, weekly_pct])
    return len(rows)


def period_summary(days: int = 7, account_id: Optional[str] = None,
                   threshold: int = 80) -> dict:
    """Aggregate the last ``days`` days of history into a small summary dict.

    Returns peak utilisation per limit, sample count, the local hour-of-day
    with the highest average 5-hour usage, and how many samples sat at/above
    ``threshold``. Values are None when there is no data. Note that history
    older than ``history_retention_days`` has been pruned, so the covered
    range (first_ts → last_ts) may be shorter than ``days``.
    """
    cutoff = time.time() - max(1, days) * 86400
    try:
        with _lock:
            conn = _connect()
            cur = conn.execute(
                "SELECT ts, session_pct, weekly_pct, opus_pct FROM snapshots "
                "WHERE ts >= ?" + (" AND account_id = ?" if account_id else "")
                + " ORDER BY ts",
                (cutoff, account_id) if account_id else (cutoff,),
            )
            rows = cur.fetchall()
    except sqlite3.Error:
        rows = []

    if not rows:
        return {
            "samples": 0, "peak_session": None, "peak_weekly": None,
            "peak_opus": None, "busiest_hour": None, "threshold": threshold,
            "threshold_hits": 0, "first_ts": None, "last_ts": None,
        }

    from collections import defaultdict
    import datetime as _dt

    peak_session = max((r[1] for r in rows if r[1] is not None), default=None)
    peak_weekly = max((r[2] for r in rows if r[2] is not None), default=None)
    peak_opus = max((r[3] for r in rows if r[3] is not None), default=None)
    threshold_hits = sum(1 for r in rows if r[1] is not None and r[1] >= threshold)

    by_hour_sum: dict = defaultdict(float)
    by_hour_n: dict = defaultdict(int)
    for ts, s, _w, _o in rows:
        if s is None:
            continue
        hour = _dt.datetime.fromtimestamp(ts).hour
        by_hour_sum[hour] += s
        by_hour_n[hour] += 1
    busiest_hour = None
    if by_hour_n:
        busiest_hour = max(
            by_hour_n, key=lambda h: by_hour_sum[h] / by_hour_n[h]
        )

    return {
        "samples": len(rows),
        "peak_session": peak_session,
        "peak_weekly": peak_weekly,
        "peak_opus": peak_opus,
        "busiest_hour": busiest_hour,
        "threshold": threshold,
        "threshold_hits": threshold_hits,
        "first_ts": rows[0][0],
        "last_ts": rows[-1][0],
    }


def weekly_summary(account_id: Optional[str] = None,
                   threshold: int = 80) -> dict:
    """Back-compat wrapper: a 7-day :func:`period_summary`."""
    return period_summary(7, account_id, threshold)


def export_period_summary(path: str | Path, account_name: str, days: int = 7,
                          account_id: Optional[str] = None,
                          threshold: int = 80) -> Optional[Path]:
    """Write a human-readable usage summary (Markdown) over ``days`` days.
    Returns the path, or None when there is no history to summarise."""
    from datetime import datetime
    from i18n import t

    data = period_summary(days, account_id, threshold)
    if not data["samples"]:
        return None

    def _iso(ts):
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "—"

    def _pct(v):
        return f"{v}%" if v is not None else "—"

    hour = data["busiest_hour"]
    hour_txt = f"{hour:02d}:00–{(hour + 1) % 24:02d}:00" if hour is not None else "—"

    lines = [
        f"# {t('summary.title')}",
        "",
        f"- **{t('summary.account')}:** {account_name}",
        f"- **{t('summary.generated')}:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- **{t('summary.range', days=days)}:** {_iso(data['first_ts'])} → {_iso(data['last_ts'])}",
        f"- **{t('summary.samples')}:** {data['samples']}",
        "",
        f"- **{t('summary.peak_session')}:** {_pct(data['peak_session'])}",
        f"- **{t('summary.peak_weekly')}:** {_pct(data['peak_weekly'])}",
    ]
    if data["peak_opus"] is not None:
        lines.append(f"- **{t('summary.peak_opus')}:** {_pct(data['peak_opus'])}")
    lines += [
        f"- **{t('summary.busiest_hour')}:** {hour_txt}",
        f"- **{t('summary.threshold_hits', pct=data['threshold'])}:** {data['threshold_hits']}",
        "",
    ]

    p = Path(path)
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def export_weekly_summary(path: str | Path, account_name: str,
                          account_id: Optional[str] = None,
                          threshold: int = 80) -> Optional[Path]:
    """Back-compat wrapper: a 7-day :func:`export_period_summary`."""
    return export_period_summary(path, account_name, 7, account_id, threshold)


def prune(retention_days: int) -> None:
    """Delete rows older than retention_days."""
    if retention_days <= 0:
        return
    cutoff = time.time() - retention_days * 86400
    try:
        with _lock:
            conn = _connect()
            conn.execute("DELETE FROM snapshots WHERE ts < ?", (cutoff,))
            conn.commit()
    except sqlite3.Error:
        pass
