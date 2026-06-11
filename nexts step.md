# What's Next for You (Ron)

Here's your priority-ordered action list:

## 🔴 High Priority (MVP blockers)

### 1. Integrate your pipeline into Jake's Flask API
Jake's `backend/app.py` serves static JSON from `data/processed/` and `data/demo/`. Your pipeline (`src/pipeline.py`, `src/rules.py`, `src/models.py`) can replace or augment those static files with **live validated + rules-processed data**.

The simplest path: add a Flask route to Jake's `app.py` that calls your pipeline. Something like:
```python
# In backend/app.py (on jake/frontend-design branch)
from src.pipeline import run_pipeline, init_db

@app.route('/api/analyze', methods=['POST'])
def analyze():
    raw_text = request.json.get('text', '')
    result = run_pipeline(raw_text)
    return jsonify(result.to_dashboard_json())
```

But first you need to **merge the repos** — your `src/` code is not on `jake/frontend-design` or `main`. Options:
- **Option A:** Open a PR from `Ronels-Ingestion-and-validation-pipline` → `main`, then Jake merges `main` into his branch
- **Option B:** Cherry-pick your `src/` files onto `jake/frontend-design` so Jake can import them directly

### 2. Real AI agent integration
Your pipeline currently runs on mock data from `src/agent_mock.py` or raw text from `demo_inputs/`. The next step is hooking into the real AI agent your coworker is building so `run_pipeline()` receives actual AI analysis JSON instead of mock strings.

### 3. `/api/recommendations` endpoint
The frontend has a placeholder section awaiting `GET /api/recommendations`. Your pipeline already generates risks, actions, and compliance flags — wire this up to serve real data.

---

## 🟡 Medium Priority (near-term)

### 4. Replace scraper seed numbers
Jake's `notes/next_steps.md` flags that scrapers use placeholder seed values instead of real numbers. Help Jake identify the real baseline metrics.

### 5. Add error handling for scraper failures
When a live data source changes its HTML format, the scrapers break silently. Your connector framework (`src/connectors/`) has better error handling patterns that could inform Jake's scrapers.

### 6. Decide on refresh cadence
Manual "Refresh data" button (Jake already built) vs scheduled cron/CloudWatch event. For AWS later, a scheduled Lambda calling `POST /api/scrape` is the standard pattern.

---

## 🟢 Nice-to-Haves (later)

### 7. Dashboard placeholder sections
These are all marked Placeholder in the task spec — wire them up when business value justifies it:
- **Executive summary** — KPI tiles from your pipeline's `to_dashboard_json()['summary']`
- **ROI / impact** — Financial impact computed from risk costs vs action costs
- **Compliance center** — Filter/search through `compliance_flags` from your pipeline
- **Agent activity** — Log of AI agent calls, retry counts, success rates
- **System health** — Connector health from `src/ingestion_bus.check_health()`

### 8. Deduplication & sorting
Your pipeline already has SHA-256 dedup in `src/ingest.py`. Jake's frontend needs "newest first" sorting added to news/results display.

---

## TL;DR — Your actual next step

**Open a PR from your branch to `main`, then coordinate with Jake to merge `main` into `jake/frontend-design`.** That puts your pipeline code where Jake can import it. After that, the integration work (step 1 above) is a single Flask route.