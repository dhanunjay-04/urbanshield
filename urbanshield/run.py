#!/usr/bin/env python3
"""
UrbanShield Data Pipeline Orchestrator
========================================
Runs the complete data generation, model training, and API startup workflow.

Usage:
    python run.py                    # Run everything
    python run.py --generate-only    # Only generate data
    python run.py --train-only       # Only train model (requires generated data)
    python run.py --serve-only       # Only start API (requires trained model)
"""

import os
import sys
import subprocess
import argparse
import logging
from pathlib import Path


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent


def run_command(cmd, description, cwd=None):
    """Execute a shell command and log output"""
    logger.info(f"Starting: {description}")
    logger.debug(f"Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or PROJECT_ROOT,
            capture_output=False,
            text=True,
        )
        
        if result.returncode != 0:
            logger.error(f"Failed: {description} (exit code {result.returncode})")
            return False
        
        logger.info(f"Completed: {description}")
        return True
    except Exception as e:
        logger.error(f"Exception during {description}: {e}")
        return False


def check_file_exists(path, description):
    """Check if required file exists"""
    if not path.exists():
        logger.error(f"Missing: {description} at {path}")
        return False
    logger.info(f"Found: {description}")
    return True


def generate_data():
    """Run data generation script"""
    data_script = PROJECT_ROOT / "data" / "generate_synthetic_data.py"
    
    if not check_file_exists(data_script, "Data generation script"):
        return False
    
    return run_command(
        [sys.executable, str(data_script)],
        "Generate synthetic data (roads, assets, river)",
    )


def train_model():
    """Run model training script"""
    ml_script = PROJECT_ROOT / "ml" / "train_risk_model.py"
    assets_csv = PROJECT_ROOT / "db" / "assets.csv"
    
    if not check_file_exists(ml_script, "Training script"):
        return False
    
    if not check_file_exists(assets_csv, "Generated assets data"):
        logger.error("Generate data first with: python run.py --generate-only")
        return False
    
    return run_command(
        [sys.executable, str(ml_script)],
        "Train risk model (Gradient Boosting + SHAP explanations)",
    )


def serve_api(host="0.0.0.0", port=8000, reload=True):
    """Start the FastAPI server"""
    api_script = PROJECT_ROOT / "backend" / "main.py"
    scored_csv = PROJECT_ROOT / "db" / "assets_scored.csv"
    
    if not check_file_exists(api_script, "API script"):
        return False
    
    if not check_file_exists(scored_csv, "Scored assets data"):
        logger.error("Train model first with: python run.py --train-only")
        return False
    
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.main:app",
        "--host", host,
        "--port", str(port),
    ]
    
    if reload:
        cmd.append("--reload")
    
    logger.info(f"Starting API server at http://{host}:{port}")
    logger.info("Press Ctrl+C to stop")
    logger.info("API docs available at http://localhost:8000/docs")
    
    return run_command(cmd, "Start FastAPI server")


def main():
    parser = argparse.ArgumentParser(
        description="UrbanShield Data Pipeline Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                        # Full pipeline: generate → train → serve
  python run.py --generate-only        # Only generate synthetic data
  python run.py --train-only          # Only train model (requires generated data)
  python run.py --serve-only          # Only start API (requires trained model)
  python run.py --no-reload           # Start API without hot-reload
        """,
    )
    
    parser.add_argument(
        "--generate-only",
        action="store_true",
        help="Only run data generation"
    )
    parser.add_argument(
        "--train-only",
        action="store_true",
        help="Only run model training"
    )
    parser.add_argument(
        "--serve-only",
        action="store_true",
        help="Only start the API server"
    )
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Disable hot-reload for API server"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="API host (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="API port (default: 8000)"
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("UrbanShield Data Pipeline")
    logger.info("=" * 60)
    
    # Check Python version
    if sys.version_info < (3, 9):
        logger.error("Python 3.9+ required")
        return 1
    
    # Determine what to run
    run_generate = True
    run_train = True
    run_serve = True
    
    if args.generate_only:
        run_generate = True
        run_train = False
        run_serve = False
    elif args.train_only:
        run_generate = False
        run_train = True
        run_serve = False
    elif args.serve_only:
        run_generate = False
        run_train = False
        run_serve = True
    
    # Execute pipeline
    try:
        if run_generate:
            if not generate_data():
                return 1
        
        if run_train:
            if not train_model():
                return 1
        
        if run_serve:
            if not serve_api(
                host=args.host,
                port=args.port,
                reload=not args.no_reload
            ):
                return 1
    
    except KeyboardInterrupt:
        logger.info("\nPipeline interrupted by user")
        return 0
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
