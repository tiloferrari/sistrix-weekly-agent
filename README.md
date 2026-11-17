# Sistrix Weekly Agent – SEO-Wettbewerbsanalyse (Deutsche Interim AG)

Agent, der sich wöchentlich mit **Sistrix** verbindet und einen **PDF-Bericht** erstellt, in dem
gezeigt wird, bei welchen Keywords die **Deutsche Interim AG** (`www.deutscheinterim.com`) im
Google-Ranking (Land: `de`) gegen wichtige Wettbewerber aus der Interim-/Personal-Branche verliert.

## Was der Agent jede Woche macht

1. **Top-3-Wettbewerber finden**: Kandidaten kommen aus der Sistrix-Wettbewerberliste
   (`domain` → `competitors`). Gefiltert wird auf Branchenrelevanz (Interim-Provider,
   Personalberatungen, Personalvermittler; Jobportale/Enzyklopädien werden ausgeschlossen).
   Die gefährlichsten 3 werden per Score ausgewählt (verlorene Keywords × Positionsgewicht,
   Keyword-Überschneidung, Sichtbarkeitsindex-Verhältnis).
2. **Kurzbericht pro Wettbewerber**: Geschäftsmodell (aus den eigenen Top-Keywords des
   Wettbewerbers), Sichtbarkeitsindex, Top-10-Keyword-Anzahl, Überschneidung mit uns –
   plus Begründung, warum der Wettbewerber SEO-gefährlich ist.
3. **Keyword-Wettbewerbsanalyse** (Sistrix-Connector, `keyword_domain_seo`): Für uns und jeden
   Wettbewerber werden die organischen Rankings bis Top 100 gezogen (bei Wettbewerbern auf die
   Branchen-Keywords gefiltert). „Verloren“ = Wettbewerber rankt besser als wir (oder wir ranken
   für ein Top-10-Keyword des Wettbewerbers gar nicht in den Top 100).
4. **Top-5-Keywords pro Wettbewerber** zur Content-Optimierung (Score = Positionsdifferenz ×
   Gewicht der Wettbewerber-Position: Top 3 = 1.0, Top 10 = 0.6, Top 20 = 0.3, sonst 0.15).

Der Bericht wird als PDF erzeugt (Titel, Ausgangslage, Wettbewerbs-Überblick, Methodik,
pro Wettbewerber Profil + Begründung + Top-5-Tabelle mit URLs).

## Aufbau

```
sistrix_agent/
  config.py     Konfiguration (Domain, Land, Schwellen, Branchen-Filter) – per Env überschreibbar
  client.py     SistrixClient-Protokoll + Connector-Client (Studio), REST-Client, Static-Client (Replay)
  analysis.py   Reine Analyse-Logik (Wettbewerber-Wahl, verlorene Keywords, Top-5)
  report.py     PDF-Bericht (reportlab, Deutsch)
  agent.py      Orchestrierung: Profile sammeln → analysieren
  __main__.py   CLI
apps/worker/src/worker/workflows/
  sistrix_weekly.py            Mistral Workflow (Connector `sistrix_e5d7`), Worker für AI Studio
apps/worker/                   Worker-Projekt (pyproject + uv.lock)
deploy/docker/Dockerfile.worker  Dockerfile für das Managed Deployment (Build-Kontext: Repo-Root)
data/
  live_capture.json            aufgezeichnete Live-Abfrage vom 16.11.2026 (Replay/Test)
tests/                         pytest-Suite
reports/                       erzeugte PDFs
```

## Nutzung

### Lokal / Replay (ohne API-Key)

```bash
pip install -r requirements.txt
python -m sistrix_agent --client static --data data/live_capture.json --output reports/bericht.pdf
```

### Lokal gegen die Sistrix-API direkt

```bash
export SISTRIX_API_KEY=...   # nie im Code/Repo einchecken
python -m sistrix_agent --client rest --output reports/bericht.pdf
```

### In Mistral AI Studio (empfohlen, „Sistrix Connector“)

Der Workflow in `apps/worker/src/worker/workflows/sistrix_weekly.py` deklariert den Connector
`sistrix_e5d7` (`connector("sistrix_e5d7")` + `@uses_connectors`) und ruft die Tools `domain` und
`keyword_domain_seo` darüber auf. Managed Deployment aus diesem Repo (Build-Kontext: Repo-Root,
Dockerfile: `deploy/docker/Dockerfile.worker`), dann:

**Wöchentlicher Zeitplan** (z. B. montags 08:00 Europe/Berlin = `0 7 * * 1` UTC im Winter):

```python
from mistralai.client import Mistral, models

client = Mistral()
client.workflows.schedules.schedule_workflow(
    workflow_identifier="sistrix-weekly-seo-report",
    deployment_name="production",
    schedule=models.ScheduleDefinition(
        input={"own_domain": "deutscheinterim.com", "country": "de"},
        cron_expressions=["0 7 * * 1"],
        time_zone_name="Europe/Berlin",
        policy=models.SchedulePolicy(overlap=models.ScheduleOverlapPolicy.SKIP),
    ),
)
```

oder per MCP: `mistral_mcp_create_workflow_schedule` mit `workflow_name="sistrix-weekly-seo-report"`.

Der Lauf lädt den PDF-Bericht zusätzlich als Mistral-Datei hoch (`pdf_file_id` im Ergebnis).

> **Wichtig für geplante Läufe:** Ein Schedule läuft als Deployment-Service-Account und kann
> nur **Workspace-/Organisations-Credentials** des Connectors nutzen. Der Sistrix-Connector
> hat aktuell nur ein User-Credential (`default`). Für den unattended Wochenlauf bitte in
> Studio ein Workspace-Credential für `sistrix_e5d7` hinterlegen (oder alternativ den
> Sistrix-API-Key als Workspace-Secret `SISTRIX_API_KEY` binden und den REST-Client nutzen).

### Alternativ: Cron auf eigenem Server

```cron
0 8 * * 1  cd /pfad/zum/sistrix-weekly-agent && SISTRIX_API_KEY=... python -m sistrix_agent --client rest --output reports/$(date +\%F)-bericht.pdf
```

## Tests

```bash
python -m pytest tests/ -q
```

## Konfiguration (Env-Variablen)

| Variable | Default | Bedeutung |
|---|---|---|
| `SISTRIX_OWN_DOMAIN` | `deutscheinterim.com` | eigene Domain |
| `SISTRIX_COMPANY_NAME` | `Deutsche Interim AG` | Anzeigename im Bericht |
| `SISTRIX_COUNTRY` | `de` | Sistrix-Land |
| `SISTRIX_TOP_COMPETITORS` | `3` | Anzahl Wettbewerber im Bericht |
| `SISTRIX_KEYWORDS_PER_COMPETITOR` | `5` | Top-Keywords pro Wettbewerber |
| `SISTRIX_MAX_POS` | `100` | bis zu welcher Position Keywords verglichen werden |
| `SISTRIX_API_KEY` | – | nur für `--client rest` nötig |

## Ergebnis des Probelaufs (16.11.2026)

 siehe `reports/` – Top-3-Wettbewerber laut Live-Daten: `interim-profis.com`, `interim-x.com`,
 `interim-aid.de` (je mit Top-5-Keywords, bei denen wir schlechter ranken).
