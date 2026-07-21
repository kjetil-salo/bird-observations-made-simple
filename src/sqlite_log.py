"""
SQLite-logging for fugleobservasjoner — erstatning for Supabase.
Databasefil: DB_PATH (env), default /data/stats.db
"""
import logging
import os
import sqlite3
import threading
from src.utils import parse_user_agent

logger = logging.getLogger('fugleobs')

DB_PATH = os.environ.get('DB_PATH', '/data/stats.db')
_lock = threading.Lock()


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ip        TEXT,
                device_id TEXT,
                device_type TEXT,
                os        TEXT,
                browser   TEXT,
                user_agent TEXT,
                ts        DATETIME DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ip ON stats(ip)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_device ON stats(device_id)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exports (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                type  TEXT,
                ts    DATETIME DEFAULT (datetime('now'))
            )
        """)
        conn.commit()


def log_view(ip: str, user_agent: str, device_id: str = '') -> bool:
    try:
        ua_info = parse_user_agent(user_agent)
        with _lock:
            with _connect() as conn:
                conn.execute(
                    "INSERT INTO stats (ip, device_id, device_type, os, browser, user_agent) VALUES (?,?,?,?,?,?)",
                    (ip, device_id, ua_info["device_type"], ua_info["os"], ua_info["browser"], user_agent)
                )
                conn.commit()
        return True
    except Exception as e:
        logger.warning(f"[SQLite] Feil ved logging: {e}")
        return False


def log_export(export_type: str) -> bool:
    """Logg en eksport-hendelse ('copy_open' eller 'direct')."""
    try:
        with _lock:
            with _connect() as conn:
                conn.execute("INSERT INTO exports (type) VALUES (?)", (export_type,))
                conn.commit()
        return True
    except Exception as e:
        logger.warning(f"[SQLite] Feil ved logging av eksport: {e}")
        return False


def get_stats() -> dict:
    """Returnerer statistikk for /stats-siden."""
    try:
        with _connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM stats").fetchone()[0]
            total_unique_ips = conn.execute("SELECT COUNT(DISTINCT ip) FROM stats").fetchone()[0]
            total_unique_devices = conn.execute("SELECT COUNT(DISTINCT device_id) FROM stats WHERE device_id != ''").fetchone()[0]

            recent_ips = [
                (row["ip"], row["cnt"])
                for row in conn.execute(
                    "SELECT ip, COUNT(*) as cnt FROM stats GROUP BY ip ORDER BY MAX(ts) DESC LIMIT 10"
                ).fetchall()
            ]

            per_browser = {
                row["browser"]: row["cnt"]
                for row in conn.execute(
                    "SELECT browser, COUNT(*) as cnt FROM stats GROUP BY browser ORDER BY cnt DESC"
                ).fetchall()
            }

            per_os = {
                row["os"]: row["cnt"]
                for row in conn.execute(
                    "SELECT os, COUNT(*) as cnt FROM stats GROUP BY os ORDER BY cnt DESC"
                ).fetchall()
            }

            exports = {
                row["type"]: row["cnt"]
                for row in conn.execute(
                    "SELECT type, COUNT(*) as cnt FROM exports GROUP BY type"
                ).fetchall()
            }

            from datetime import date, timedelta
            today = date.today()
            trend_map = {(today - timedelta(days=i)).isoformat(): 0 for i in range(29, -1, -1)}
            for row in conn.execute(
                "SELECT DATE(ts) as dato, COUNT(*) as cnt FROM stats "
                "WHERE ts >= DATE('now', '-29 days') GROUP BY dato ORDER BY dato"
            ).fetchall():
                d = row["dato"]
                if d in trend_map:
                    trend_map[d] = row["cnt"]
            trend_30d = list(trend_map.items())

            # Unike enheter (device_id fra UUID-cookie) per dag – mer nyttig enn sidevisninger
            unique_map = {(today - timedelta(days=i)).isoformat(): 0 for i in range(29, -1, -1)}
            for row in conn.execute(
                "SELECT DATE(ts) as dato, COUNT(DISTINCT device_id) as cnt FROM stats "
                "WHERE device_id != '' AND ts >= DATE('now', '-29 days') GROUP BY dato ORDER BY dato"
            ).fetchall():
                d = row["dato"]
                if d in unique_map:
                    unique_map[d] = row["cnt"]
            unique_devices_per_day = list(unique_map.items())

            # Ukentlige unike brukere (device_id, fallback IP) – siste 26 uker, ISO-uke (mandag)
            weeks = 26
            this_monday = today - timedelta(days=today.weekday())
            week_counts = {}
            for row in conn.execute(
                "SELECT DATE(ts, '-' || ((strftime('%w', ts) + 6) % 7) || ' days') AS uke, "
                "COUNT(DISTINCT COALESCE(NULLIF(device_id, ''), 'ip:' || ip)) AS cnt "
                "FROM stats WHERE ip NOT IN ('127.0.0.1', '::1', 'localhost') "
                "AND ts >= DATE('now', '-' || ? || ' days') GROUP BY uke ORDER BY uke",
                (weeks * 7,)
            ).fetchall():
                week_counts[row["uke"]] = row["cnt"]
            unique_users_per_week = [
                ((this_monday - timedelta(weeks=weeks - 1 - i)).isoformat(),
                 week_counts.get((this_monday - timedelta(weeks=weeks - 1 - i)).isoformat(), 0))
                for i in range(weeks)
            ]

        return {
            "total": total,
            "total_unique_ips": total_unique_ips,
            "total_unique_devices": total_unique_devices,
            "recent_ips": recent_ips,
            "per_browser": per_browser,
            "per_os": per_os,
            "exports": exports,
            "trend_30d": trend_30d,
            "unique_devices_per_day": unique_devices_per_day,
            "unique_users_per_week": unique_users_per_week,
        }
    except Exception as e:
        logger.warning(f"[SQLite] Feil ved henting av stats: {e}")
        return None


# Initialiser databasen ved import
try:
    init_db()
except Exception as e:
    logger.warning(f"[SQLite] Klarte ikke initialisere database: {e}")
