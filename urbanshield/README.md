# UrbanShield
### AI-Powered Geospatial Infrastructure Risk & Predictive Maintenance Platform

An end-to-end geospatial analytics platform that identifies infrastructure risk
hotspots (roads, bridges, water pipelines, power poles, storm drains) and
prioritizes maintenance — combining spatial data processing, machine learning,
PostGIS, interactive mapping, explainable ML, and a natural-language AI
assistant for infrastructure investigation.

---

## Quick Start (5 minutes)

### 1. Prerequisites
- Python 3.9+
- PostgreSQL 13+ (for Docker) or optional for local development
- Anthropic API key for AI assistant features

### 2. Local Development Setup

```bash
# Clone/navigate to the project
cd urbanshield

# Create virtual environment
python -m venv .venv

# Activate it
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment variables
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# Run the complete pipeline (generate → train → serve)
python run.py

# Open your browser to:
# - Dashboard: http://localhost:8000/
# - API Docs: http://localhost:8000/docs
```

### 3. Docker Deployment

```bash
# Build and start all services (DB + API + Dashboard + AI Assistant)
# PowerShell: these ports avoid a conflict if another app already uses 8000.
$env:API_PORT='8010'
$env:FRONTEND_PORT='8080'
$env:ASSISTANT_PORT='8001'
docker compose up --build -d

# Services will be available at:
# - Unified dashboard: http://localhost:8080
# - API Docs: http://localhost:8080/api/docs
# - Assistant: embedded in the dashboard (Ask AI)
# - Direct API: http://localhost:8010
# - PostgreSQL: localhost:5432
```

---

## Architecture

```
                    ┌──────────────────┐
                    │  Data Sources     │  OpenStreetMap, city open data,
                    │  (data/)          │  sensor feeds, synthetic generator
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  PostGIS          │  Spatial storage + indexing
                    │  (db/schema.sql)  │  ST_DWithin, ST_ClusterDBSCAN
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  ML Risk Model    │  GradientBoosting + explainability
                    │  (ml/)            │  (SHAP or built-in fallback explainer)
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  FastAPI Backend  │  /assets /nearby /hotspots
                    │  (backend/)       │  /maintenance-priority /explain
                    └────┬─────────┬────┘
                         │         │
              ┌──────────▼──┐   ┌──▼─────────────────┐
              │  Map UI      │   │  AI Assistant Agent │
              │  (frontend/) │   │  (ai_assistant/)     │
              │  Leaflet     │   │  LangChain tool-use   │
              └──────────────┘   └──────────────────────┘
```

## Implementation Status

| Layer | Tech | Status | File |
|-------|------|--------|------|
| **Data generation** | Synthetic street-grid network + Munneru river polyline | ✅ Complete | `data/generate_synthetic_data.py` |
| **Spatial storage** | PostGIS schema with indexes, waterways, `ST_Distance`/`ST_DWithin` | ✅ Complete | `db/schema.sql` |
| **Risk model** | Gradient Boosted Trees, ROC-AUC **0.89**, explainability | ✅ Complete | `ml/train_risk_model.py` |
| **Explainability** | Per-asset feature attribution (top 3 risk drivers via SHAP-like explainer) | ✅ Complete | `ml/` |
| **FastAPI Backend** | Scoring, filtering, radius search, hotspots, maintenance ranking, river layer | ✅ Complete | `backend/main.py` |
| **Interactive Map** | Leaflet-based dashboard with risk markers, filters, stats | ✅ Complete | `frontend/index.html` |
| **AI Assistant** | LangChain agent with tool-calling, grounded in live API calls | ✅ Complete | `ai_assistant/agent.py` |
| **Configuration** | .env support, environment variables, portable paths | ✅ Complete | `.env`, `backend/config.py` |
| **Orchestration** | Data pipeline script with logging and error handling | ✅ Complete | `run.py` |
| **Docker Compose** | Full stack containerization with volumes and health checks | ✅ Complete | `docker-compose.yml` |
| **PostGIS Integration** | Optional: swap CSV for PostGIS queries (initial: CSV-based) | 🟡 Partial | Comments in backend code |

---

## File Structure

```
urbanshield/
├── data/                          # Data generation
│   └── generate_synthetic_data.py  # Creates 2,500+ assets, river geometry
├── db/                            # Database & data files
│   ├── schema.sql                 # PostGIS schema definition
│   ├── assets.csv                 # Generated raw asset data
│   ├── assets_scored.csv          # Scored assets with risk levels
│   ├── incidents.csv              # Historical incident log
│   └── river.json                 # River polyline + street grid (map layer)
├── ml/                            # Machine learning
│   ├── train_risk_model.py        # GradientBoosting + explainability
│   ├── model.joblib               # Trained model artifact
│   └── feature_importance.png     # Global feature importance chart
├── backend/                        # FastAPI backend
│   ├── main.py                    # API routes & data serving
│   ├── config.py                  # Configuration from .env
│   ├── requirements.txt           # Backend dependencies
│   └── Dockerfile                 # Container image
├── frontend/                       # Web dashboard
│   └── index.html                 # Leaflet-based interactive map
├── ai_assistant/                  # LangChain agent
│   └── agent.py                   # Tool-calling infrastructure agent
├── run.py                         # Orchestration: generate → train → serve
├── docker-compose.yml             # Full stack definition (DB, API, frontend)
├── nginx.conf                     # Frontend reverse proxy config
├── .env.example                   # Configuration template
├── .gitignore                     # Git exclusions
└── README.md                      # This file
```

---

## Usage

### Option 1: Run the Complete Pipeline (Recommended for Development)

```bash
# Activate your virtual environment first
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Run everything: generate data → train model → start API
python run.py

# For detailed help:
python run.py --help
```

### Option 2: Run Steps Individually

```bash
# 1. Generate synthetic data
cd data && python generate_synthetic_data.py && cd ..

# 2. Train the risk model
cd ml && python train_risk_model.py && cd ..

# 3. Start the API
cd backend && uvicorn main:app --reload --port 8000 && cd ..
```

### Option 3: Docker Deployment

```bash
# All-in-one: database, API, and frontend in containers
docker-compose up --build

# View logs
docker-compose logs -f backend

# Stop services
docker-compose down

# Clean up (remove data volumes)
docker-compose down -v
```

---

## Environment Configuration

Create a `.env` file (copy from `.env.example`) to configure:

```bash
# API Settings
API_HOST=0.0.0.0
API_PORT=8000
FRONTEND_API_BASE=http://localhost:8000

# AI Assistant
ANTHROPIC_API_KEY=sk-ant-...

# Database (for PostGIS)
DB_USER=urbanshield
DB_PASSWORD=urbanshield_dev
DB_HOST=localhost
DB_PORT=5432
DB_NAME=urbanshield_db

# Logging
LOG_LEVEL=INFO
LOG_FILE=./logs/urbanshield.log
```

---

## API Endpoints

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Interactive risk dashboard |
| `/health` | GET | Service status and asset count |
| `/config` | GET | Frontend configuration (API base URL) |
| `/assets` | GET | List all assets (paginated, filterable) |
| `/assets/{asset_id}` | GET | Full detail for one asset |
| `/assets/{asset_id}/explain` | GET | Risk explanation for one asset |
| `/nearby?lat=X&lon=Y&radius_m=500` | GET | Assets within radius |
| `/hotspots` | GET | High-risk cluster zones |
| `/maintenance-priority` | GET | Top N assets for maintenance crews |
| `/stats` | GET | Dashboard summary stats |
| `/river-layer` | GET | River polyline + street grid (map layer) |

### API Documentation

Full interactive documentation available at:
- **Local**: http://localhost:8000/docs
- **Docker**: http://localhost:8000/docs

### Example Requests

```bash
# List top 10 critical assets
curl "http://localhost:8000/assets?risk_tier=critical&limit=10"

# Find assets near a location (500m radius)
curl "http://localhost:8000/nearby?lat=17.25&lon=80.15&radius_m=500"

# Get explanation for asset
curl "http://localhost:8000/assets/ASSET_001/explain"

# Get dashboard stats
curl "http://localhost:8000/stats"
```

---

## Frontend Usage

### Opening the Dashboard

**Local Development:**
```
http://localhost:8000
```

**Docker Deployment:**
```
http://localhost:8080
```

### Features

- **Interactive Map**: Click on risk markers to see asset details
- **Filters**: Filter by asset type and risk tier
- **Statistics**: Real-time dashboard header with aggregate stats
- **Hotspots**: Visual clustering of high-risk zones
- **Details Panel**: Expanded view of top-risk assets with explanations

### Configuring API Base URL

The frontend automatically detects the API URL from:
1. URL parameter: `?api_base=http://...`
2. Window global: `window.URBANSHIELD_API_BASE`
3. localStorage: Previously saved URL
4. Default: `http://localhost:8000`

Example:
```
http://localhost:8080?api_base=http://api.example.com:8000
```

---

## AI Assistant

The LangChain agent (`ai_assistant/agent.py`) can be invoked to ask natural-language questions about infrastructure:

```python
from ai_assistant.agent import build_agent

agent = build_agent()
response = agent.invoke({"input": "What are the top 5 critical assets near 17.25, 80.15?"})
print(response['output'])
```

The agent has access to:
- `/assets` - List/filter assets
- `/nearby` - Radius search
- `/hotspots` - Clustering
- `/stats` - Aggregate statistics
- `/explain` - Risk explanations

---

## Development Guide

### Adding New Risk Features

Edit `ml/train_risk_model.py`:

```python
NUMERIC_FEATURES = [
    "elevation_m", "age_years", ...,
    "your_new_feature",  # Add here
]
```

Then retrain:
```bash
python ml/train_risk_model.py
python run.py --serve-only
```

### Integrating Real Data

Replace `data/generate_synthetic_data.py` with your data source:

```python
# Use OSMnx for real street networks:
import osmnx as ox
G = ox.graph_from_place("Khammam, Telangana")

# Use real asset data:
df = pd.read_csv("municipal_assets.csv")
```

### Switching to PostGIS Backend

The code is already structured for this (see comments in `backend/main.py`):

```python
# Replace AssetStore with SQLAlchemy + GeoAlchemy2
from geoalchemy2 import Geometry
from sqlalchemy import create_engine

engine = create_engine(config.DATABASE_URL)
# Use session.query(Asset).filter(Asset.geom.ST_DWithin(...))
```

---

## Troubleshooting

### "Data file not found" Error

**Solution:** Run the data generation pipeline first:
```bash
python run.py --generate-only
python run.py --train-only
python run.py --serve-only
```

### "River data not found" Error

**Solution:** Ensure `db/river.json` exists:
```bash
python data/generate_synthetic_data.py
```

### Port Already in Use

**Solution:** Use a different port:
```bash
python run.py --port 9000
```

Or modify `.env`:
```bash
API_PORT=9000
```

### Docker Container Fails to Start

**Solution:** Check logs and ensure data files exist:
```bash
docker-compose logs backend
docker-compose down
python data/generate_synthetic_data.py
python ml/train_risk_model.py
docker-compose up --build
```

### API Returns 500 Error

**Check logs:**
```bash
tail logs/urbanshield.log
# or in Docker:
docker-compose logs backend
```

---

## Performance & Scaling

### Current Implementation (CSV-based)
- ✅ Suitable for cities with 1,000-10,000 assets
- ✅ Fast spatial queries with pandas Haversine distance
- ✅ Instant startup (no DB init required)

### Scale to 100,000+ Assets
- Migrate to PostGIS backend (see `db/schema.sql`)
- Replace `AssetStore` with SQLAlchemy + GeoAlchemy2
- Use spatial indexes: `GIST`, `BRIN`
- Leverage `ST_ClusterDBSCAN`, `ST_DWithin` for performance

See comments in `backend/main.py` for exact migration steps.
| Map dashboard | Leaflet.js, river + street network layers, color-coded risk markers, live filters | `frontend/index.html` |
| AI assistant | LangChain tool-calling agent grounded in live API data | `ai_assistant/agent.py` |
| Orchestration | Docker Compose (PostGIS + backend + frontend) | `docker-compose.yml` |

### Khammam-specific modeling

Khammam's dominant infrastructure risk driver is the **Munneru river**, which
floods parts of the city seasonally. Rather than a random flood flag, this
build computes real point-to-river distance for every asset (vectorized
point-to-polyline geometry) and uses it as a continuous feature — it came out
as the single strongest predictor in the trained model, ahead of asset age.
Assets are also placed along a synthetic street-grid graph (`networkx`)
instead of scattered uniformly, and road segments crossing the river are
automatically promoted to bridges — so the map reads like an actual city
layout, not a random point cloud.

## Quickstart (no Docker — fastest way to see it working)

```bash
pip install -r requirements.txt

# 1. Generate synthetic city infrastructure data
cd data && python generate_synthetic_data.py

# 2. Train the risk model (produces assets_scored.csv + model.joblib)
cd ../ml && python train_risk_model.py

# 3. Start the API
cd ../backend && uvicorn main:app --reload --port 8000
# → open http://localhost:8000/docs for interactive API docs

# 4. Open the map dashboard
# just open frontend/index.html in a browser (it fetches from localhost:8000)

# 5. (optional) Ask the AI assistant a question
export ANTHROPIC_API_KEY=sk-...
cd ../ai_assistant && python agent.py "Which water pipelines are highest risk?"
```

## Quickstart (full stack with real PostGIS via Docker)

```bash
docker compose up --build
# Postgres+PostGIS on :5432, API on :8000, dashboard on :8080
```

Then load the generated CSVs into PostGIS following the `\copy` instructions
at the bottom of `db/schema.sql`, and swap `backend/main.py`'s `AssetStore`
CSV reads for SQLAlchemy/GeoAlchemy2 queries against the `assets` table
(the route signatures are already written to match this 1:1).

## Notes on this build

- **Explainability without network access**: this environment couldn't
  `pip install shap` (no internet in the sandbox), so `ml/train_risk_model.py`
  ships a `BaselineAblationExplainer` — a from-scratch feature-attribution
  method with the same additive/efficiency property as SHAP (per-feature
  contributions sum to `prediction − baseline`). It's a legitimate
  explainability technique on its own, and swapping in real
  `shap.TreeExplainer` is a one-line change once you have internet access.
- **Data**: ships with a synthetic generator so the whole pipeline runs
  immediately without needing municipal data access. Swap `data/generate_synthetic_data.py`
  for real pulls (OSMnx for road networks, city open-data portals for
  incident logs) — the downstream schema stays the same.
- **AI assistant**: requires an LLM API key (Anthropic or OpenAI) to run live,
  since it calls a real model. All its tools are grounded — it can only report
  numbers that come back from the FastAPI backend, never invented ones.

## Suggested resume bullet (once you've run it end-to-end)

> Built UrbanShield, an end-to-end geospatial analytics platform (PostGIS,
> scikit-learn, FastAPI, Leaflet, LangChain) for Khammam, Telangana that scores
> 2,500+ infrastructure assets for failure risk (ROC-AUC 0.89) using real
> point-to-river distance and street-network topology, explains each score
> with per-feature attribution, clusters risk into geographic hotspots, and
> lets engineers query maintenance priorities via a natural-language AI
> assistant.
