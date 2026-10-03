#!/usr/bin/env python3
"""
UrbanShield AI Assistant Server
Provides a simple HTTP API for the AI chat interface to call.

Run:
    python ai_assistant/server.py
    
Then open: ai_assistant/chat.html in your browser
"""

import os
import re
import sys
from pathlib import Path

# Load project configuration before importing the agent.
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
load_dotenv(project_root / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import the agent builder
from ai_assistant.agent import (
    build_agent,
    explain_asset_risk,
    get_city_stats,
    get_hotspots,
    get_maintenance_priority_list,
    list_high_risk_assets,
)

app = FastAPI(title="UrbanShield AI Assistant Server")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global agent instance
agent_executor = None

class QuestionRequest(BaseModel):
    question: str

class AnswerResponse(BaseModel):
    answer: str
    success: bool = True


def data_backed_fallback(question: str) -> str:
    """Answer common demo questions from the live API if the LLM is unavailable."""
    normalized = question.lower()
    asset_match = re.search(r"\bAST-\d{5}\b", question, re.IGNORECASE)
    if asset_match:
        return explain_asset_risk.invoke({"asset_id": asset_match.group().upper()})

    if any(term in normalized for term in ("maintenance", "fix first", "priorit")):
        slots_match = re.search(r"\b(\d+)\s*(?:crews|slots|teams)\b", normalized)
        crew_slots = int(slots_match.group(1)) if slots_match else 20
        return get_maintenance_priority_list.invoke({"crew_slots": min(max(crew_slots, 1), 2500)})

    if "hotspot" in normalized:
        return get_hotspots.invoke({})

    asset_types = (
        "road_segment", "bridge", "water_pipeline", "power_pole", "stormwater_drain"
    )
    asset_type = next(
        (kind for kind in asset_types if kind in normalized or kind.replace("_", " ") in normalized),
        "",
    )
    if "critical" in normalized or "high risk" in normalized or asset_type:
        risk_tier = "critical" if "critical" in normalized else "high"
        return list_high_risk_assets.invoke({"asset_type": asset_type, "risk_tier": risk_tier})

    return get_city_stats.invoke({})


@app.on_event("startup")
async def startup():
    global agent_executor
    logger.info("Starting UrbanShield AI Assistant Server...")
    
    provider = os.environ.get("LLM_PROVIDER", "ollama").lower()
    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key or api_key == "your_api_key_here":
            logger.error("ANTHROPIC_API_KEY is not set for the Anthropic provider")
            return
    elif provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key or api_key == "your_openai_api_key_here":
            logger.error("OPENAI_API_KEY is not set for the OpenAI provider")
            return
    elif provider != "ollama":
        logger.error("LLM_PROVIDER must be 'ollama', 'openai', or 'anthropic'")
        return
    
    try:
        agent_executor = build_agent()
        logger.info("✅ AI Agent initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize agent: {e}")
        raise

@app.get("/health")
async def health():
    return {"status": "ok", "service": "UrbanShield AI Assistant"}

@app.post("/ask", response_model=AnswerResponse)
async def ask(request: QuestionRequest):
    """Ask the AI assistant a question about infrastructure."""
    
    if not agent_executor:
        return AnswerResponse(
            answer="❌ AI Assistant not initialized. Make sure ANTHROPIC_API_KEY is set in .env",
            success=False
        )
    
    try:
        logger.info(f"Question: {request.question}")
        result = agent_executor.invoke({"input": request.question})
        answer = result.get("output", "No response generated")
        logger.info(f"Answer: {answer[:100]}...")
        
        return AnswerResponse(answer=answer, success=True)
    
    except Exception as e:
        logger.warning("LLM request failed; using data-backed fallback: %s", e)
        try:
            answer = data_backed_fallback(request.question)
            return AnswerResponse(
                answer=f"AI model unavailable; data-backed result:\n\n{answer}",
                success=True,
            )
        except Exception:
            logger.exception("Data-backed assistant fallback failed")
            return AnswerResponse(
                answer="The assistant is temporarily unavailable. The dashboard and API are still online.",
                success=False,
            )

if __name__ == "__main__":
    import uvicorn
    
    logger.info("=" * 60)
    logger.info("UrbanShield AI Assistant Server")
    logger.info("=" * 60)
    
    provider = os.environ.get("LLM_PROVIDER", "ollama").lower()
    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key or api_key == "your_api_key_here":
            print("\n❌ ANTHROPIC_API_KEY not set for the Anthropic provider!")
            print("Use LLM_PROVIDER=ollama for the free local provider.")
            sys.exit(1)
        print("\n✅ Anthropic provider configured!")
    else:
        print(f"\n✅ {provider} provider configured!")
    print("\n📍 AI Assistant Server running on http://localhost:8001")
    print("📍 Chat interface: file:///.../ai_assistant/chat.html")
    print("📍 API endpoint: http://localhost:8001/ask")
    print("\nPress CTRL+C to stop")
    print("=" * 60 + "\n")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        log_level="info"
    )
