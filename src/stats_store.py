"""
Fasade for statistikk-lagring og -uthenting.

Skjuler for resten av appen om dataene ligger i SQLite (primær – Raspberry Pi)
eller Supabase (backup – Fly). Appkoden (server.py) skal kun kalle funksjonene
her og trenger ikke vite noe om hvilken backend som er i bruk.

Skriving: dobbeltskriving til begge backends. SQLite skrives alltid; Supabase
er en no-op hvis den ikke er konfigurert (tom SUPABASE_URL/KEY). Dermed har
Pi (SQLite) og Fly (Supabase) hver sitt komplette datasett.

Lesing: velger automatisk kilden med mest data («richest source wins»).
Dermed leser Pi fra SQLite (Supabase er ukonfigurert der) og Fly fra Supabase
(som har den eldre historikken fra da Fly var hovedplassen) – uten miljø-
spesifikk konfigurasjon.
"""
import logging

from src import sqlite_log, supabase_log

logger = logging.getLogger('fugleobs')


def log_view(ip: str, user_agent: str, device_id: str = '') -> bool:
    """Logg en sidevisning til alle tilgjengelige backends.

    Returnerer True hvis primærbackend (SQLite) lyktes.
    """
    ok = False
    try:
        ok = sqlite_log.log_view(ip, user_agent, device_id=device_id)
    except Exception as e:
        logger.warning(f"[stats] SQLite-logging feilet: {e}")
    try:
        supabase_log.log_view_to_supabase(ip, user_agent, device_id=device_id)
    except Exception as e:
        logger.warning(f"[stats] Supabase-logging feilet: {e}")
    return ok


def log_export(export_type: str) -> bool:
    """Logg en eksport-hendelse til alle tilgjengelige backends."""
    ok = False
    try:
        ok = sqlite_log.log_export(export_type)
    except Exception as e:
        logger.warning(f"[stats] SQLite-eksportlogging feilet: {e}")
    try:
        supabase_log.log_export_to_supabase(export_type)
    except Exception as e:
        logger.warning(f"[stats] Supabase-eksportlogging feilet: {e}")
    return ok


def get_stats():
    """Hent aggregert statistikk.

    Returnerer (stats_dict, kilde) der kilde er "SQLite" eller "Supabase",
    eller (None, None) hvis ingen backend har data. Velger kilden med flest
    sidevisninger, slik at hvert miljø leser fra sin rikeste backend.
    """
    sqlite_stats = None
    try:
        sqlite_stats = sqlite_log.get_stats()
    except Exception as e:
        logger.warning(f"[stats] SQLite-uthenting feilet: {e}")

    supa = None
    try:
        supa = supabase_log.get_stats_from_supabase()  # None hvis ukonfigurert
    except Exception as e:
        logger.warning(f"[stats] Supabase-uthenting feilet: {e}")

    sqlite_total = sqlite_stats.get("total", 0) if sqlite_stats else 0
    supa_total = supa.get("total", 0) if supa else 0

    # Velg backend med mest data
    if supa and supa_total > sqlite_total:
        return supa, "Supabase"
    if sqlite_stats is not None:
        return sqlite_stats, "SQLite"
    if supa:
        return supa, "Supabase"
    return None, None
