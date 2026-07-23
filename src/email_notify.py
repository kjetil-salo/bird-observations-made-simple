"""
Epost-varsling ved nye tilbakemeldinger (fase 2 av tilbakemeldingskanalen).

Sender et varsel til eier når en ny sak kommer inn, slik at kanalen faktisk
blir sett uten å måtte sjekke /feedback-admin manuelt. Hvis melderen oppga
e-post, settes `Reply-To` til den — da går et «Svar» rett til brukeren
(«bruker starter på forms, tas videre på e-post»).

Provider auto-detekteres fra miljøvariabler, og hele modulen er en ren no-op
hvis ingenting er konfigurert (samme filosofi som valgfri Supabase-logging).
Prioritert rekkefølge:

  1. SMTP (SMTP_HOST + SMTP_USER + SMTP_PASS) → send via smtplib/STARTTLS.
     Gjenbruker eksisterende SMTP2GO-oppsett (mail-eu.smtp2go.com:2525).
  2. RESEND_API_KEY   → send via Resend (https://api.resend.com)
  3. SMTP2GO_API_KEY  → send via SMTP2GO HTTP-API (https://api.smtp2go.com)

Felles:
  FEEDBACK_NOTIFY_TO    → mottaker (eier). Uten denne sendes ingenting.
  FEEDBACK_NOTIFY_FROM  → avsender (må være verifisert hos provideren)
  SMTP_PORT             → valgfri, default 2525

Sendingen er «best effort»: feil logges, men kaster aldri videre og skal
aldri påvirke svaret til brukeren.
"""
import logging
import os

logger = logging.getLogger('fugleobs')

_TYPE_LABEL = {'feil': 'Feil', 'ønske': 'Ønske', 'annet': 'Annet'}


def is_configured() -> bool:
    """True hvis både en provider og mottaker er satt."""
    to = os.environ.get('FEEDBACK_NOTIFY_TO')
    smtp = os.environ.get('SMTP_HOST') and os.environ.get('SMTP_USER') and os.environ.get('SMTP_PASS')
    provider = smtp or os.environ.get('RESEND_API_KEY') or os.environ.get('SMTP2GO_API_KEY')
    return bool(to and provider)


def _build_body(case_no, fb_type, message, email, app_version, device):
    reporter = email or '(ikke oppgitt)'
    return (
        f"Ny tilbakemelding i Enkel-AO.\n\n"
        f"Saksnummer: {case_no}\n"
        f"Type:       {_TYPE_LABEL.get(fb_type, fb_type)}\n"
        f"Fra:        {reporter}\n"
        f"Versjon:    {app_version or '-'}\n"
        f"Enhet:      {device or '-'}\n\n"
        f"Melding:\n{message}\n\n"
        f"— Svar på denne e-posten for å svare melderen direkte "
        f"(hvis e-post ble oppgitt).\n"
    )


def _send_smtp(sender, to, subject, body, reply_to):
    import smtplib
    from email.message import EmailMessage

    host = os.environ.get('SMTP_HOST')
    port = int(os.environ.get('SMTP_PORT', '2525'))
    user = os.environ.get('SMTP_USER')
    password = os.environ.get('SMTP_PASS')

    msg = EmailMessage()
    msg['From'] = sender
    msg['To'] = to
    msg['Subject'] = subject
    if reply_to:
        msg['Reply-To'] = reply_to
    msg.set_content(body)

    with smtplib.SMTP(host, port, timeout=10) as s:
        s.starttls()
        s.login(user, password)
        s.send_message(msg)


def _send_resend(api_key, sender, to, subject, body, reply_to):
    import httpx
    payload = {'from': sender, 'to': [to], 'subject': subject, 'text': body}
    if reply_to:
        payload['reply_to'] = reply_to
    r = httpx.post(
        'https://api.resend.com/emails',
        headers={'Authorization': f'Bearer {api_key}'},
        json=payload,
        timeout=10.0,
    )
    r.raise_for_status()


def _send_smtp2go(api_key, sender, to, subject, body, reply_to):
    import httpx
    payload = {
        'sender': sender,
        'to': [to],
        'subject': subject,
        'text_body': body,
    }
    if reply_to:
        payload['custom_headers'] = [{'header': 'Reply-To', 'value': reply_to}]
    r = httpx.post(
        'https://api.smtp2go.com/v3/email/send',
        headers={'X-Smtp2go-Api-Key': api_key, 'Content-Type': 'application/json'},
        json=payload,
        timeout=10.0,
    )
    r.raise_for_status()


def send_feedback_notification(case_no, fb_type, message, email='',
                               app_version='', device='') -> bool:
    """Send varsel om ny tilbakemelding til eier. Best effort, kaster aldri."""
    to = os.environ.get('FEEDBACK_NOTIFY_TO')
    if not to:
        return False  # ikke konfigurert → stille no-op

    sender = os.environ.get('FEEDBACK_NOTIFY_FROM', to)
    subject = f"[Enkel-AO] Ny tilbakemelding {case_no} ({_TYPE_LABEL.get(fb_type, fb_type)})"
    body = _build_body(case_no, fb_type, message, email, app_version, device)
    reply_to = email or None

    smtp_ready = os.environ.get('SMTP_HOST') and os.environ.get('SMTP_USER') and os.environ.get('SMTP_PASS')
    resend_key = os.environ.get('RESEND_API_KEY')
    smtp2go_key = os.environ.get('SMTP2GO_API_KEY')

    def _dispatch():
        if smtp_ready:
            _send_smtp(sender, to, subject, body, reply_to)
        elif resend_key:
            _send_resend(resend_key, sender, to, subject, body, reply_to)
        elif smtp2go_key:
            _send_smtp2go(smtp2go_key, sender, to, subject, body, reply_to)
        else:
            return False  # ingen provider konfigurert
        return True

    # Ett retry — SMTP-tilkoblinger timer av og til ut forbigående.
    import time
    last_err = None
    for attempt in range(2):
        try:
            if _dispatch() is False:
                return False
            logger.info(f'[FEEDBACK] Varsel sendt for {case_no}')
            return True
        except Exception as e:
            last_err = e
            if attempt == 0:
                time.sleep(1.5)
    logger.warning(f'[FEEDBACK] Klarte ikke sende varsel for {case_no}: {last_err}')
    return False
