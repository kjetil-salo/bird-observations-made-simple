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

# Bilder har et eget budsjett, atskilt fra tekstbudsjettet over — et par
# bilder skal aldri kunne felle hele delingen. Klienten nedskalerer alltid
# til en liten delings-thumbnail (~800px/JPEG q0.6) før innsending; grensene
# her er en server-side bakstopper, ikke den primære størrelsesstyringen.
MAX_PHOTO_BYTES = 120_000
MAX_TOTAL_PHOTO_BYTES = 1_500_000
MAX_PHOTOS_PER_SHARE = 20


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


def _clean_photo(value, budget_used: int, count_used: int) -> tuple[str, int, int]:
    """
    Valider et bilde-felt og hold regnskap mot det delte bildebudsjettet.

    Returnerer (data_url_eller_tom_streng, nytt_budget_brukt, nytt_antall). Et
    bilde som er ugyldig, for stort alene, eller ville sprengt total-budsjettet
    eller antallsgrensen, droppes stille — resten av observasjonen (og
    delingen) skal ikke felles av ett bilde.

    Kun JPEG godtas — det er det klienten faktisk produserer (nedskalert
    canvas-thumbnail). Hvitelisting av mime-type framfor et generelt
    `data:image/`-sjekk stenger blant annet ute `image/svg+xml`, som kan
    inneholde skript — unødvendig risiko på et offentlig, uinnlogget
    endepunkt når vi likevel bare venter oss JPEG.
    """
    if not isinstance(value, str) or not value.startswith('data:image/jpeg;base64,'):
        return '', budget_used, count_used

    size = len(value.encode('utf-8'))
    if size > MAX_PHOTO_BYTES:
        return '', budget_used, count_used
    if count_used >= MAX_PHOTOS_PER_SHARE:
        return '', budget_used, count_used
    if budget_used + size > MAX_TOTAL_PHOTO_BYTES:
        return '', budget_used, count_used

    return value, budget_used + size, count_used + 1


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
    photo_budget_used = 0
    photo_count = 0
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

        foto, photo_budget_used, photo_count = _clean_photo(
            obs.get('photo'), photo_budget_used, photo_count
        )

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
            'photo': foto,
        })
    return rene


def _text_payload_size_ok(rene: list) -> bool:
    """
    Sjekk tekstbudsjettet — beregnet UTEN bilder, som har sitt eget budsjett
    (håndhevet i `_clean_photo` under `sanitize_observations`). Bilder skal
    aldri kunne felle hele delingen slik et for stort tekstinnhold skal.
    """
    tekst_only = [{k: v for k, v in o.items() if k != 'photo'} for o in rene]
    payload = json.dumps(tekst_only, ensure_ascii=False)
    return len(payload.encode('utf-8')) <= MAX_PAYLOAD_BYTES


def _count_dropped_photos(raw: list, rene: list) -> int:
    """
    Hvor mange bilder ble forsøkt delt, men droppet av `_clean_photo`
    (ugyldig format, for stort enkeltbilde, eller budsjett/antall sprengt)?

    Rent informativt tall til klienten — appen skal aldri felle en deling på
    grunn av bilder, men brukeren skal få vite om noe falt bort i stillhet,
    i stedet for at det bare mangler uten forklaring.
    """
    if not isinstance(raw, list):
        return 0
    forsokt = sum(
        1 for o in raw
        if isinstance(o, dict) and isinstance(o.get('photo'), str) and o.get('photo')
    )
    inkludert = sum(1 for o in rene if o.get('photo'))
    return max(0, forsokt - inkludert)


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

    if not _text_payload_size_ok(rene):
        logger.warning('[share] Tekstpayload for stor — avviser')
        return None
    payload = json.dumps(rene, ensure_ascii=False)
    photos_dropped = _count_dropped_photos(observations, rene)

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
                        return {'slug': slug, 'deleteKey': delete_key, 'expiresTs': expires_ts,
                                'photosDropped': photos_dropped}
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


def update_share(slug: str, delete_key: str, observations, display_name: str = '',
                  email: str = '') -> dict | None:
    """
    Oppdater innholdet i en eksisterende deling — samme slug/URL, ny payload.

    Brukes for lange feltøkter (f.eks. Herdla, flere timer i felt) der man vil
    at en allerede utsendt lenke skal vise ferske funn, uten å måtte sende en
    ny lenke til alle. `expires_ts` endres bevisst ikke — en oppdatering
    forlenger ikke levetiden, den bare erstatter innholdet.

    Returnerer None hvis slug ikke finnes, er utløpt, eller nøkkelen er feil.
    """
    if not slug or not delete_key:
        return None
    if len(slug) != _SLUG_LENGTH or any(c not in _SLUG_ALPHABET for c in slug):
        return None

    rene = sanitize_observations(observations)
    if not rene:
        return None

    if not _text_payload_size_ok(rene):
        logger.warning('[share] Tekstpayload for stor ved oppdatering — avviser')
        return None
    payload = json.dumps(rene, ensure_ascii=False)
    photos_dropped = _count_dropped_photos(observations, rene)

    display_name = _clean_text(display_name, MAX_NAME_LEN)
    email = _clean_text(email, MAX_EMAIL_LEN)
    if '@' not in email:
        email = ''

    try:
        with _lock:
            with _connect() as conn:
                _purge_expired(conn)
                cur = conn.execute(
                    "UPDATE shares SET payload = ?, display_name = ?, email = ? "
                    "WHERE slug = ? AND delete_key = ?",
                    (payload, display_name, email, slug, delete_key)
                )
                conn.commit()
                if cur.rowcount == 0:
                    return None
                row = conn.execute(
                    "SELECT expires_ts FROM shares WHERE slug = ?", (slug,)
                ).fetchone()
                return {'slug': slug, 'expiresTs': row['expires_ts'] if row else None,
                        'photosDropped': photos_dropped}
    except Exception as e:
        logger.warning(f'[share] Feil ved oppdatering: {e}')
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
