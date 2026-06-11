# How to Get Live Data Running in the Ingestion Pipeline

**Branch:** `Ronels-Ingestion-and-validation-pipline`

---

## The Two Paths to Live Data

There are **two separate approaches** in this repo. Here's what each does and how to run them.

---

## Path 1: Run the `IngestionBus` with live connectors (this branch)

Your `src/connectors/*.py` files implement the `SourceConnector` ABC. They poll live APIs and return `RawDocument` objects (raw bytes + metadata). The `IngestionBus` processes them through the pipeline.

### Which connectors are live vs simulated?

| Connector | File | Live API | Default Mode | Needs |
|-----------|------|----------|--------------|-------|
| Federal Register | `federal_register.py` | `https://www.federalregister.gov/api/v1/` | **LIVE** (no simulate flag) | Nothing — free API |
| Exchange Rates | `exchange_rates.py` | `https://open.er-api.com/v6/latest/USD` | **LIVE** (`simulate: False`) | Nothing — free API |
| HARPEX Shipping | `shipping_rates.py` | `https://www.harpex.com/` | `simulate: True` | HTML scraping — fragile |
| US-China Lane | `us_china_lane.py` | Port of LA + Census | `simulate: True` | `CENSUS_API_KEY` env var for Census |
| EU Trade Lane | `eu_trade_lane.py` | Rotterdam + Eurostat | `simulate: True` | Nothing — free APIs |
| Folder | `folder.py` | Local filesystem | Always live | Files in `./demo_inputs/` |
| Email | `email.py` | IMAP mailbox | Manual setup | IMAP credentials |

### How to run the bus with live data

```bash
# 1. First activate your venv and install deps
cd /Users/ronel/Downloads/Summer26-Magnus
pip install -r requirements.txt

# 2. Run the ingestion bus with default configs (folder connector only)
python -m src --bus
# This scans ./demo_inputs/, processes files, runs pipeline, saves to DB

# 3. Run with live connectors (from __init__.py defaults)
python -c "
from src.ingestion_bus import IngestionBus
from src.connectors import LIVE_CONNECTOR_CONFIGS
from src.database import init_db

init_db()
bus = IngestionBus(LIVE_CONNECTOR_CONFIGS)
# Add folder connector too
bus.connectors['folder'] = __import__('src.connectors.folder', fromlist=['FolderConnector']).FolderConnector({'path': './demo_inputs'})

results = bus.poll_all()
print(bus.report())
"
```

### The catch: pipeline expects AI agent output

When the bus calls `run_pipeline(raw_text)`, it passes the raw text to **Pydantic validation** (`src/models.parse_agent_output()`), which expects a JSON string matching the `SupplyChainAnalysis` schema:

```json
{
  "system_status": {...},
  "source_info": {...},
  "ai_analysis": {...},
  "compliance_items": [...],
  "risks": [...],
  "actions": [...]
}
```

The live connectors return **raw data** (exchange rates, tariff notices), not structured analysis with risks/actions. So `run_pipeline()` will **fail validation** on live connector data unless you add an AI agent in between.

**To make live data flow through your pipeline end-to-end, you need one of:**

1. **The real AI agent** (your coworker's LangGraph agent) — connectors feed raw text → agent produces `SupplyChainAnalysis` JSON → `run_pipeline()` validates/rules/stores
2. **A transformer function** that converts connector output into the expected schema (you write a mapping from, say, exchange rate data → a simple `SupplyChainAnalysis` with one risk item)

---

## Path 2: Run Jake's scrapers + Flask API (on `jake/frontend-design`)

Jake's approach bypasses your pipeline entirely. His scrapers fetch live data, transform it into simple JSON records, and serve them via Flask.

### What's on Jake's branch

```
backend/scrapers/
├── tariff_scraper.py          # Federal Register API → tariff news + metrics
├── shipping_rates_scraper.py  # HARPEX website → weekly index
├── exchange_rates_scraper.py  # open.er-api.com → FX rates
├── us_china_routes.py         # POLA + Census → US-China lane data
└── us_europe_routes.py        # Rotterdam + Eurostat → EU-US lane data
```

All scrapers follow the same pattern:
1. Fetch from live API
2. Transform into `{title, source_link, date_scraped, summary, category}` records
3. Save to `data/processed/<category>.json`
4. `metrics()` function returns stat tiles
5. On failure → fall back to sample data from `data/sample_outputs/`

### How to run Jake's scrapers

```bash
# Switch to Jake's branch
git checkout jake/frontend-design

# Install backend deps (has Flask + requests)
cd backend
pip install -r requirements.txt

# Run individual scrapers
python -m scrapers.tariff_scraper       # Tariff news
python -m scrapers.shipping_rates_scraper   # HARPEX
python -m scrapers.exchange_rates_scraper   # FX
python -m scrapers.us_china_routes       # US-China
python -m scrapers.us_europe_routes      # EU-US

# Or run all scrapers at once
python -m scrapers

# Start the Flask server
python app.py
# Open http://localhost:5000
```

### Scrapers that are live vs simulated (Jake's branch)

| Scraper | API | Status | Fallback |
|---------|-----|--------|----------|
| `tariff_scraper.py` | Federal Register API | **LIVE** — no API key needed | Sample data |
| `exchange_rates_scraper.py` | open.er-api.com | **LIVE** — no API key needed | Sample data |
| `shipping_rates_scraper.py` | harpex.com HTML | **LIVE** — scrapes HTML | Sample data |
| `us_china_routes.py` | POLA website + Census | Partial (POLA HTML may work; Census needs `CENSUS_API_KEY`) | Simulated signals |
| `us_europe_routes.py` | Rotterdam + Eurostat API | **LIVE** — Eurostat API works | Simulated signals |

---

## Recommended: Run Both Paths Together

The best setup for development:

```bash
# Terminal 1: Jake's scrapers + Flask (on jake/frontend-design)
cd /Users/ronel/Downloads/Summer26-Magnus
git checkout jake/frontend-design
cd backend
python app.py  # Scrapers run on demand via sidebar "Refresh data"
# Open http://localhost:5000 → see live dashboard
```

```bash
# Terminal 2: Your pipeline with mock data (on Ronels-Ingestion-and-validation-pipline)
cd /Users/ronel/Downloads/Summer26-Magnus
git checkout Ronels-Ingestion-and-validation-pipline
python -m src --rules-demo  # Test rules engine
python -m tests.test_pipeline  # Run test scenarios
```

Then when you want to merge the two:
1. **PR your branch → `main`** so your `src/` code is available to Jake
2. **Add a Flask route to `backend/app.py`** that imports your pipeline:
   ```python
   from src.pipeline import run_pipeline
   
   @app.route('/api/analyze', methods=['POST'])
   def analyze():
       data = request.get_json()
       result = run_pipeline(data.get('text', ''))
       return jsonify(result.to_dashboard_json())
   ```
3. **Point the frontend's AI risk report** at this new endpoint instead of static demo data

---

## Quick Test: Is Your Connector Actually Hitting a Live API?

```bash
cd /Users/ronel/Downloads/Summer26-Magnus

# Test Exchange Rates (should work, no API key needed)
python -c "
import requests
r = requests.get('https://open.er-api.com/v6/latest/USD', timeout=10)
print('Status:', r.status_code)
print('Rates:', r.json().get('rates', {}).get('CNY'))
"

# Test Federal Register (should work, no API key needed)
python -c "
import requests
r = requests.get('https://www.federalregister.gov/api/v1/documents.json?conditions[term]=tariff&per_page=3', timeout=10)
print('Status:', r.status_code)
print('Results:', len(r.json().get('results', [])))
"