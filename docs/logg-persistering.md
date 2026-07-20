# Persistente logger

## Problem
Docker `json-file`-loggdriveren lagrer logg per container-ID under
`/var/lib/docker/containers/<id>/`. Ved deploy (`docker compose build --no-cache`
+ `up -d`) opprettes en **ny container**, og den gamle loggen blir foreldreløs og
forsvinner. Dozzle viser bare live docker-logg, så historikken ryker ved hver
restart/rebuild.

## Løsning
Applikasjonsloggen (`fugleobs`-loggeren) skrives i tillegg til en **roterende fil**
på det varige `/data`-volumet (`ao-data`), som overlever container-rebuild.

- Styres av miljøvariabelen `LOG_DIR`.
- På Pi: `LOG_DIR=/data/logs` (satt i `docker-compose.pi.yml`).
- Fil: `/data/logs/fugleobs.log`, roterer ved 10 MB, beholder 5 gamle filer (~60 MB totalt).
- **Uten `LOG_DIR`** (lokal utvikling) logges kun til konsoll — ingen atferdsendring.
- Konsoll-logging beholdes alltid, så Dozzle fungerer som før for live-visning.

Implementert i `server.py` (logging-oppsett øverst) med `RotatingFileHandler`.

## Lese loggen på Pi
```bash
# Live + historikk fra fila
ssh kjetil@<pi> "cat ~/enkel-ao_data/logs/fugleobs.log"   # via volumet
# eller inne i containeren:
docker compose -f docker-compose.pi.yml exec enkel-ao cat /data/logs/fugleobs.log
```

Volumet `ao-data` ligger på Pi under Docker sin volume-sti
(`/var/lib/docker/volumes/enkel-ao_ao-data/_data/logs/` med mindre annet er konfigurert).
