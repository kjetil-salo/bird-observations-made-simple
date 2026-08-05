"""
Deling av observasjoner via hemmelig lenke.

Brukeren tar et øyeblikksbilde av dagens funn og får en lenke å sende til
fuglevenner. Lenken er ikke gjettbar, men den er *hemmelig, ikke privat* —
alle som har den kan lese delingen. Den slutter å virke etter SHARE_TTL_DAYS.

Lagres i samme SQLite-database som statistikk og tilbakemeldinger (DB_PATH,
default /data/stats.db). Følger mønsteret fra src/feedback_store.py.

**Utløp uten cron og uten Redis:** hver skriving rydder bort utløpte rader
(`DELETE WHERE expires_ts < now`). Vi beholder ingen TTL-mekanisme utenfor
databasen — og fordi raden slettes først ved neste skriving, kan en utløpt
lenke besvares med «denne delingen er utløpt» framfor en naken 404.

**Personvern:** kun en hviteliste av felt lagres. Koordinater lagres aldri, og
observasjoner med `hideUntil` (skjult på AO) slippes ikke gjennom. Se
docs/deling-av-observasjoner-plan.md.
"""
import json
import logging
import os
import secrets
import sqlite3
import threading
import time

logger = logging.getLogger('fugleobs')

DB_PATH = os.environ.get('DB_PATH', '/data/stats.db')
_lock = threading.Lock()

# Samme entydige alfabet som saksnummer i feedback_store — utelater tegn som
# lett forveksles (0/O, 1/I/L), slik at en lenke også tåler å bli lest opp.
_SLUG_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
_SLUG_LENGTH = 12

SHARE_TTL_DAYS = 14
MAX_OBSERVATIONS = 200
MAX_PAYLOAD_BYTES = 100_000
MAX_NAME_LEN = 40
MAX_EMAIL_LEN = 254
MAX_TEXT_LEN = 500


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS shares (
                slug         TEXT PRIMARY KEY,
                payload      TEXT NOT NULL,
                display_name TEXT,
                delete_key   TEXT NOT NULL,
                created_ts   REAL,
                expires_ts   REAL,
                views        INTEGER DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_shares_expires ON shares(expires_ts)")
        cols = {r[1] for r in conn.execute('PRAGMA table_info(shares)')}
        if 'email' not in cols:
            conn.execute('ALTER TABLE shares ADD COLUMN email TEXT')
        conn.commit()


def _generate_slug() -> str:
    return ''.join(secrets.choice(_SLUG_ALPHABET) for _ in range(_SLUG_LENGTH))


def _purge_expired(conn):
    """Rydd bort utløpte delinger. Kalles ved skriving — ingen cron nødvendig."""
    conn.execute("DELETE FROM shares WHERE expires_ts < ?", (time.time(),))


def _clean_text(value, limit=MAX_TEXT_LEN) -> str:
    if not isinstance(value, str):
        return ''
    return value.strip()[:limit]


def sanitize_observations(raw) -> list:
    """
    Plukk ut de feltene som skal deles — alt annet forkastes.

    Hvitelisting framfor svarteliste: kommer det nye felt på observasjons-
    objektet senere, lekker de ikke ut i en deling ved et uhell. Koordinater
    (`position`) er bevisst ikke med, og observasjoner med `hideUntil` er
    skjult på AO og skal ikke publiseres av oss samtidig.
    """
    if not isinstance(raw, list):
        return []

    rene = []
    for obs in raw[:MAX_OBSERVATIONS]:
        if not isinstance(obs, dict):
            continue
        if obs.get('hideUntil'):
            continue  # skjult på AO — deles ikke

        species = obs.get('species')
        navn = _clean_text(species.get('taxonName'), 120) if isinstance(species, dict) else ''
        if not navn:
            continue

        antall = obs.get('count')
        try:
            antall = int(antall)
        except (TypeError, ValueError):
            antall = None

        rene.append({
            'taxonName': navn,
            'count': antall,
            'activity': _clean_text(obs.get('activity'), 60),
            'age': _clean_text(obs.get('age'), 20),
            'gender': _clean_text(obs.get('gender'), 20),
            'placeName': _clean_text(obs.get('placeName'), 200),
            'timestamp': _clean_text(obs.get('timestamp'), 40),
            'tilKlokkeslett': _clean_text(obs.get('tilKlokkeslett'), 40),
            'comment': _clean_text(obs.get('comment')),
        })
    return rene


def create_share(observations, display_name: str = '', email: str = '',
                 ttl_days: int = SHARE_TTL_DAYS) -> dict | None:
    """
    Lagre en deling og returner {'slug', 'deleteKey', 'expiresTs'}.

    Returnerer None hvis det ikke er noe å dele eller lagringen feiler
    (kaller sørger for grasiøs degradering).

    `email` er en frivillig visnings-fallback (AO-innloggingen er ofte en
    e-post) — brukes av generate_share_page kun når display_name er tom.
    Brukeren har fått opplyst at den i så fall vises offentlig på lenken.
    """
    rene = sanitize_observations(observations)
    if not rene:
        return None

    payload = json.dumps(rene, ensure_ascii=False)
    if len(payload.encode('utf-8')) > MAX_PAYLOAD_BYTES:
        logger.warning('[share] Payload for stor — avviser')
        return None

    display_name = _clean_text(display_name, MAX_NAME_LEN)
    email = _clean_text(email, MAX_EMAIL_LEN)
    if '@' not in email:
        email = ''  # ikke-epost-verdier skal ikke vises offentlig
    delete_key = secrets.token_urlsafe(16)
    now = time.time()
    expires_ts = now + ttl_days * 86400

    try:
        with _lock:
            with _connect() as conn:
                _purge_expired(conn)
                for _ in range(5):
                    slug = _generate_slug()
                    try:
                        conn.execute(
                            "INSERT INTO shares (slug, payload, display_name, email, delete_key, created_ts, expires_ts) "
                            "VALUES (?,?,?,?,?,?,?)",
                            (slug, payload, display_name, email, delete_key, now, expires_ts)
                        )
                        conn.commit()
                        return {'slug': slug, 'deleteKey': delete_key, 'expiresTs': expires_ts}
                    except sqlite3.IntegrityError:
                        continue  # kollisjon — svært usannsynlig, prøv ny slug
        logger.warning('[share] Klarte ikke generere unik slug')
        return None
    except Exception as e:
        logger.warning(f'[share] Feil ved lagring: {e}')
        return None


def get_share(slug: str) -> dict | None:
    """
    Hent en deling. Returnerer None hvis den ikke finnes eller er utløpt.

    Utløpte rader ryddes ved skriving, ikke her — en utløpt deling skal kunne
    besvares som «utløpt», og oppslaget skal ikke skrive til databasen.
    """
    if not slug or not isinstance(slug, str):
        return None
    if len(slug) != _SLUG_LENGTH or any(c not in _SLUG_ALPHABET for c in slug):
        return None

    try:
        with _connect() as conn:
            row = conn.execute("SELECT * FROM shares WHERE slug = ?", (slug,)).fetchone()
            if not row:
                return None
            if row['expires_ts'] and row['expires_ts'] < time.time():
                return None
            conn.execute("UPDATE shares SET views = views + 1 WHERE slug = ?", (slug,))
            conn.commit()
            data = dict(row)
            data['observations'] = json.loads(data.pop('payload'))
            data.pop('delete_key', None)
            return data
    except Exception as e:
        logger.warning(f'[share] Feil ved henting: {e}')
        return None


def delete_share(slug: str, delete_key: str) -> bool:
    """Trekk tilbake en deling. Krever nøkkelen som ble utstedt ved opprettelse."""
    if not slug or not delete_key:
        return False
    try:
        with _lock:
            with _connect() as conn:
                _purge_expired(conn)
                cur = conn.execute(
                    "DELETE FROM shares WHERE slug = ? AND delete_key = ?",
                    (slug, delete_key)
                )
                conn.commit()
                return cur.rowcount > 0
    except Exception as e:
        logger.warning(f'[share] Feil ved sletting: {e}')
        return False


# Initialiser databasen ved import (samme mønster som feedback_store)
try:
    init_db()
except Exception as e:
    logger.warning(f'[share] Klarte ikke initialisere database: {e}')
