#!/usr/bin/env python3
"""
UrbanShield PostGIS Migration Script
====================================
Migrates asset data from CSV files to PostGIS database.
Includes spatial indexing and validation.

Usage:
    python db/migrate_to_postgis.py --host localhost --user urbanshield --password urbanshield_dev
"""

import argparse
import logging
import sys
from pathlib import Path
import json

import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from psycopg2.errors import DatabaseError

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_sql_file(filename):
    """Load SQL file from db directory"""
    sql_file = PROJECT_ROOT / "db" / filename
    if not sql_file.exists():
        raise FileNotFoundError(f"SQL file not found: {sql_file}")
    with open(sql_file) as f:
        return f.read()


def connect_db(host, port, user, password, dbname):
    """Connect to PostgreSQL database"""
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=dbname,
        )
        logger.info(f"Connected to {dbname} at {host}:{port}")
        return conn
    except psycopg2.OperationalError as e:
        logger.error(f"Failed to connect to database: {e}")
        logger.error("Ensure PostgreSQL is running and credentials are correct")
        raise


def init_database(conn):
    """Initialize database schema from schema.sql"""
    logger.info("Initializing database schema...")
    schema_sql = load_sql_file("schema.sql")
    
    try:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
        logger.info("Schema initialized successfully")
    except DatabaseError as e:
        logger.error(f"Error initializing schema: {e}")
        conn.rollback()
        raise


def load_assets_from_csv(csv_path):
    """Load scored assets from CSV"""
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    logger.info(f"Loading assets from {csv_path}")
    df = pd.read_csv(csv_path)
    
    # Parse JSON column
    df["top_risk_drivers"] = df["top_risk_drivers"].apply(json.loads)
    
    logger.info(f"Loaded {len(df)} assets from CSV")
    return df


def load_incidents_from_csv(csv_path):
    """Load incidents from CSV"""
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    logger.info(f"Loading incidents from {csv_path}")
    df = pd.read_csv(csv_path)
    
    logger.info(f"Loaded {len(df)} incidents from CSV")
    return df


def load_assets_to_db(conn, assets_df):
    """Insert assets into PostGIS database"""
    logger.info(f"Inserting {len(assets_df)} assets into database...")
    
    insert_sql = """
        INSERT INTO assets (
            asset_id, asset_type, material,
            elevation_m, age_years, traffic_load, soil_corrosivity,
            flood_zone, distance_to_river_m, days_since_inspection,
            past_maintenance_count, failed_recently, risk_score, risk_tier,
            geom
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            ST_SetSRID(ST_Point(%s, %s), 4326)
        )
        ON CONFLICT (asset_id) DO UPDATE SET
            risk_score = EXCLUDED.risk_score,
            risk_tier = EXCLUDED.risk_tier,
            updated_at = NOW()
    """
    
    rows = []
    for _, row in assets_df.iterrows():
        rows.append((
            row['asset_id'],
            row['asset_type'],
            row['material'],
            float(row['elevation_m']),
            int(row['age_years']),
            float(row['traffic_load']),
            float(row['soil_corrosivity']),
            int(row['flood_zone']),
            float(row['distance_to_river_m']),
            int(row['days_since_inspection']),
            int(row['past_maintenance_count']),
            bool(int(row['failed_recently'])),
            float(row['risk_score']),
            row['risk_tier'],
            # Geometry (lon, lat) - note: PostGIS uses lon,lat order
            float(row['longitude']),
            float(row['latitude']),
        ))
    
    try:
        with conn.cursor() as cur:
            execute_batch(cur, insert_sql, rows, page_size=100)
        conn.commit()
        logger.info(f"Successfully inserted {len(rows)} assets")
    except DatabaseError as e:
        logger.error(f"Error inserting assets: {e}")
        conn.rollback()
        raise


def load_incidents_to_db(conn, incidents_df):
    """Insert incidents into database"""
    logger.info(f"Inserting {len(incidents_df)} incidents into database...")
    
    insert_sql = """
        INSERT INTO incidents (
            incident_id, asset_id, asset_type, incident_date,
            severity, repair_cost_usd, description
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (incident_id) DO NOTHING
    """
    
    rows = []
    for _, row in incidents_df.iterrows():
        rows.append((
            row['incident_id'],
            row['asset_id'],
            row['asset_type'],
            row['incident_date'],
            row['severity'],
            float(row['repair_cost_usd']),
            row['description'],
        ))
    
    try:
        with conn.cursor() as cur:
            execute_batch(cur, insert_sql, rows, page_size=100)
        conn.commit()
        logger.info(f"Successfully inserted {len(rows)} incidents")
    except DatabaseError as e:
        logger.error(f"Error inserting incidents: {e}")
        conn.rollback()
        raise


def create_spatial_indexes(conn):
    """Create spatial indexes for performance"""
    logger.info("Creating spatial indexes...")
    
    indexes_sql = """
        CREATE INDEX IF NOT EXISTS idx_assets_geom ON assets USING GIST (geom);
        CREATE INDEX IF NOT EXISTS idx_assets_risk_tier ON assets (risk_tier);
        CREATE INDEX IF NOT EXISTS idx_assets_type ON assets (asset_type);
        CREATE INDEX IF NOT EXISTS idx_assets_risk_score ON assets (risk_score DESC);
        CREATE INDEX IF NOT EXISTS idx_incidents_asset ON incidents (asset_id);
        ANALYZE assets;
        ANALYZE incidents;
    """
    
    try:
        with conn.cursor() as cur:
            cur.execute(indexes_sql)
        conn.commit()
        logger.info("Spatial indexes created successfully")
    except DatabaseError as e:
        logger.error(f"Error creating indexes: {e}")
        conn.rollback()
        raise


def validate_migration(conn):
    """Validate the migration"""
    logger.info("Validating migration...")
    
    with conn.cursor() as cur:
        # Check asset counts
        cur.execute("SELECT COUNT(*) FROM assets")
        asset_count = cur.fetchone()[0]
        logger.info(f"✓ Total assets in database: {asset_count}")
        
        # Check risk distribution
        cur.execute("""
            SELECT risk_tier, COUNT(*) 
            FROM assets 
            GROUP BY risk_tier 
            ORDER BY COUNT(*) DESC
        """)
        logger.info("✓ Risk tier distribution:")
        for tier, count in cur.fetchall():
            logger.info(f"  - {tier}: {count}")
        
        # Check asset type distribution
        cur.execute("""
            SELECT asset_type, COUNT(*) 
            FROM assets 
            GROUP BY asset_type 
            ORDER BY COUNT(*) DESC
        """)
        logger.info("✓ Asset type distribution:")
        for atype, count in cur.fetchall():
            logger.info(f"  - {atype}: {count}")
        
        # Check incidents
        cur.execute("SELECT COUNT(*) FROM incidents")
        incident_count = cur.fetchone()[0]
        logger.info(f"✓ Total incidents in database: {incident_count}")
        
        # Test spatial query
        cur.execute("""
            SELECT COUNT(*) FROM assets 
            WHERE ST_DWithin(
                geom::geography,
                ST_SetSRID(ST_Point(80.15, 17.25), 4326)::geography,
                500
            )
        """)
        nearby_count = cur.fetchone()[0]
        logger.info(f"✓ Assets within 500m of (17.25, 80.15): {nearby_count}")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate UrbanShield asset data from CSV to PostGIS",
        epilog="Example: python migrate_to_postgis.py --host localhost --user urbanshield"
    )
    
    parser.add_argument(
        "--host",
        default="localhost",
        help="PostgreSQL host (default: localhost)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5432,
        help="PostgreSQL port (default: 5432)"
    )
    parser.add_argument(
        "--user",
        default="urbanshield",
        help="PostgreSQL user (default: urbanshield)"
    )
    parser.add_argument(
        "--password",
        default="urbanshield_dev",
        help="PostgreSQL password (default: urbanshield_dev)"
    )
    parser.add_argument(
        "--dbname",
        default="urbanshield_db",
        help="Database name (default: urbanshield_db)"
    )
    parser.add_argument(
        "--csv-assets",
        type=Path,
        default=PROJECT_ROOT / "db" / "assets_scored.csv",
        help="Path to assets CSV (default: db/assets_scored.csv)"
    )
    parser.add_argument(
        "--csv-incidents",
        type=Path,
        default=PROJECT_ROOT / "db" / "incidents.csv",
        help="Path to incidents CSV (default: db/incidents.csv)"
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("UrbanShield PostGIS Migration")
    logger.info("=" * 60)
    
    try:
        # Connect to database
        conn = connect_db(
            args.host, args.port, args.user, args.password, args.dbname
        )
        
        # Initialize schema
        init_database(conn)
        
        # Load data
        assets_df = load_assets_from_csv(args.csv_assets)
        incidents_df = load_incidents_from_csv(args.csv_incidents)
        
        # Load into database
        load_assets_to_db(conn, assets_df)
        load_incidents_to_db(conn, incidents_df)
        
        # Create indexes
        create_spatial_indexes(conn)
        
        # Validate
        validate_migration(conn)
        
        conn.close()
        
        logger.info("=" * 60)
        logger.info("✓ Migration completed successfully!")
        logger.info("=" * 60)
        
        return 0
    
    except Exception as e:
        logger.exception(f"Migration failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
