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
