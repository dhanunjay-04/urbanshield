"""
UrbanShield - FastAPI Backend
---------------------------------------------------------------
Serves scored infrastructure assets, spatial hotspot queries, and
per-asset risk explanations to the frontend map and the AI assistant.

In production, replace the CSV-backed AssetStore with real PostGIS
queries (see db/schema.sql) via SQLAlchemy + GeoAlchemy2 — the route
signatures below are written to match that swap 1:1 (see comments).

Run:
    uvicorn main:app --reload --port 8000
Docs:
    http://localhost:8000/docs
"""

import json
import math
import logging
import re
import sys
from typing import Optional
from pathlib import Path

# Add parent directory to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

try:
    from .config import config
except ImportError:
    from config import config

# Configure logging
logging.basicConfig(
    level=config.LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(config.get_log_file_path()),
    ],
)
logger = logging.getLogger(__name__)

DATA_PATH = config.DATA_PATH

app = FastAPI(
    title="UrbanShield API",
    description="Geospatial infrastructure risk & predictive maintenance API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def strip_api_prefix(request: Request, call_next):
    if request.scope["path"].startswith("/api/"):
        request.scope["path"] = request.scope["path"][4:]
    return await call_next(request)



# ---------------------------------------------------------------
# Data access layer (CSV now; swap for PostGIS via SQLAlchemy later)
# ---------------------------------------------------------------
class AssetStore:
    def __init__(self, path: str):
        self.df = pd.read_csv(path)
        self.df["top_risk_drivers"] = self.df["top_risk_drivers"].apply(json.loads)

    def all(self) -> pd.DataFrame:
        return self.df

    def by_id(self, asset_id: str) -> Optional[pd.Series]:
        match = self.df[self.df["asset_id"] == asset_id]
        return match.iloc[0] if len(match) else None

    def within_radius(self, lat: float, lon: float, radius_m: float) -> pd.DataFrame:
        # Haversine distance (meters) — PostGIS equivalent: ST_DWithin(geom::geography, ...)
        R = 6371000
        lat1, lon1 = math.radians(lat), math.radians(lon)
        lat2 = self.df["latitude"].apply(math.radians)
        lon2 = self.df["longitude"].apply(math.radians)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = (
            (dlat / 2).apply(math.sin) ** 2
            + math.cos(lat1) * lat2.apply(math.cos) * (dlon / 2).apply(math.sin) ** 2
        )
        c = 2 * a.apply(lambda x: math.asin(min(1, math.sqrt(x))))
        dist = R * c
        return self.df[dist <= radius_m].assign(distance_m=dist[dist <= radius_m].round(1))

    def filter(
        self,
        asset_type: Optional[str] = None,
        risk_tier: Optional[str] = None,
        min_risk: Optional[float] = None,
    ) -> pd.DataFrame:
        out = self.df
        if asset_type:
            out = out[out["asset_type"] == asset_type]
        if risk_tier:
            out = out[out["risk_tier"] == risk_tier]
        if min_risk is not None:
            out = out[out["risk_score"] >= min_risk]
        return out


# ---------------------------------------------------------------
# Initialize data store with error handling
# ---------------------------------------------------------------
try:
    logger.info(f"Loading asset data from {DATA_PATH}")
    store = AssetStore(DATA_PATH)
    logger.info(f"Successfully loaded {len(store.all())} assets")
except FileNotFoundError as e:
    logger.error(f"Data file not found at {DATA_PATH}")
    logger.error(
        "You must run the data generation and model training pipeline first:\n"
        "  1. python data/generate_synthetic_data.py\n"
        "  2. python ml/train_risk_model.py\n"
        "Then restart the API."
    )
    raise
except Exception as e:
    logger.error(f"Error loading asset data: {e}")
    raise


# ---------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------
class RiskDriver(BaseModel):
    feature: str
    impact: float


class Asset(BaseModel):
    asset_id: str
    asset_type: str
    material: str
    latitude: float
    longitude: float
    age_years: float
    traffic_load: float
    soil_corrosivity: float
    distance_to_river_m: float
    flood_zone: int
    days_since_inspection: int
    past_maintenance_count: int
    risk_score: float
    risk_tier: str
    top_risk_drivers: list[RiskDriver]


class NearbyAsset(Asset):
    distance_m: float


class HotspotSummary(BaseModel):
    zone_center_lat: float
    zone_center_lon: float
    asset_count: int
    avg_risk_score: float
    dominant_type: str


class AssistantQuestion(BaseModel):
    question: str


# ---------------------------------------------------------------
# Routes
# ---------------------------------------------------------------
@app.get("/")
def root():
    """Serve the UrbanShield dashboard as the website landing page."""
    return FileResponse(PROJECT_ROOT / "frontend" / "index.html")


@app.get("/health")
def health():
    """API health check and loaded dataset status."""
    return {
        "service": "UrbanShield API",
        "version": "1.0.0",
        "status": "ok",
        "asset_count": len(store.all()),
        "frontend_api_base": config.FRONTEND_API_BASE,
    }


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    """Serve the interactive map dashboard."""
    return FileResponse(PROJECT_ROOT / "frontend" / "index.html")


@app.get("/ai_assistant/chat.html", include_in_schema=False)
def assistant_page():
    """Serve the optional AI assistant chat interface."""
    return FileResponse(PROJECT_ROOT / "ai_assistant" / "chat.html")


@app.get("/assistant-api/health")
def assistant_health():
    return {"status": "ok", "service": "UrbanShield data-backed assistant"}


@app.post("/assistant-api/ask")
def assistant_ask(request: AssistantQuestion):
    """Answer common demo questions from the loaded dataset without an LLM key."""
    question = request.question.strip()
    normalized = question.lower()
    asset_match = re.search(r"\bAST-\d{5}\b", question, re.IGNORECASE)

    if asset_match:
        asset_id = asset_match.group().upper()
        if store.by_id(asset_id) is None:
            answer = f"No asset found with ID {asset_id}."
        else:
            answer = explain_asset_risk(asset_id)["explanation"]
    elif any(term in normalized for term in ("maintenance", "fix first", "priorit")):
        slots_match = re.search(r"\b(\d+)\s*(?:crews|slots|teams)\b", normalized)
        slots = min(max(int(slots_match.group(1)), 1), 2500) if slots_match else 10
        assets = store.all().sort_values("risk_score", ascending=False).head(slots)
        answer = "Top maintenance priorities:\n" + "\n".join(
            f"{index + 1}. {row.asset_id} ({row.asset_type}), risk {row.risk_score:.2f}"
            for index, row in enumerate(assets.itertuples())
        )
    elif "hotspot" in normalized:
        zones = hotspots()
        answer = "\n".join(
            f"Zone near ({zone['zone_center_lat']}, {zone['zone_center_lon']}): "
            f"{zone['asset_count']} assets, average risk {zone['avg_risk_score']:.2f}."
            for zone in zones[:10]
        ) or "No significant hotspot clusters detected."
    elif any(term in normalized for term in ("critical", "high risk", "bridge", "pipeline", "road")):
        asset_types = ("road_segment", "bridge", "water_pipeline", "power_pole", "stormwater_drain")
        asset_type = next(
            (kind for kind in asset_types if kind in normalized or kind.replace("_", " ") in normalized),
            None,
        )
        risk_tier = "critical" if "critical" in normalized else "high"
        assets = store.filter(asset_type=asset_type, risk_tier=risk_tier)
        assets = assets.sort_values("risk_score", ascending=False).head(10)
        answer = "\n".join(
            f"{row.asset_id} ({row.asset_type}), risk {row.risk_score:.2f} [{row.risk_tier}]"
            for row in assets.itertuples()
        ) or "No assets matched that risk filter."
    else:
        summary = stats()
        answer = (
            f"Total assets: {summary['total_assets']}. Critical assets: "
            f"{summary['critical_count']}. Average risk score: {summary['avg_risk_score']:.3f}. "
            f"Risk tiers: {summary['by_tier']}."
        )

    return {
        "answer": f"Data-backed demo answer (no external AI credits required):\n\n{answer}",
        "success": True,
    }


@app.get("/config")
def get_config():
    """Return frontend-safe configuration for the web dashboard."""
    return {
        "api_base": config.FRONTEND_API_BASE,
        "asset_count": len(store.all()),
        "version": "1.0.0",
    }


@app.get("/assets", response_model=list[Asset])
def list_assets(
    asset_type: Optional[str] = None,
    risk_tier: Optional[str] = Query(None, description="low | medium | high | critical"),
    min_risk: Optional[float] = Query(None, ge=0, le=1),
    limit: int = Query(500, le=2500),
):
    """List assets, optionally filtered by type / risk tier / minimum risk score."""
    df = store.filter(asset_type=asset_type, risk_tier=risk_tier, min_risk=min_risk)
    df = df.sort_values("risk_score", ascending=False).head(limit)
    return df.to_dict(orient="records")


@app.get("/assets/{asset_id}", response_model=Asset)
def get_asset(asset_id: str):
    """Full detail + explainability for one asset."""
    row = store.by_id(asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    return row.to_dict()


@app.get("/assets/{asset_id}/explain")
def explain_asset(asset_id: str):
    """Plain-language risk explanation for one asset (used by the AI assistant)."""
    row = store.by_id(asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    drivers = row["top_risk_drivers"]
    lines = [
        f"{d['feature']} ({'raises' if d['impact']>0 else 'lowers'} risk by {abs(d['impact']):.2f})"
        for d in drivers
    ]
    return {
        "asset_id": asset_id,
        "asset_type": row["asset_type"],
        "risk_score": round(float(row["risk_score"]), 3),
        "risk_tier": row["risk_tier"],
        "explanation": (
            f"{asset_id} ({row['asset_type']}) has a risk score of {row['risk_score']:.2f} "
            f"({row['risk_tier']}). Main drivers: " + "; ".join(lines) + "."
        ),
    }


@app.get("/nearby", response_model=list[NearbyAsset])
def nearby_assets(
    lat: float,
    lon: float,
    radius_m: float = Query(500, gt=0),
    risk_tier: Optional[str] = None,
):
    """Assets within radius_m meters of (lat, lon) — PostGIS: ST_DWithin on geography."""
    df = store.within_radius(lat, lon, radius_m)
    if risk_tier:
        df = df[df["risk_tier"] == risk_tier]
    return df.sort_values("risk_score", ascending=False).to_dict(orient="records")


@app.get("/hotspots", response_model=list[HotspotSummary])
def hotspots(
    grid_size: float = Query(0.01, gt=0, description="grid cell size in degrees (~1.1km at grid_size=0.01)"),
    min_assets: int = Query(5, ge=1, description="minimum assets in a cell to count as a hotspot"),
):
    """
    Simple grid-based clustering of high-risk assets into hotspot zones.
    PostGIS equivalent: ST_ClusterDBSCAN(geom, eps, minpoints) OVER () — see schema.sql.
    """
    df = store.all().copy()
    df = df[df["risk_tier"].isin(["high", "critical"])]
    if df.empty:
        return []
    df["grid_lat"] = (df["latitude"] / grid_size).round().astype(int)
    df["grid_lon"] = (df["longitude"] / grid_size).round().astype(int)

    zones = []
    for (glat, glon), group in df.groupby(["grid_lat", "grid_lon"]):
        if len(group) < min_assets:
            continue
        zones.append(
            {
                "zone_center_lat": round(group["latitude"].mean(), 5),
                "zone_center_lon": round(group["longitude"].mean(), 5),
                "asset_count": len(group),
                "avg_risk_score": round(group["risk_score"].mean(), 3),
                "dominant_type": group["asset_type"].mode().iloc[0],
            }
        )
    zones.sort(key=lambda z: z["avg_risk_score"], reverse=True)
    return zones


@app.get("/river-layer")
def river_layer():
    """River polyline + street grid geometry, for map display (see db/river.json)."""
    river_path = config.RIVER_LAYER_PATH
    logger.info(f"Loading river layer from: {river_path}")
    if not river_path.exists():
        logger.error(f"River data not found at {river_path}")
        raise HTTPException(
            status_code=500,
            detail=f"River data not found. Run: python data/generate_synthetic_data.py"
        )
    try:
        with open(river_path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid river.json format: {e}")
        raise HTTPException(status_code=500, detail=f"Invalid river.json format: {e}")
    except IOError as e:
        logger.error(f"Error reading river.json: {e}")
        raise HTTPException(status_code=500, detail=f"Error reading river.json: {e}")


@app.get("/stats")
def stats():
    """Summary stats for the dashboard header."""
    df = store.all()
    return {
        "total_assets": len(df),
        "by_tier": df["risk_tier"].value_counts().to_dict(),
        "by_type": df["asset_type"].value_counts().to_dict(),
        "avg_risk_score": round(df["risk_score"].mean(), 4),
        "critical_count": int((df["risk_tier"] == "critical").sum()),
    }


@app.get("/maintenance-priority", response_model=list[Asset])
def maintenance_priority(
    budget_slots: int = Query(20, ge=1, le=2500, description="number of maintenance crews/slots available"),
):
    """
    Prioritized maintenance list — top N assets ranked by risk score,
    ready to hand directly to field crews.
    """
    df = store.all().sort_values("risk_score", ascending=False).head(budget_slots)
    return df.to_dict(orient="records")
