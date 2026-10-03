"""
UrbanShield Configuration Module
Loads settings from .env file and environment variables
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env file from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
else:
    load_dotenv()  # Fall back to environment variables


class Config:
    """Application configuration loaded from environment"""

    # API Settings
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", 8000))
    API_RELOAD = os.getenv("API_RELOAD", "true").lower() == "true"

    # Frontend API endpoint
    FRONTEND_API_BASE = os.getenv("FRONTEND_API_BASE", "http://localhost:8000")

    # AI Assistant
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

    # Data paths (relative to project root, or absolute)
    DATA_PATH_RAW = os.getenv("DATA_PATH", "./db/assets_scored.csv")
    RIVER_LAYER_PATH_RAW = os.getenv("RIVER_LAYER_PATH", "./db/river.json")

    # Resolve paths relative to PROJECT_ROOT if they're relative
    @staticmethod
    def resolve_path(path_str: str) -> Path:
        """Convert path string to absolute Path, relative to PROJECT_ROOT if needed"""
        p = Path(path_str)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p

    # Resolved absolute paths
    DATA_PATH = resolve_path.__func__(DATA_PATH_RAW)
    RIVER_LAYER_PATH = resolve_path.__func__(RIVER_LAYER_PATH_RAW)

    # Database (for PostGIS integration)
    DB_USER = os.getenv("DB_USER", "urbanshield")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "urbanshield_dev")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", 5432))
    DB_NAME = os.getenv("DB_NAME", "urbanshield_db")

    # Construct SQLAlchemy database URL for PostGIS
    @property
    def DATABASE_URL(self) -> str:
        """PostgreSQL connection string"""
        return (
            f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "./logs/urbanshield.log")

    @classmethod
    def get_log_file_path(cls) -> Path:
        """Get absolute path to log file, creating directory if needed"""
        log_path = cls.resolve_path(cls.LOG_FILE)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        return log_path


# Create a global config instance
config = Config()
