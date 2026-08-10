"""
HTML templates for fugleobservasjoner.

Genererer HTML-sider for statistikk og login.
"""

import html as _html


def generate_stats_login_page():
    """Generer login-side for statistikk."""
    return """
<html>
<head><meta name='viewport' content='width=device-width,initial-scale=1'><title>Logg inn for statistikk</title></head>
<body style="font-family:system-ui, sans-serif;padding:18px;">
    <h2>Logg inn</h2>
    <p>Oppgi nøkkel for å se statistikk.</p>
    <input id="stats-key" type="text" placeholder="Skriv inn nøkkel" style="padding:8px;font-size:16px;" />
    <button id="stats-go" style="padding:8px 10px;margin-left:8px;">Vis</button>
    <p style="color:#666;margin-top:12px;font-size:0.9rem">Nøkkelen lagres i din nettleser slik at du ikke må skrive den igjen.</p>
    <script>
        (function(){
            const inp = document.getElementById('stats-key');
            const btn = document.getElementById('stats-go');
            const saved = localStorage.getItem('stats_key');
            if (saved) inp.value = saved;
            btn.addEventListener('click', () => {
                const v = inp.value.trim();
                if (!v) return alert('Skriv inn nøkkel');
                localStorage.setItem('stats_key', v);
                location.search = '?key=' + encodeURIComponent(v);
            });
        })();
    </script>
</body>
</html>
"""


def generate_stats_page(recent_ips, per_ua, total, per_device=None, per_os=None, per_browser=None, total_unique_ips=0, source="Supabase", total_unique_devices=0, exports=None, trend_30d=None, trend_7d=None, unique_devices_per_day=None, unique_users_per_week=None):
    """Generer statistikk-side med data fra enten Supabase eller in-memory."""
    per_device = per_device or {}
    per_os = per_os or {}
    per_browser = per_browser or {}
    exports = exports or {}
    trend_30d = trend_30d or trend_7d or []
    export_copy_open = exports.get('copy_open', 0)
    export_direct = exports.get('direct', 0)
    export_total = export_copy_open + export_direct

    # recent_ips er liste av (ip, count) tuples, allerede sortert nyeste først
    ip_rows = ''.join(f'<tr><td><a href="https://ipinfo.io/{ip}" target="_blank" rel="noopener">{ip}</a></td><td>{count}</td></tr>'
                     for ip, count in recent_ips)

    # Device, OS, Browser - kompakte tabeller
    device_rows = ''.join(f'<tr><td>{d}</td><td>{c}</td></tr>'
                         for d, c in sorted(per_device.items(), key=lambda x: -x[1]))
    os_rows = ''.join(f'<tr><td>{o}</td><td>{c}</td></tr>'
                     for o, c in sorted(per_os.items(), key=lambda x: -x[1]))
    browser_rows = ''.join(f'<tr><td>{b}</td><td>{c}</td></tr>'
                          for b, c in sorted(per_browser.items(), key=lambda x: -x[1]))

    # User-agent - vis bare topp 10
    ua_sorted = sorted(per_ua.items(), key=lambda x: -x[1])[:10]
    ua_rows = ''.join(f'<tr><td style="word-break:break-all;max-width:400px">{ua}</td><td>{count}</td></tr>'
                     for ua, count in ua_sorted)

    # Bygg device/os/browser seksjon kun hvis data finnes
    device_section = ""
    if per_device or per_os or per_browser:
        device_section = '<div class="stats-grid">'
        if per_device:
            device_section += f'''
            <div class="stats-card">
                <div class="card-title">Enhetstype</div>
                <table>
                    <tr><th>Type</th><th>Antall</th></tr>
                    {device_rows}
                </table>
            </div>
            '''
        if per_os:
            device_section += f'''
            <div class="stats-card">
                <div class="card-title">Operativsystem</div>
                <table>
                    <tr><th>OS</th><th>Antall</th></tr>
                    {os_rows}
                </table>
            </div>
            '''
        if per_browser:
            device_section += f'''
            <div class="stats-card">
                <div class="card-title">Nettleser</div>
                <table>
                    <tr><th>Browser</th><th>Antall</th></tr>
                    {browser_rows}
                </table>
            </div>
            '''
        device_section += '</div>'

    # Unike enheter per dag (basert på UUID-cookie) – den viktigste metrikken
    unique_devices_per_day = unique_devices_per_day or []
    unique_today = unique_devices_per_day[-1][1] if unique_devices_per_day else 0
    unique_section = ""
    if unique_devices_per_day:
        u_labels = [dato for dato, _ in unique_devices_per_day]
        u_values = [cnt for _, cnt in unique_devices_per_day]
        unique_section = f'''
        <div class="section-title">Unike enheter per dag (siste 30 dager)</div>
        <canvas id="uniqueChart" style="width:100%;max-height:220px;"></canvas>
        <script>
        (function() {{
            var ctx = document.getElementById('uniqueChart').getContext('2d');
            new Chart(ctx, {{
                type: 'bar',
                data: {{
                    labels: {u_labels},
                    datasets: [{{
                        label: 'Unike enheter',
                        data: {u_values},
                        backgroundColor: 'rgba(34, 197, 94, 0.6)',
                        borderColor: 'rgba(34, 197, 94, 1)',
                        borderWidth: 1
                    }}]
                }},
                options: {{
                    responsive: true,
                    plugins: {{ legend: {{ display: false }} }},
                    scales: {{
                        x: {{ ticks: {{ maxRotation: 45, font: {{ size: 10 }} }} }},
                        y: {{ beginAtZero: true, ticks: {{ stepSize: 1 }} }}
                    }}
                }}
            }});
        }})();
        </script>
        '''

    # Ukentlige unike brukere (device_id, fallback IP) – siste uke er pågående
    unique_users_per_week = unique_users_per_week or []
    weekly_section = ""
    if unique_users_per_week:
        w_labels = [uke[5:] for uke, _ in unique_users_per_week]  # MM-DD
        w_values = [cnt for _, cnt in unique_users_per_week]
        # Grå farge på siste (pågående) uke, grønn ellers
        w_colors = ["rgba(34, 197, 94, 0.6)"] * len(w_values)
        w_borders = ["rgba(34, 197, 94, 1)"] * len(w_values)
        if w_colors:
            w_colors[-1] = "rgba(148, 163, 184, 0.5)"
            w_borders[-1] = "rgba(148, 163, 184, 1)"
        weekly_section = f'''
        <div class="section-title">Ukentlige unike brukere (siste {len(w_values)} uker)</div>
        <div style="color:#888;font-size:0.85em;margin-bottom:0.5em;">Unik = device-cookie (fallback IP). Siste stolpe er pågående uke.</div>
        <canvas id="weeklyChart" style="width:100%;max-height:240px;"></canvas>
        <script>
        (function() {{
            var ctx = document.getElementById('weeklyChart').getContext('2d');
            new Chart(ctx, {{
                type: 'bar',
                data: {{
                    labels: {w_labels},
                    datasets: [{{
                        label: 'Unike brukere',
                        data: {w_values},
                        backgroundColor: {w_colors},
                        borderColor: {w_borders},
                        borderWidth: 1
                    }}]
                }},
                options: {{
                    responsive: true,
                    plugins: {{ legend: {{ display: false }} }},
                    scales: {{
                        x: {{ ticks: {{ maxRotation: 60, minRotation: 45, font: {{ size: 10 }} }} }},
                        y: {{ beginAtZero: true, ticks: {{ stepSize: 10 }} }}
                    }}
                }}
            }});
        }})();
        </script>
        '''

    trend_section = ""
    if trend_30d:
        labels = [dato for dato, _ in trend_30d]
        values = [cnt for _, cnt in trend_30d]
        trend_section = f'''
        <div class="section-title">Sidevisninger siste 30 dager</div>
        <canvas id="trendChart" style="width:100%;max-height:220px;"></canvas>
        <script>
        (function() {{
            var ctx = document.getElementById('trendChart').getContext('2d');
            new Chart(ctx, {{
                type: 'bar',
                data: {{
                    labels: {labels},
                    datasets: [{{
                        label: 'Sidevisninger',
                        data: {values},
                        backgroundColor: 'rgba(59, 130, 246, 0.6)',
                        borderColor: 'rgba(59, 130, 246, 1)',
                        borderWidth: 1
                    }}]
                }},
                options: {{
                    responsive: true,
                    plugins: {{ legend: {{ display: false }} }},
                    scales: {{
                        x: {{ ticks: {{ maxRotation: 45, font: {{ size: 10 }} }} }},
                        y: {{ beginAtZero: true, ticks: {{ stepSize: 1 }} }}
                    }}
                }}
            }});
        }})();
        </script>
        '''

    # Chart.js lastes én gang hvis noen av grafene skal vises
    chartjs_load = ''
    if unique_section or trend_section or weekly_section:
        chartjs_load = '<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>'

    return f"""
<html>
<head>
    <title>Brukerstatistikk ({source})</title>
    <meta name='viewport' content='width=device-width, initial-scale=1'>
    <style>
        body {{ font-family: system-ui, sans-serif; background: #f8f9fa; color: #222; margin: 0; padding: 0; }}
        .container {{ max-width: 900px; margin: 2em auto; background: #fff; border-radius: 10px; box-shadow: 0 2px 8px #0001; padding: 2em; }}
        h1, h2, h3 {{ margin-top: 0; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 1em; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background: #f0f0f0; }}
        .stat-row {{ display: flex; gap: 2em; align-items: center; font-size: 1.5em; font-weight: bold; margin-bottom: 1em; }}
        .section-title {{ margin-top: 2em; margin-bottom: 0.5em; font-size: 1.2em; color: #444; }}
        .source {{ color: #666; font-size: 0.9em; margin-top: 2em; text-align: right; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1em; margin-bottom: 2em; }}
        .stats-card {{ background: #f8f9fa; border-radius: 8px; padding: 1em; }}
        .card-title {{ font-weight: 600; margin-bottom: 0.5em; color: #333; }}
        .stats-card table {{ margin-bottom: 0; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Brukerstatistikk</h1>
        <div class="stat-row">
            <span>🟢 {unique_today} unike enheter i dag</span>
            <span>{total_unique_devices} unike enheter totalt</span>
            <span>{total} sidevisninger</span>
        </div>
        <div class="stat-row" style="font-size:1.1em;">
            <span>📤 {export_total} eksporter totalt</span>
            <span>📋 {export_copy_open} via importside</span>
            <span>📡 {export_direct} direkte til AO</span>
        </div>

        {chartjs_load}
        {weekly_section}
        {unique_section}
        {trend_section}
        <div class="section-title">Siste 10 IP-adresser</div>
        <table>
            <tr><th>IP-adresse</th><th>Antall visninger</th></tr>
            {ip_rows}
        </table>

        {device_section}
        <div class="source">Datakilde: {source}</div>
    </div>
</body>
</html>
"""


def generate_error_page(error_msg):
    """Generer feilside for statistikk."""
    return f"""
<html>
<body>
    <h2>Feil ved henting av statistikk fra Supabase:</h2>
    <pre>{error_msg}</pre>
</body>
</html>
"""


_FEEDBACK_TYPE_LABEL = {'feil': '🐛 Feil', 'ønske': '💡 Ønske', 'annet': '💬 Annet'}
_FEEDBACK_STATUS_LABEL = {
    'ny': 'Ny', 'under_arbeid': 'Under arbeid', 'løst': 'Løst', 'avvist': 'Avvist',
}
_FEEDBACK_STATUS_COLOR = {
    'ny': '#2563eb', 'under_arbeid': '#d97706', 'løst': '#16a34a', 'avvist': '#6b7280',
}


def generate_feedback_admin_page(items, counts, key, status_filter=''):
    """Generer key-beskyttet admin-visning av innmeldte tilbakemeldinger."""
    counts = counts or {}
    total = sum(counts.values())

    # Filter-lenker med antall per status
    def _filter_link(value, label):
        n = total if not value else counts.get(value, 0)
        active = (status_filter == value)
        style = 'font-weight:700;text-decoration:underline;' if active else ''
        q = f'?key={_html.escape(key)}'
        if value:
            q += f'&status={value}'
        return f'<a href="{q}" style="margin-right:14px;color:#2563eb;{style}">{label} ({n})</a>'

    filters = _filter_link('', 'Alle') + ''.join(
        _filter_link(s, _FEEDBACK_STATUS_LABEL[s]) for s in ('ny', 'under_arbeid', 'løst', 'avvist')
    )

    rows = []
    for it in items:
        case_no = _html.escape(str(it.get('case_no') or ''))
        fb_type = it.get('type') or 'annet'
        type_label = _FEEDBACK_TYPE_LABEL.get(fb_type, _html.escape(fb_type))
        message = _html.escape(str(it.get('message') or '')).replace('\n', '<br>')
        email = _html.escape(str(it.get('email') or ''))
        email_cell = f'<a href="mailto:{email}?subject=Sak%20{case_no}">{email}</a>' if email else '<span style="color:#999">—</span>'
        ts = _html.escape(str(it.get('ts') or ''))
        version = _html.escape(str(it.get('app_version') or ''))
        device = _html.escape(' / '.join(x for x in (
            it.get('device_type'), it.get('os'), it.get('browser')) if x and x != 'unknown'))
        status = it.get('status') or 'ny'
        color = _FEEDBACK_STATUS_COLOR.get(status, '#333')

        options = ''.join(
            f'<option value="{s}"{" selected" if s == status else ""}>{_FEEDBACK_STATUS_LABEL[s]}</option>'
            for s in ('ny', 'under_arbeid', 'løst', 'avvist')
        )
        status_select = (
            f'<select onchange="setStatus(\'{case_no}\', this.value)" '
            f'style="padding:4px;border-radius:6px;border:1px solid #ccc;color:{color};font-weight:600;">{options}</select>'
        )

        rows.append(f"""
        <tr>
            <td style="white-space:nowrap;"><strong>{case_no}</strong><br>
                <span style="color:#888;font-size:0.8em;">{ts}</span></td>
            <td style="white-space:nowrap;">{type_label}</td>
            <td>{message}</td>
            <td style="white-space:nowrap;font-size:0.85em;">{email_cell}</td>
            <td style="white-space:nowrap;font-size:0.8em;color:#666;">{version}<br>{device}</td>
            <td style="white-space:nowrap;">{status_select}</td>
        </tr>""")

    if not rows:
        rows_html = '<tr><td colspan="6" style="text-align:center;color:#888;padding:2em;">Ingen tilbakemeldinger ennå.</td></tr>'
    else:
        rows_html = ''.join(rows)

    return f"""<!DOCTYPE html>
<html lang="nb">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Tilbakemeldinger</title>
    <style>
        body {{ font-family: system-ui, sans-serif; background: #f8f9fa; color: #222; margin: 0; padding: 0; }}
        .container {{ max-width: 1100px; margin: 1.5em auto; background: #fff; border-radius: 10px; box-shadow: 0 2px 8px #0001; padding: 1.5em 2em; }}
        h1 {{ margin: 0 0 0.3em 0; }}
        .filters {{ margin: 0.5em 0 1.2em 0; font-size: 0.95em; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ border-bottom: 1px solid #eee; padding: 10px 8px; text-align: left; vertical-align: top; }}
        th {{ background: #f0f0f0; font-size: 0.85em; text-transform: uppercase; letter-spacing: 0.03em; color: #555; }}
        td {{ font-size: 0.95em; }}
        a {{ text-decoration: none; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>💬 Tilbakemeldinger</h1>
        <div class="filters">{filters}</div>
        <table>
            <thead>
                <tr><th>Sak / tid</th><th>Type</th><th>Melding</th><th>Epost</th><th>Versjon / enhet</th><th>Status</th></tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>
    </div>
    <script>
        const KEY = {_html.escape(repr(key))};
        async function setStatus(caseNo, status) {{
            try {{
                const r = await fetch('/api/feedback-status?key=' + encodeURIComponent(KEY), {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ caseNo, status }})
                }});
                if (!r.ok) alert('Kunne ikke oppdatere status');
            }} catch (e) {{ alert('Feil: ' + e.message); }}
        }}
    </script>
</body>
</html>
"""


_MND = ['januar', 'februar', 'mars', 'april', 'mai', 'juni',
        'juli', 'august', 'september', 'oktober', 'november', 'desember']


def _norsk_dato(iso):
    """«2026-07-27T15:00:00» → «27. juli 2026». Tom streng hvis ugyldig."""
    if not iso or len(iso) < 10:
        return ''
    try:
        aar, mnd, dag = int(iso[0:4]), int(iso[5:7]), int(iso[8:10])
        return f'{dag}. {_MND[mnd - 1]} {aar}'
    except (ValueError, IndexError):
        return ''


def _klokke(obs):
    """«15:00» eller «15:00–16:30» ut fra timestamp/tilKlokkeslett."""
    fra = (obs.get('timestamp') or '')[11:16]
    til = (obs.get('tilKlokkeslett') or '')[11:16]
    if fra and til and til != fra:
        return f'{fra}–{til}'
    return fra


def generate_share_page(share, base_url=''):
    """
    Generer den offentlige delingssiden for et sett observasjoner.

    Alt brukerinnhold escapes. Kun feltene share_store slipper gjennom vises —
    aldri koordinater. Egne OG-tagger gjør at lenken ser pen ut limt inn i
    Messenger/Facebook.
    """
    obs_list = share.get('observations') or []
    navn = (share.get('display_name') or '').strip()
    epost = (share.get('email') or '').strip()
    identitet = navn or epost

    datoer = sorted({(o.get('timestamp') or '')[:10] for o in obs_list if o.get('timestamp')})
    dato_tekst = _norsk_dato(datoer[-1] + 'T00:00:00') if datoer else ''
    if len(datoer) > 1:
        forste = _norsk_dato(datoer[0] + 'T00:00:00')
        dato_tekst = f'{forste} – {dato_tekst}'

    arter = len({o.get('taxonName', '').lower() for o in obs_list if o.get('taxonName')})
    steder = [s for s in dict.fromkeys(o.get('placeName', '') for o in obs_list) if s]

    # Grupper på lokalitet, i den rekkefølgen lokalitetene dukker opp
    grupper = []
    for sted in steder or ['']:
        i_gruppe = [o for o in obs_list if (o.get('placeName') or '') == sted]
        if i_gruppe:
            grupper.append((sted, i_gruppe))
    if not steder:
        grupper = [('', obs_list)]

    seksjoner = []
    for sted, i_gruppe in grupper:
        rader = []
        for o in i_gruppe:
            antall = o.get('count')
            antall_html = f'<span class="antall">{antall}</span> ' if antall else ''
            detaljer = [d for d in (o.get('activity'), o.get('age'), o.get('gender')) if d]
            detalj_html = (f'<div class="detalj">{_html.escape(" · ".join(detaljer))}</div>'
                           if detaljer else '')
            kommentar = o.get('comment')
            kommentar_html = (f'<div class="kommentar">{_html.escape(kommentar)}</div>'
                              if kommentar else '')
            foto = o.get('photo')
            foto_html = (f'<img class="foto" src="{_html.escape(foto)}" alt="" loading="lazy" />'
                         if foto else '')
            rader.append(f"""
          <li>
            <div class="art">{antall_html}{_html.escape(o.get('taxonName', ''))}</div>
            <div class="tid">{_html.escape(_klokke(o))}</div>
            {detalj_html}{kommentar_html}{foto_html}
          </li>""")
        # Med bare én lokalitet står navnet allerede i ingressen — ikke gjenta det
        vis_sted = sted and len(grupper) > 1
        sted_html = f'<h2>{_html.escape(sted)}</h2>' if vis_sted else ''
        seksjoner.append(f'<section>{sted_html}<ul>{"".join(rader)}</ul></section>')

    if identitet:
        tittel = f'{_html.escape(identitet)} så {arter} art{"er" if arter != 1 else ""}'
    else:
        # Ingen navn eller e-post oppgitt — vis en nøytral rapporttittel
        # i stedet for et anonymt «En fuglekikker».
        tittel = f'Observasjonsrapport fra {_html.escape(steder[0])}' if steder else 'Observasjonsrapport'
    if dato_tekst:
        tittel += f' – {dato_tekst}'
    beskrivelse = f'{len(obs_list)} observasjon{"er" if len(obs_list) != 1 else ""}'
    if steder:
        beskrivelse += f' på {_html.escape(steder[0])}'
        if len(steder) > 1:
            beskrivelse += f' +{len(steder) - 1} sted{"er" if len(steder) > 2 else ""}'

    og_image = f'{base_url}/img/og-image.png' if base_url else '/img/og-image.png'

    return f"""<!doctype html>
<html lang="nb">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{tittel}</title>
  <meta name="robots" content="noindex, nofollow" />
  <meta property="og:title" content="{tittel}" />
  <meta property="og:description" content="{beskrivelse}" />
  <meta property="og:image" content="{og_image}" />
  <meta name="twitter:card" content="summary_large_image" />
  <link rel="icon" href="/favicon.svg" />
  <style>
    :root {{ color-scheme: light dark; }}
    body {{ font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
           margin: 0; padding: 24px 16px 48px; background: #0f172a; color: #e5e7eb;
           line-height: 1.5; }}
    .wrap {{ max-width: 560px; margin: 0 auto; }}
    header {{ margin-bottom: 24px; }}
    h1 {{ font-size: 1.5rem; margin: 0 0 4px; }}
    .meta {{ color: #94a3b8; font-size: 0.95rem; }}
    section {{ background: rgba(255,255,255,0.04); border-radius: 12px;
              padding: 4px 16px 12px; margin-bottom: 16px; }}
    h2 {{ font-size: 1rem; color: #93c5fd; margin: 16px 0 8px; }}
    ul {{ list-style: none; margin: 0; padding: 0; }}
    li {{ padding: 10px 0; border-bottom: 1px solid rgba(148,163,184,0.15); }}
    li:last-child {{ border-bottom: none; }}
    .art {{ font-weight: 600; }}
    .antall {{ color: #86efac; }}
    .tid {{ float: right; color: #94a3b8; font-size: 0.9rem; }}
    .detalj {{ color: #94a3b8; font-size: 0.9rem; }}
    .kommentar {{ color: #cbd5e1; font-size: 0.9rem; font-style: italic; margin-top: 4px; }}
    .foto {{ display: block; max-width: 100%; border-radius: 8px; margin-top: 8px; clear: both; }}
    footer {{ margin-top: 32px; text-align: center; color: #64748b; font-size: 0.85rem; }}
    footer a {{ color: #93c5fd; }}
    @media (prefers-color-scheme: light) {{
      body {{ background: #ffffff; color: #1a1a1a; }}
      .meta, .detalj, .tid {{ color: #64748b; }}
      section {{ background: #f8fafc; }}
      h2 {{ color: #1d4ed8; }}
      .antall {{ color: #16a34a; }}
      .kommentar {{ color: #334155; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>{tittel}</h1>
      <div class="meta">{beskrivelse}</div>
    </header>
    {''.join(seksjoner)}
    <footer>
      Delt fra <a href="/">Enkel-AO</a> · lenken slutter å virke etter en tid
    </footer>
  </div>
</body>
</html>
"""


def generate_share_missing_page():
    """
    Side for lenker som er utløpt eller aldri har eksistert.

    Bevisst samme side for begge tilfeller — ellers kan man teste seg fram til
    hvilke slugs som finnes.
    """
    return """<!doctype html>
<html lang="nb">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Delingen er ikke tilgjengelig</title>
  <meta name="robots" content="noindex, nofollow" />
  <link rel="icon" href="/favicon.svg" />
  <style>
    :root { color-scheme: light dark; }
    body { font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
           background: #0f172a; color: #e5e7eb; display: flex; min-height: 100vh;
           align-items: center; justify-content: center; margin: 0; padding: 24px; }
    .kort { max-width: 420px; text-align: center; }
    h1 { font-size: 1.3rem; margin-bottom: 8px; }
    p { color: #94a3b8; line-height: 1.5; }
    a { color: #93c5fd; }
    @media (prefers-color-scheme: light) {
      body { background: #ffffff; color: #1a1a1a; }
      p { color: #64748b; }
    }
  </style>
</head>
<body>
  <div class="kort">
    <h1>🔍 Denne delingen er ikke tilgjengelig</h1>
    <p>Delinger slutter å virke etter en tid, og kan også trekkes tilbake av den
       som delte dem. Spør gjerne om en ny lenke.</p>
    <p><a href="/">Til Enkel-AO</a></p>
  </div>
</body>
</html>
"""
