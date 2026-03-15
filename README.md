# Preisvergleich

Persönlicher Supermarkt-Preisvergleich. Läuft lokal auf dem Raspberry Pi.

## Schnellstart

```bash
# Auf dem Pi ausführen:
git clone / scp die Dateien nach ~/docker/preisvergleich
cd ~/docker/preisvergleich
docker compose up -d
```

Dann im Browser: `http://<pi-ip>:8012`

## Cloudflare Tunnel

In deiner `config.yml` (lokale Tunnel-Config) einen Eintrag hinzufügen:

```yaml
- hostname: preise.deine-domain.de
  service: http://localhost:8012
```

## Lokale Entwicklung (ohne Docker)

```bash
pip install -r requirements.txt
uvicorn main:app --reload
# → http://localhost:8000
```

## Datei-Struktur

```
preisvergleich/
├── main.py            # FastAPI Backend + API-Routen
├── templates/
│   └── index.html     # Komplettes Frontend (1 Datei)
├── data/
│   └── prices.db      # SQLite DB (auto-erstellt)
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## API-Endpunkte (für spätere Erweiterungen)

| Method | URL | Beschreibung |
|--------|-----|--------------|
| GET | /api/products | Alle Produkte |
| POST | /api/products | Neues Produkt |
| DELETE | /api/products/{id} | Produkt löschen |
| GET | /api/stores | Alle Märkte |
| POST | /api/stores | Neuer Markt |
| DELETE | /api/stores/{id} | Markt löschen |
| POST | /api/prices | Preis eintragen |
| DELETE | /api/prices/{id} | Preiseintrag löschen |
| GET | /api/compare?product_ids=1,2 | Vergleichstabelle |
| GET | /api/history/{product_id} | Preisverlauf |
