"""
Håndterer konvertering av observasjoner til AO CSV-format.

Brukes av ao_import_httpx.py for direkte import til Artsobservasjoner.no.
"""

from datetime import datetime


def observations_to_csv(observations):
    """
    Konverter observations array til AO CSV-format.

    Format matcher observations.js toCsv() funksjonen:
    Header + data-rader med tab-separerte verdier.
    """
    # CSV Header - VIKTIG: Må matche nøyaktig det AO forventer
    header_cols = [
        'Artsnavn',
        'Lokalitetsnavn',
        'Superlokalitet',
        'Nord',
        'Øst',
        'Nøyaktighet',
        'Fra dato',
        'Til dato',
        'Fra klokkeslett',
        'Til klokkeslett',
        'Antall',
        'Alder',
        'Kjønn',
        'Aktivitet',
        'Kommentar (synlig for alle)',
        'Privat kommentar (kun synlig for deg selv)',
        'Skjul funn til dato',
    ]

    # Legg til 10 medobservatør-kolonner
    for i in range(10):
        header_cols.append('Medobservatør')

    # Resten av kolonnene (tomme for oss, men AO forventer dem)
    extra_cols = [
        'Bestemmelsesmetode', 'Natursystem', 'Beskriv natursystem',
        'Livsmedium', 'Beskriv livsmedium', 'Art som livsmedium',
        'Beskriv art som livsmedium', 'Dybde min', 'Dybde maks',
        'Høyde min', 'Høyde maks', 'Andrehånds', 'Usikker artsbestemming',
        'Ikke spontan', 'Interessant observasjon', 'Ikke gjenfunnet',
        'Ikke funnet', 'Offentlig samling', 'Privat samling',
        'Referansenummer i samling', 'Beskrivelse artsbestemming',
        'Bestemt av', 'Bestemt av (fritekst)', 'Bestemmelsesår',
        'Bekreftet av', 'Bekreftet av (fritekst)', 'Bekreftelsesår',
    ]
    header_cols.extend(extra_cols)

    lines = ['\t'.join(header_cols)]

    # Data-rader
    for obs in observations:
        # Species kan være objekt med taxonName
        species = obs.get('species', '')
        if isinstance(species, dict):
            species_name = species.get('taxonName', '')
        else:
            species_name = str(species) if species else ''

        # Dato/tid fra timestamp (ISO format)
        date_str = ''
        time_str = ''
        if obs.get('timestamp'):
            try:
                dt = datetime.fromisoformat(obs['timestamp'].replace('Z', '+00:00'))
                # DD.MM.YYYY format
                date_str = dt.strftime('%d.%m.%Y')
                # HH:MM format (unntatt 00:00)
                if dt.hour != 0 or dt.minute != 0:
                    time_str = dt.strftime('%H:%M')
            except Exception:
                pass

        # Til-klokkeslett (valgfritt)
        time_to_str = ''
        if obs.get('tilKlokkeslett'):
            try:
                dt = datetime.fromisoformat(obs['tilKlokkeslett'].replace('Z', '+00:00'))
                time_to_str = dt.strftime('%H:%M')
            except Exception:
                pass

        # Hvis ingen til-tid, bruk fra-tid
        if not time_to_str:
            time_to_str = time_str

        # Bruk placeId (tall-ID) hvis tilgjengelig, ellers stedsnavn
        place_id = obs.get('placeId')
        place_col = str(place_id) if place_id is not None else obs.get('placeName', '')

        # Konverter hideUntil fra YYYY-MM-DD → DD.MM.YYYY
        hide_until_str = ''
        hide_until = obs.get('hideUntil', '')
        if hide_until:
            parts = hide_until.split('-')
            if len(parts) == 3:
                hide_until_str = f'{parts[2]}.{parts[1]}.{parts[0]}'

        row = [
            species_name,
            place_col,
            '',  # Superlokalitet
            '',  # Nord (lat)
            '',  # Øst (lon)
            '',  # Nøyaktighet
            date_str,
            date_str,  # Til dato = fra dato
            time_str,
            time_to_str,
            str(obs.get('count', '')),
            obs.get('age', ''),
            obs.get('gender', ''),
            obs.get('activity', ''),
            obs.get('comment', ''),
            obs.get('_photoMarker', ''),  # Privat kommentar (markør for bildematching)
            hide_until_str,
        ]

        # Medobservatører (maks 10)
        co_obs = obs.get('coObservers', [])
        for i in range(10):
            if i < len(co_obs):
                # Kan være objekt med .name eller bare string
                co = co_obs[i]
                if isinstance(co, dict):
                    row.append(co.get('name', ''))
                else:
                    row.append(str(co) if co else '')
            else:
                row.append('')

        # Ekstra kolonner (alle tomme)
        for _ in extra_cols:
            row.append('')

        lines.append('\t'.join(row))

    # VIKTIG: AO forventer \r\n line endings
    return '\r\n'.join(lines)
