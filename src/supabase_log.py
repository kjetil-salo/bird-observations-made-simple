# Enkel Supabase-logging for fugleobservasjoner
import logging
import os
from src.utils import parse_user_agent

try:
    from supabase import create_client
except ImportError:
    create_client = None

logger = logging.getLogger('fugleobs')

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase = None
if SUPABASE_URL and SUPABASE_KEY and create_client:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def log_view_to_supabase(ip: str, user_agent: str, device_id: str = ''):
    if not supabase:
        return False
    try:
        ua_info = parse_user_agent(user_agent)

        data = {
            "ip": ip,
            "user_agent": user_agent,  # Behold original som backup
            "device_type": ua_info["device_type"],
            "os": ua_info["os"],
            "browser": ua_info["browser"],
            # timestamp settes automatisk av Supabase (default now())
        }
        if device_id:
            data["device_id"] = device_id
        supabase.table("stats").insert(data).execute()
        return True
    except Exception as e:
        logger.warning(f"[Supabase] Feil ved logging: {e}")
        return False


def get_stats_from_supabase():
    """Hent aggregert statistikk fra Supabase via RPC-funksjon."""
    if not supabase:
        return None
    try:
        result = supabase.rpc("get_stats").execute()
        data = result.data
        if not data:
            return None

        top_ips = [(r["ip"], r["cnt"]) for r in (data.get("top_ips") or [])]

        from datetime import date, timedelta
        today = date.today()
        trend_map = {(today - timedelta(days=i)).isoformat(): 0 for i in range(29, -1, -1)}
        for r in (data.get("trend_30d") or []):
            d = str(r.get("dato", ""))[:10]
            if d in trend_map:
                trend_map[d] = r.get("cnt", 0)
        trend_30d = list(trend_map.items())

        # Unike enheter per dag (krever oppdatert get_stats-RPC i Supabase; tom hvis ikke)
        raw_unique = data.get("unique_devices_per_day") or []
        unique_map = {(today - timedelta(days=i)).isoformat(): 0 for i in range(29, -1, -1)}
        for r in raw_unique:
            d = str(r.get("dato", ""))[:10]
            if d in unique_map:
                unique_map[d] = r.get("cnt", 0)
        unique_devices_per_day = list(unique_map.items()) if raw_unique else []

        return {
            "total": data.get("total", 0),
            "total_unique_ips": data.get("unique_ips", 0),
            "total_unique_devices": data.get("unique_devices", 0),
            "recent_ips": top_ips,
            "per_browser": data.get("per_browser") or {},
            "per_os": data.get("per_os") or {},
            "exports": data.get("exports") or {},
            "trend_30d": trend_30d,
            "unique_devices_per_day": unique_devices_per_day,
            "unique_users_per_week": get_weekly_unique_users(),
        }
    except Exception as e:
        logger.warning(f"[Supabase] Feil ved henting av stats: {e}")
        return None


def get_weekly_unique_users(weeks: int = 26):
    """Ukentlige unike brukere (ISO-uke, mandag).

    Identitet = device_id (UUID-cookie) der den finnes, ellers fallback til IP.
    Ekskluderer localhost. Henter kun de siste `weeks` ukene for å begrense last.
    Returnerer liste av (uke_mandag_iso, antall) sortert stigende, eller [].
    """
    if not supabase:
        return []
    try:
        from datetime import datetime, date, timedelta
        today = date.today()
        this_monday = today - timedelta(days=today.weekday())
        cutoff = (this_monday - timedelta(weeks=weeks - 1)).isoformat()

        skip_ip = {"127.0.0.1", "::1", "localhost"}
        week_sets = {}
        step = 1000
        start = 0
        while True:
            res = (
                supabase.table("stats")
                .select("ip,timestamp,device_id")
                .gte("timestamp", cutoff)
                .order("id")
                .range(start, start + step - 1)
                .execute()
            )
            batch = res.data or []
            for row in batch:
                ip = (row.get("ip") or "").strip()
                if ip in skip_ip:
                    continue
                ts = row.get("timestamp")
                if not ts:
                    continue
                d = datetime.fromisoformat(ts).date()
                monday = (d - timedelta(days=d.weekday())).isoformat()
                ident = row.get("device_id") or ("ip:" + ip)
                week_sets.setdefault(monday, set()).add(ident)
            if len(batch) < step:
                break
            start += step

        # Fyll ut tomme uker slik at grafen blir sammenhengende
        result = []
        for i in range(weeks):
            wk = (this_monday - timedelta(weeks=weeks - 1 - i)).isoformat()
            result.append((wk, len(week_sets.get(wk, ()))))
        return result
    except Exception as e:
        logger.warning(f"[Supabase] Feil ved henting av ukentlige unike brukere: {e}")
        return []


def log_export_to_supabase(export_type: str) -> bool:
    """Logg eksport-hendelse til Supabase ('copy_open' eller 'direct')."""
    if not supabase:
        return False
    try:
        supabase.table("exports").insert({"type": export_type}).execute()
        return True
    except Exception as e:
        logger.warning(f"[Supabase] Feil ved logging av eksport: {e}")
        return False
