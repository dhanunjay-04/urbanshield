"""
UrbanShield - Synthetic Infrastructure Asset Data Generator
--------------------------------------------------------------
Generates a realistic city-scale dataset of infrastructure assets
(roads, bridges, water pipelines) with geospatial coordinates and
features used for risk scoring — placed along a synthetic street
grid, with flood risk driven by real point-to-river distance rather
than a random flag (the Munneru river runs through Khammam and is
the city's dominant flood driver).

In production this module would be replaced/augmented with:
  - OpenStreetMap road network pulls (via OSMnx) instead of the
    synthetic grid below
  - Real river/waterway geometry (also from OSM, or state GIS data)
  - Municipal open-data portals (pothole complaints, maintenance logs)
  - Sensor/IoT feeds (vibration, pressure, traffic counters)

Run:
    python generate_synthetic_data.py
Output:
    ../db/assets.csv          (raw asset table, ready for PostGIS load)
    ../db/incidents.csv       (historical failure/incident log)
    ../db/river.json          (river polyline + street grid, for map display)
"""

import json
import numpy as np
import pandas as pd
import networkx as nx
from datetime import datetime, timedelta
from pathlib import Path

RNG = np.random.default_rng(42)

# ---- Project root for portable file paths ----
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "db"

# ---- City bounding box (Khammam, Telangana, ~12km x 12km) ----
CITY_NAME = "Khammam"
LAT_MIN, LAT_MAX = 17.20, 17.30
LON_MIN, LON_MAX = 80.10, 80.20

# Meters-per-degree at this latitude (equirectangular approximation — fine at city scale)
M_PER_DEG_LAT = 111_320
M_PER_DEG_LON = 111_320 * np.cos(np.radians((LAT_MIN + LAT_MAX) / 2))

ASSET_TYPES = ["road_segment", "bridge", "water_pipeline", "power_pole", "stormwater_drain"]
ASSET_TYPE_WEIGHTS = [0.45, 0.05, 0.25, 0.15, 0.10]
MATERIALS = {
    "road_segment": ["asphalt", "concrete", "gravel"],
    "bridge": ["steel", "reinforced_concrete", "masonry"],
    "water_pipeline": ["cast_iron", "PVC", "ductile_iron", "steel"],
    "power_pole": ["concrete", "wood", "steel"],
    "stormwater_drain": ["concrete", "brick", "PVC"],
}

N_ASSETS = 2500


# ---------------------------------------------------------------
# Munneru river polyline (approximate — a meandering line crossing
# the city, matching its real southwest-to-northeast course through
# Khammam). Replace with real OSM waterway geometry when online.
# ---------------------------------------------------------------
def build_river_polyline() -> np.ndarray:
    t = np.linspace(0, 1, 40)
    lon = LON_MIN + t * (LON_MAX - LON_MIN)
    # Meander using a couple of sine harmonics so it isn't a straight line
    meander = 0.028 * np.sin(t * 3.4 + 0.5) + 0.012 * np.sin(t * 7.1)
    lat = LAT_MIN + 0.35 * (LAT_MAX - LAT_MIN) + meander * (LAT_MAX - LAT_MIN)
    return np.column_stack([lat, lon])  # shape (40, 2)


def point_to_polyline_dist_m(lat, lon, polyline) -> np.ndarray:
    """Vectorized min distance (meters) from arrays of points to a polyline."""
    px = (lon[:, None] - polyline[None, :, 1]) * M_PER_DEG_LON
    py = (lat[:, None] - polyline[None, :, 0]) * M_PER_DEG_LAT
    seg_x = (polyline[1:, 1] - polyline[:-1, 1]) * M_PER_DEG_LON
    seg_y = (polyline[1:, 0] - polyline[:-1, 0]) * M_PER_DEG_LAT
    seg_len2 = seg_x ** 2 + seg_y ** 2
    seg_len2[seg_len2 == 0] = 1e-9

    ax = px[:, :-1]  # point relative to segment start, per segment
    ay = py[:, :-1]
    t = np.clip((ax * seg_x + ay * seg_y) / seg_len2, 0, 1)
    proj_x = t * seg_x
    proj_y = t * seg_y
    dist = np.sqrt((ax - proj_x) ** 2 + (ay - proj_y) ** 2)
    return dist.min(axis=1)


# ---------------------------------------------------------------
# Synthetic street grid (stand-in for a real OSMnx road pull).
# Roads/bridges/other assets are placed along this graph instead of
# scattered uniformly, so the map reads like an actual city layout.
# ---------------------------------------------------------------
def build_street_grid(rows=14, cols=14):
    G = nx.grid_2d_graph(rows, cols)
    lat_step = (LAT_MAX - LAT_MIN) / (rows - 1)
    lon_step = (LON_MAX - LON_MIN) / (cols - 1)
    # Slight jitter per node so the grid doesn't look perfectly synthetic
    jitter = RNG.normal(0, 0.0006, size=(rows, cols, 2))
    pos = {}
    for r in range(rows):
        for c in range(cols):
            lat = LAT_MIN + r * lat_step + jitter[r, c, 0]
            lon = LON_MIN + c * lon_step + jitter[r, c, 1]
            pos[(r, c)] = (lat, lon)
    # A handful of diagonal shortcut roads for realism
    for _ in range(10):
        r1, c1 = RNG.integers(0, rows), RNG.integers(0, cols)
        r2, c2 = RNG.integers(0, rows), RNG.integers(0, cols)
        if (r1, c1) != (r2, c2):
            G.add_edge((r1, c1), (r2, c2))
    return G, pos


def sample_points_on_edges(G, pos, n, river_polyline):
    """Sample n points uniformly along the street graph's edges, returning
    (lat, lon, crosses_river) for each. crosses_river marks edges whose
    midpoint is within 120m of the river — those become bridge candidates."""
    edges = list(G.edges())
    edge_idx = RNG.integers(0, len(edges), n)
    fracs = RNG.uniform(0, 1, n)
    lats, lons, crosses_river = [], [], []
    for i, f in zip(edge_idx, fracs):
        (r1, c1), (r2, c2) = edges[i]
        lat1, lon1 = pos[(r1, c1)]
        lat2, lon2 = pos[(r2, c2)]
        lat = lat1 + f * (lat2 - lat1)
        lon = lon1 + f * (lon2 - lon1)
        lats.append(lat)
        lons.append(lon)
    lats, lons = np.array(lats), np.array(lons)
    dist_to_river = point_to_polyline_dist_m(lats, lons, river_polyline)
    crosses_river = dist_to_river < 150
    return lats, lons, crosses_river


def generate_assets(n=N_ASSETS) -> pd.DataFrame:
    river = build_river_polyline()
    G, pos = build_street_grid()
    lat, lon, near_river_edge = sample_points_on_edges(G, pos, n, river)

    # Nudge non-road assets (pipelines/poles/drains) slightly off the road
    # centerline, the way real utility infrastructure runs alongside streets.
    offset_lat = RNG.normal(0, 0.0008, n)
    offset_lon = RNG.normal(0, 0.0008, n)

    asset_type = RNG.choice(ASSET_TYPES, size=n, p=ASSET_TYPE_WEIGHTS)
    is_road_like = np.isin(asset_type, ["road_segment", "bridge"])
    lat = np.where(is_road_like, lat, lat + offset_lat)
    lon = np.where(is_road_like, lon, lon + offset_lon)

    # Bridges cluster where the road network crosses the river
    asset_type = np.where(
        (asset_type == "road_segment") & near_river_edge & (RNG.random(n) < 0.5),
        "bridge",
        asset_type,
    )

    # Real distance-to-river feature (meters) — the actual flood risk driver
    distance_to_river_m = point_to_polyline_dist_m(lat, lon, river)
    flood_zone = (distance_to_river_m < 400).astype(int)  # kept as a legacy boolean flag

    # Age: older infra skews toward city center (simulated via distance-based bias)
    center_lat, center_lon = (LAT_MIN + LAT_MAX) / 2, (LON_MIN + LON_MAX) / 2
    dist_from_center = np.sqrt((lat - center_lat) ** 2 + (lon - center_lon) ** 2)
    dist_norm = (dist_from_center - dist_from_center.min()) / (np.ptp(dist_from_center) + 1e-9)
    base_age = RNG.gamma(shape=4.0, scale=6.0, size=n)  # years
    age_years = np.clip(base_age + (1 - dist_norm) * 15, 0, 90).round(1)

    material = np.array([RNG.choice(MATERIALS[t]) for t in asset_type])

    # Traffic / usage load (0-100 scale), higher near center
    traffic_load = np.clip(RNG.normal(loc=40 + (1 - dist_norm) * 40, scale=15, size=n), 0, 100).round(1)

    # Soil corrosivity index (affects pipelines/poles), 0-1 — elevated near the river
    river_proximity_norm = np.clip(1 - distance_to_river_m / 3000, 0, 1)
    soil_corrosivity = np.clip(RNG.beta(2, 5, n) + 0.25 * river_proximity_norm, 0, 1).round(3)

    # Last inspection recency (days since last inspection)
    days_since_inspection = RNG.integers(30, 2200, n)

    # Maintenance history count
    past_maintenance_count = RNG.poisson(lam=1.5, size=n)

    # Elevation (meters) — lower near the river (real floodplain topography)
    elevation_m = np.clip(RNG.normal(520, 25, n) - 18 * river_proximity_norm, 440, 600).round(1)

    # ---- True latent risk function (ground truth generator, hidden from the model) ----
    material_risk = np.array([
        {"asphalt": 0.3, "concrete": 0.15, "gravel": 0.5,
         "steel": 0.25, "reinforced_concrete": 0.15, "masonry": 0.45,
         "cast_iron": 0.55, "PVC": 0.2, "ductile_iron": 0.25,
         "wood": 0.5, "brick": 0.4}[m] for m in material
    ])

    latent_risk = (
        0.26 * (age_years / 90)
        + 0.18 * material_risk
        + 0.13 * (traffic_load / 100)
        + 0.13 * soil_corrosivity
        + 0.20 * river_proximity_norm       # river distance is now the strongest flood-risk driver
        + 0.08 * (days_since_inspection / 2200)
        - 0.05 * np.tanh(past_maintenance_count / 3)
    )
    noise = RNG.normal(0, 0.05, n)
    latent_risk = np.clip(latent_risk + noise, 0, 1)

    threshold = np.quantile(latent_risk, 0.79)  # targets ~21% positive rate
    label_noise = RNG.normal(0, 0.06, n)
    failed_recently = ((latent_risk + label_noise) > threshold).astype(int)

    df = pd.DataFrame({
        "asset_id": [f"AST-{i:05d}" for i in range(n)],
        "asset_type": asset_type,
        "material": material,
        "latitude": lat.round(6),
        "longitude": lon.round(6),
        "elevation_m": elevation_m,
        "age_years": age_years,
        "traffic_load": traffic_load,
        "soil_corrosivity": soil_corrosivity,
        "distance_to_river_m": distance_to_river_m.round(1),
        "flood_zone": flood_zone,
        "days_since_inspection": days_since_inspection,
        "past_maintenance_count": past_maintenance_count,
        "failed_recently": failed_recently,
        "_true_latent_risk": latent_risk.round(4),  # kept for validation only; not a model feature
    })
    return df, river, G, pos


def generate_incidents(assets: pd.DataFrame) -> pd.DataFrame:
    """Generate a historical incident log for assets that failed recently."""
    failed = assets[assets["failed_recently"] == 1].copy()
    n = len(failed)
    days_ago = RNG.integers(1, 730, n)
    incident_date = [datetime.now() - timedelta(days=int(d)) for d in days_ago]
    severity = RNG.choice(["low", "medium", "high", "critical"], size=n, p=[0.35, 0.35, 0.22, 0.08])
    repair_cost_usd = np.round(RNG.gamma(shape=2.5, scale=1500, size=n), 2)

    incidents = pd.DataFrame({
        "incident_id": [f"INC-{i:05d}" for i in range(n)],
        "asset_id": failed["asset_id"].values,
        "asset_type": failed["asset_type"].values,
        "incident_date": incident_date,
        "severity": severity,
        "repair_cost_usd": repair_cost_usd,
        "description": [
            f"{t.replace('_', ' ').title()} failure reported near lat {la:.4f}, lon {lo:.4f}"
            for t, la, lo in zip(failed["asset_type"], failed["latitude"], failed["longitude"])
        ],
    })
    return incidents


if __name__ == "__main__":
    assets, river, G, pos = generate_assets()
    incidents = generate_incidents(assets)

    # Ensure db directory exists
    DB_PATH.mkdir(parents=True, exist_ok=True)
    
    assets_out = assets.drop(columns=["_true_latent_risk"])
    assets_out.to_csv(DB_PATH / "assets.csv", index=False)
    print(f"Saved assets to {DB_PATH / 'assets.csv'}")
    
    incidents.to_csv(DB_PATH / "incidents.csv", index=False)
    print(f"Saved incidents to {DB_PATH / 'incidents.csv'}")

    # Export river polyline + street grid for the map layer
    streets = [
        {"from": list(pos[a]), "to": list(pos[b])} for a, b in G.edges()
    ]
    with open(DB_PATH / "river.json", "w") as f:
        json.dump({
            "river_polyline": river.tolist(),
            "streets": streets,
        }, f)

    print(f"Generated {len(assets_out)} assets and {len(incidents)} incidents for {CITY_NAME}.")
    print(assets_out.head())
    print(f"\nFailure rate: {assets_out['failed_recently'].mean():.1%}")
    print(f"Assets within 400m of Munneru river (flood_zone=1): {assets_out['flood_zone'].sum()} ({assets_out['flood_zone'].mean():.1%})")

