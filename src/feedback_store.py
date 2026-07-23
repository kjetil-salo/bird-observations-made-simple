"""
Lagring av brukertilbakemeldinger (feil og ønsker).

Anonyme brukere kan melde fra uten innlogging. Hver innmelding får et
saksnummer (f.eks. «AO-4F7K2») som vises til melderen som kvittering og
brukes som menneskelig nøkkel når eier følger opp saken.

Lagres i samme SQLite-database som statistikken (DB_PATH, default
/data/stats.db) — Pi er primær produksjon og har det varige /data-volumet.
Følger samme mønster som src/sqlite_log.py.

Utsending av epost-kvittering er bevisst IKKE med i denne fasen (krever
epost-provider/infrastruktur). Meldere får saksnummeret på skjerm, og eier
leser innmeldingene på /feedback og svarer manuelt fra egen epost.
"""
import logging
import os
import secrets
import sqlite3
import threading

from src.utils import parse_user_agent

logger = logging.getLogger('fugleobs')

DB_PATH = os.environ.get('DB_PATH', '/data/stats.db')
_lock = threading.Lock()

# Entydig alfabet for saksnummer — utelater tegn som lett forveksles
# (0/O, 1/I/L). Gjør nummeret trygt å lese opp og skrive av for hånd.
_CASE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
_CASE_PREFIX = 'AO-'
_CASE_LENGTH = 5

VALID_TYPES = ('feil', 'ønske', 'annet')
MAX_MESSAGE_LEN = 4000
MAX_EMAIL_LEN = 200
MAX_VERSION_LEN = 40


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                case_no     TEXT UNIQUE,
                type        TEXT,
                message     TEXT NOT NULL,
                email       TEXT,
                app_version TEXT,
                user_agent  TEXT,
                device_type TEXT,
                os          TEXT,
                browser     TEXT,
                ip          TEXT,
                status      TEXT DEFAULT 'ny',
                ts          DATETIME DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_case ON feedback(case_no)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_status ON feedback(status)")
        conn.commit()


def _generate_case_no() -> str:
    """Lag et kort, ikke-gjettbart saksnummer, f.eks. «AO-4F7K2»."""
    body = ''.join(secrets.choice(_CASE_ALPHABET) for _ in range(_CASE_LENGTH))
    return _CASE_PREFIX + body


def create_feedback(message: str, fb_type: str = 'annet', email: str = '',
                    app_version: str = '', user_agent: str = '', ip: str = '') -> str | None:
    """Lagre en tilbakemelding og returner saksnummeret.

    Returnerer None ved feil (kaller sørger for grasiøs degradering).
    Validering av lengder/typer skjer her, slik at endepunktet holdes tynt.
    """
    message = (message or '').strip()
    if not message:
        return None
    message = message[:MAX_MESSAGE_LEN]

    if fb_type not in VALID_TYPES:
        fb_type = 'annet'
    email = (email or '').strip()[:MAX_EMAIL_LEN]
    app_version = (app_version or '').strip()[:MAX_VERSION_LEN]

    ua_info = parse_user_agent(user_agent)

    try:
        with _lock:
            with _connect() as conn:
                # Prøv noen ganger i tilfelle saksnummer-kollisjon (svært usannsynlig)
                for _ in range(5):
                    case_no = _generate_case_no()
                    try:
                        conn.execute(
                            "INSERT INTO feedback "
                            "(case_no, type, message, email, app_version, user_agent, device_type, os, browser, ip) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (case_no, fb_type, message, email, app_version, user_agent,
                             ua_info['device_type'], ua_info['os'], ua_info['browser'], ip)
                        )
                        conn.commit()
                        return case_no
                    except sqlite3.IntegrityError:
                        continue  # kollisjon på case_no — prøv nytt nummer
        logger.warning('[feedback] Klarte ikke generere unikt saksnummer')
        return None
    except Exception as e:
        logger.warning(f'[feedback] Feil ved lagring: {e}')
        return None


def list_feedback(limit: int = 200, status: str = '') -> list:
    """Hent innmeldinger for admin-visning, nyeste først."""
    try:
        with _connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM feedback WHERE status = ? ORDER BY ts DESC LIMIT ?",
                    (status, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM feedback ORDER BY ts DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f'[feedback] Feil ved henting: {e}')
        return []


def count_by_status() -> dict:
    """Antall saker per status — for oversikt på admin-siden."""
    try:
        with _connect() as conn:
            return {
                row['status']: row['cnt']
                for row in conn.execute(
                    "SELECT status, COUNT(*) as cnt FROM feedback GROUP BY status"
                ).fetchall()
            }
    except Exception as e:
        logger.warning(f'[feedback] Feil ved telling: {e}')
        return {}


VALID_STATUSES = ('ny', 'under_arbeid', 'løst', 'avvist')


def set_status(case_no: str, status: str) -> bool:
    """Oppdater status på en sak (admin-handling)."""
    if status not in VALID_STATUSES:
        return False
    try:
        with _lock:
            with _connect() as conn:
                cur = conn.execute(
                    "UPDATE feedback SET status = ? WHERE case_no = ?",
                    (status, case_no)
                )
                conn.commit()
                return cur.rowcount > 0
    except Exception as e:
        logger.warning(f'[feedback] Feil ved statusoppdatering: {e}')
        return False


# Initialiser databasen ved import (samme mønster som sqlite_log)
try:
    init_db()
except Exception as e:
    logger.warning(f'[feedback] Klarte ikke initialisere database: {e}')
