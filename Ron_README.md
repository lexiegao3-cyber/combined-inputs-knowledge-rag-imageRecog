# GreenChem AI Supply Chain Operations — Ron's Pipeline

**Branch:** `Ronels-Ingestion-and-validation-pipline`

This is the **core backend processing pipeline** for the GreenChem supply chain compliance platform. It takes raw text from documents (or mock AI agent output), validates it against a Pydantic schema, runs a YAML-driven business rules engine, and persists everything to a database.

The dashboard frontend, Flask API, and live scrapers live on **`jake/frontend-design`** — see the integration guide below.

---

## Architecture Overview

```
demo_inputs/*.txt / *.pdf / *.docx / etc.
        │
        ▼
  [Ingestion Gateway]  src/ingest.py, src/ingestion_bus.py
        │  - Multi-format extraction (TXT, CSV, PDF, Excel, Word, JSON, audio)
        │  - PII redaction (SSN, bank routing, credit cards)
        │  - Deduplication via SHA-256 hash
        │  - 7 pluggable source connectors (folder, email, Federal Register, HARPEX, FX, US-China, EU trade)
        │
        ▼ (raw text string)
  [Your Coworker's AI Agent]  ← Mocked by src/agent_mock.py (3 scenarios)
        │  - Returns structured JSON (SupplyChainAnalysis schema)
        │  - Or returns malformed/incomplete JSON for retry testing
        │
        ▼ (JSON string)
  ┌─────────────────────────────────────────────────────────┐
  │  [Pydantic Validation]  src/models.py                   │
  │  - ParseAgentOutput() → SupplyChainAnalysis             │
  │  - Strips markdown fences LLMs sometimes emit           │
  │  - Returns structured error for agent retry loop        │
  └─────────────────────────────────────────────────────────┘
        │
        ▼ (validated SupplyChainAnalysis)
  ┌─────────────────────────────────────────────────────────┐
  │  [YAML-Driven Rules Engine]  src/rules.py               │
  │  - 10 declarative rules in rules_config.yaml            │
  │  - DAG-based execution (rules can depend on others)     │
  │  - Jurisdiction-aware (US, EU, UK, SEA)                 │
  │  - Confidence tiering: AUTO / SUGGEST / ESCALATE / BLOCK│
  │  - Actions: set_field, mutate_payload, block_actions,   │
  │    violation, warn, add_compliance_flag, notify         │
  └─────────────────────────────────────────────────────────┘
        │
        ▼ (mutated analysis + RuleResult)
  ┌─────────────────────────────────────────────────────────┐
  │  [Database Persistence]  src/database.py                │
  │  - SQLAlchemy ORM (SQLite MVP → PostgreSQL/Aurora later)│
  │  - Tables: analysis_runs, compliance_flags, risks,      │
  │    triggered_actions, raw_documents, pipeline_logs,     │
  │    human_overrides, document_types                      │
  └─────────────────────────────────────────────────────────┘
        │
        ▼ (PipelineResult)
  ┌─────────────────────────────────────────────────────────┐
  │  [Dashboard JSON Transform]  pipeline.to_dashboard_json()│
  │  - Formats risks, actions, compliance flags for frontend │
  │  - Matches Jake's riskActionsData.js format              │
  └─────────────────────────────────────────────────────────┘
```

---

## Quick Start

```bash
pip install -r requirements.txt
python -m src
```

This runs the quick demo with mock data (a $145k tariff risk → Rule 1 triggers → priority escalated to Critical).

### Other entry points

```bash
python -m src --rules-demo     # Show all 10 YAML rules applied against mock data
python -m src --bus            # Run the ingestion bus (folder connector)
python -m src --health         # Check connector health
python -m tests.test_pipeline  # Run the 3 mock-agent scenarios
```

---

## What's on this branch

### `src/` — Core Pipeline

| File | Purpose |
|------|---------|
| `__main__.py` | Entry point: `python -m src` with `--bus`, `--rules-demo`, `--health` flags |
| `models.py` | Pydantic v2 models: `SupplyChainAnalysis`, `Risk`, `Action`, `ComplianceItem`, etc. |
| `pipeline.py` | Orchestrator: validate → rules → database → dashboard JSON |
| `rules.py` | Data-driven rules engine — loads rules from `rules_config.yaml` |
| `database.py` | SQLAlchemy ORM with 8 tables, session factory, DB init |
| `agent_mock.py` | Mock AI agent returning 3 test scenarios |
| `ingest.py` | Multi-format ingestion gateway with PII redaction |
| `ingestion_bus.py` | Polling bus: connectors → raw doc storage → pipeline |

### `src/connectors/` — Pluggable Source Connectors

| Connector | Type | Description |
|-----------|------|-------------|
| `folder.py` | Static | Reads files from a local directory |
| `email.py` | Static | IMAP mailbox connector |
| `federal_register.py` | Live | Federal Register API for tariff notices |
| `shipping_rates.py` | Live | HARPEX shipping charter index |
| `exchange_rates.py` | Live | open.er-api.com USD/CNY, USD/EUR |
| `us_china_lane.py` | Live | US–China trade lane metrics |
| `eu_trade_lane.py` | Live | EU–US trade lane metrics |

### `rules_config.yaml` — 10 Business Rules

| # | Rule | Trigger | Action |
|---|------|---------|--------|
| 1 | Financial Risk Escalation | risk cost > $100k | Escalate to Critical priority |
| 2 | Low Confidence Gate | confidence < 0.60 | Block all actions, escalate to human |
| 3 | Target System Validation | invalid target_system | Hard violation |
| 4 | US Section 301 Tariff | US_CBP + TARIFF_CLASSIFICATION | Flag for urgent review, notify Slack |
| 5 | EU REACH Chemical Check | CHEMICALS SKU + EU port | Add REACH compliance flag |
| 6 | Combined Risk Score | HIGH probability + cost > $50k | Escalate to human |
| 7 | Missing COO Certificate | COUNTRY_OF_ORIGIN + MISSING | Set severity HIGH, notify logistics |
| 8 | Port Congestion Delay | DELAY category + HIGH probability | Add delay warning flag |
| 9 | Non-English Document | language != "en" | Add bilingual review flag |
| 10 | Expedited Shipment | delivery within 72h | Add expedited processing flag |

### `demo_inputs/` — Test Files

| File | Description |
|------|-------------|
| `scenario_a_tariff_spike.txt` | Raw email/PDF text simulating a tariff emergency |
| `cenario_c_perfect_agent_output.txt` | Pre-structured JSON simulating perfect AI agent output |

### `tests/` — Test Suite

| File | Description |
|------|-------------|
| `test_pipeline.py` | Runs all 3 mock scenarios through validation + rules engine |

---

## How Jake's Branch Connects to This

Jake's **`jake/frontend-design`** branch has the Flask web server, frontend dashboard, and live scrapers. Here's how the two systems relate:

### Jake's architecture (on `jake/frontend-design`)

```
scrapers/ (Python)            → data/processed/*.json
Flask app.py                  → GET /api/metrics, /api/results, /api/health
frontend/ (vanilla JS)        → Calls Flask API, renders dark-glass UI
data/demo/greenchem/          → Canned demo datasets for screenshots
```

### Integration points

| This branch (Ron's pipeline) | Jake's branch |
|------------------------------|---------------|
| `src/models.py` — SupplyChainAnalysis schema | `data/demo/greenchem/dashboard.json` — risk/action format |
| `pipeline.to_dashboard_json()` — transforms pipeline output | `frontend/js/sections/riskActionsData.js` — expected risk/action format |
| `src/rules.py` — YAML rules engine | `frontend/js/sections/risks.js` — renders risk cards |
| `src/ingestion_bus.py` — connector framework | `backend/scrapers/` — individual scrapers |

### What Jake should know about this pipeline

1. **No Flask server here** — This branch is a CLI pipeline. Jake's `backend/app.py` serves the API.
2. **No frontend here** — Jake's `frontend/` has the full dark-glass UI.
3. **The pipeline can generate dashboard JSON** — Call `run_pipeline()` then `result.to_dashboard_json()` to get data matching the frontend's `riskActionsData.js` format.
4. **Connector framework vs scrapers** — The `src/connectors/` classes follow a `poll()` → `acknowledge()` contract. Jake's `backend/scrapers/` are standalone scripts that write JSON files. Both approaches work; they serve different use cases.
5. **Rules engine is reusable** — If Jake wants AI-generated recommendations to pass through business rules, the `src/rules.py` `run_rules()` function can be imported into the Flask app.

### Deployment notes

- **Database:** SQLite for MVP (`supply_chain_mvp.db`). Set `DATABASE_URL` env var for PostgreSQL/Aurora.
- **Scaling:** The pipeline is stateless (except the DB). Can be deployed as a Lambda or ECS task.
- **Dependencies:** `pip install -r requirements.txt` (pydantic, sqlalchemy, pyyaml, requests).

---

## Full File Listing

```
Summer26-Magnus/
├── Ron_README.md                        # This file
├── requirements.txt                     # Python deps
├── rules_config.yaml                    # 10 YAML business rules
├── src/
│   ├── __init__.py
│   ├── __main__.py                      # Entry: python -m src
│   ├── agent_mock.py                    # 3 test scenarios
│   ├── database.py                      # SQLAlchemy ORM (8 tables)
│   ├── ingest.py                        # Multi-format ingestion + PII
│   ├── ingestion_bus.py                 # Connector polling bus
│   ├── models.py                        # Pydantic v2 schemas
│   ├── pipeline.py                      # Validation → Rules → DB → Dashboard JSON
│   ├── rules.py                         # YAML-driven rules engine
│   └── connectors/
│       ├── __init__.py                  # Registry + live connector configs
│       ├── base.py                      # SourceConnector ABC
│       ├── email.py                     # IMAP email connector
│       ├── eu_trade_lane.py             # EU-US trade metrics
│       ├── exchange_rates.py            # open.er-api.com FX
│       ├── federal_register.py          # Federal Register API
│       ├── folder.py                    # Local folder connector
│       ├── shipping_rates.py            # HARPEX index
│       └── us_china_lane.py             # US-China trade lane
├── demo_inputs/
│   ├── scenario_a_tariff_spike.txt      # Raw email/PDF text
│   └── cenario_c_perfect_agent_output.txt # Pre-structured JSON
├── scripts/
│   ├── __init__.py
│   └── generate_demo_pdf.py             # Generate test PDFs
└── tests/
    ├── __init__.py
    └── test_pipeline.py                 # 3 mock scenarios
```

### Jake's branch has (for reference)

```
Summer26-Magnus/
├── README.md                            # GreenChem dashboard README
├── AGENTS.md                            # Agent/Composer rules
├── handoff.md                           # Session state
├── backend/
│   ├── app.py                           # Flask API server
│   ├── config.py                        # Configuration
│   ├── requirements.txt                 # Flask deps
│   └── scrapers/                        # Live data scrapers
│       ├── tariff_scraper.py            # Federal Register
│       ├── shipping_rates_scraper.py    # HARPEX
│       ├── exchange_rates_scraper.py    # FX
│       ├── us_china_routes.py           # US-China lane
│       └── us_europe_routes.py          # EU-US lane
├── frontend/
│   ├── index.html                       # App shell
│   ├── style.css / css/                # Dark-glass theme
│   └── js/
│       ├── api.js                       # Fetch wrapper
│       ├── main.js                      # App init
│       ├── components.js                # Card/tile factories
│       └── sections/                    # Dashboard panels
├── data/
│   ├── processed/                       # Live scraper output
│   ├── sample_outputs/                  # Bundled fallback data
│   └── demo/greenchem/                  # Canned demo dataset
├── notes/                               # Plans and docs
└── research/                            # Data source notes
```

---

## Git Workflow

```bash
# Ron works on this branch:
git checkout Ronels-Ingestion-and-validation-pipline
git add src/ tests/ rules_config.yaml requirements.txt
git commit -m "Describe what changed"
git push origin Ronels-Ingestion-and-validation-pipline

# Jake works on:
git checkout jake/frontend-design
git push origin jake/frontend-design

# Merge when ready:
# PR from Ronels-Ingestion-and-validation-pipline → main
# PR from jake/frontend-design → main