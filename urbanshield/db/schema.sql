-- UrbanShield PostGIS Schema
-- ---------------------------------------------------------------
-- Run against a PostgreSQL instance with the PostGIS extension.
--   createdb urbanshield
--   psql -d urbanshield -f schema.sql

CREATE EXTENSION IF NOT EXISTS postgis;

-- ============ Assets ============
CREATE TABLE IF NOT EXISTS assets (
    asset_id                VARCHAR(20) PRIMARY KEY,
    asset_type              VARCHAR(50) NOT NULL,
    material                VARCHAR(50),
    geom                    GEOMETRY(Point, 4326) NOT NULL,
    elevation_m             NUMERIC(6,1),
    age_years               NUMERIC(5,1),
    traffic_load            NUMERIC(5,1),
    soil_corrosivity        NUMERIC(5,3),
    flood_zone              BOOLEAN,
    distance_to_river_m     NUMERIC(8,1),   -- point-to-polyline distance to nearest river (ST_Distance)
    days_since_inspection   INTEGER,
    past_maintenance_count  INTEGER,
    failed_recently         BOOLEAN,
    risk_score              NUMERIC(5,4),      -- populated by ML pipeline
    risk_tier               VARCHAR(10),        -- 'low' | 'medium' | 'high' | 'critical'
    updated_at               TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_assets_geom ON assets USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_assets_type ON assets (asset_type);
CREATE INDEX IF NOT EXISTS idx_assets_risk ON assets (risk_score DESC);

-- ============ Incidents (historical failure/maintenance log) ============
CREATE TABLE IF NOT EXISTS incidents (
    incident_id      VARCHAR(20) PRIMARY KEY,
    asset_id         VARCHAR(20) REFERENCES assets(asset_id),
    asset_type       VARCHAR(50),
    incident_date    TIMESTAMP,
    severity         VARCHAR(20),
    repair_cost_usd  NUMERIC(10,2),
    description      TEXT
);

CREATE INDEX IF NOT EXISTS idx_incidents_asset ON incidents (asset_id);
CREATE INDEX IF NOT EXISTS idx_incidents_date ON incidents (incident_date DESC);

-- ============ Risk hotspot zones (derived, spatial clustering output) ============
CREATE TABLE IF NOT EXISTS risk_zones (
    zone_id          SERIAL PRIMARY KEY,
    zone_geom        GEOMETRY(Polygon, 4326),
    avg_risk_score   NUMERIC(5,4),
    asset_count      INTEGER,
    dominant_type    VARCHAR(50),
    computed_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_riskzones_geom ON risk_zones USING GIST (zone_geom);

-- ============ Waterways (rivers, for flood-risk distance calc) ============
CREATE TABLE IF NOT EXISTS waterways (
    waterway_id      SERIAL PRIMARY KEY,
    name             VARCHAR(100),
    geom             GEOMETRY(LineString, 4326)  -- e.g. the Munneru river through Khammam
);

CREATE INDEX IF NOT EXISTS idx_waterways_geom ON waterways USING GIST (geom);

-- Real point-to-river distance query (replaces the Python haversine
-- approximation used in db/river.json / backend/main.py's CSV mode):
-- SELECT a.asset_id,
--        ST_Distance(a.geom::geography, w.geom::geography) AS distance_to_river_m
-- FROM assets a, waterways w
-- WHERE w.name = 'Munneru'
-- ORDER BY distance_to_river_m ASC;

-- ============ Example spatial queries ============

-- Load CSV (after generate_synthetic_data.py) via psql \copy, then populate geom:
--   \copy assets(asset_id,asset_type,material,latitude,longitude,elevation_m,age_years,
--                traffic_load,soil_corrosivity,flood_zone,days_since_inspection,
--                past_maintenance_count,failed_recently) FROM 'assets.csv' WITH CSV HEADER
--   UPDATE assets SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326);
-- (requires temporary latitude/longitude columns during load, then drop them)

-- Find all high-risk assets within 500m of a given point:
-- SELECT asset_id, asset_type, risk_score
-- FROM assets
-- WHERE risk_tier IN ('high','critical')
--   AND ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(78.47,17.40),4326)::geography, 500);

-- Cluster high-risk assets into hotspot zones (using ST_ClusterDBSCAN):
-- SELECT asset_id, ST_ClusterDBSCAN(geom, eps := 0.005, minpoints := 5) OVER () AS cluster_id
-- FROM assets WHERE risk_score > 0.6;
