"""
UrbanShield - AI Infrastructure Investigation Assistant
---------------------------------------------------------------
A tool-using LLM agent that lets engineers ask natural-language
questions about infrastructure risk and get grounded answers pulled
live from the UrbanShield API (never hallucinated numbers — every
answer is backed by a tool call).

Example questions it can answer:
  "Which water pipelines are at critical risk?"
  "What's driving the risk score for AST-00109?"
  "Show me the top 10 maintenance priorities within our current budget of 15 crews"
  "Are there any hotspots near latitude 17.42, longitude 78.47?"

This uses LangChain's tool-calling agent pattern (matches the stack
already used in the Land Document Assistant / RAG projects). Requires
an LLM API key (OpenAI/Anthropic) — set via environment variable.

Run:
    export ANTHROPIC_API_KEY=...   # or OPENAI_API_KEY
    python agent.py "Which bridges are highest risk right now?"
"""

import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

API_BASE = os.environ.get("URBANSHIELD_API", "http://localhost:8000")


# ---------------------------------------------------------------
# Tools — thin wrappers around the FastAPI backend. The agent can
# only answer using data these tools return, which is what keeps
# it grounded instead of guessing numbers.
# ---------------------------------------------------------------
@tool
def list_high_risk_assets(asset_type: str = "", risk_tier: str = "high") -> str:
    """Get a list of infrastructure assets filtered by type and/or risk tier
    (low, medium, high, critical). Leave asset_type empty for all types.
    asset_type options: road_segment, bridge, water_pipeline, power_pole, stormwater_drain."""
    params = {"risk_tier": risk_tier, "limit": 15}
    if asset_type:
        params["asset_type"] = asset_type
    r = requests.get(f"{API_BASE}/assets", params=params, timeout=10)
    r.raise_for_status()
    assets = r.json()
    if not assets:
        return "No assets found matching that filter."
    lines = [
        f"{a['asset_id']} ({a['asset_type']}, {a['material']}) - risk {a['risk_score']:.2f} [{a['risk_tier']}]"
        for a in assets
    ]
    return "\n".join(lines)


@tool
def explain_asset_risk(asset_id: str) -> str:
    """Get a plain-language explanation of WHY a specific asset has its risk score,
    including the top contributing factors. Use the exact asset_id, e.g. AST-00109."""
    r = requests.get(f"{API_BASE}/assets/{asset_id}/explain", timeout=10)
    if r.status_code == 404:
        return f"No asset found with ID {asset_id}."
    r.raise_for_status()
    return r.json()["explanation"]


@tool
def find_nearby_risk(latitude: float, longitude: float, radius_m: float = 500) -> str:
    """Find infrastructure assets near a given latitude/longitude within radius_m meters,
    sorted by risk score descending."""
    params = {"lat": latitude, "lon": longitude, "radius_m": radius_m}
    r = requests.get(f"{API_BASE}/nearby", params=params, timeout=10)
    r.raise_for_status()
    assets = r.json()
    if not assets:
        return "No assets found in that radius."
    lines = [
        f"{a['asset_id']} ({a['asset_type']}) - {a.get('distance_m','?')}m away, risk {a['risk_score']:.2f} [{a['risk_tier']}]"
        for a in assets[:10]
    ]
    return "\n".join(lines)


@tool
def get_hotspots() -> str:
    """Get a list of geographic hotspot zones where high/critical-risk assets are clustered.
    Useful for area-level (not single-asset) risk questions."""
    r = requests.get(f"{API_BASE}/hotspots", timeout=10)
    r.raise_for_status()
    zones = r.json()
    if not zones:
        return "No significant hotspot clusters detected."
    lines = [
        f"Zone near ({z['zone_center_lat']}, {z['zone_center_lon']}): "
        f"{z['asset_count']} assets, avg risk {z['avg_risk_score']:.2f}, mostly {z['dominant_type']}"
        for z in zones[:10]
    ]
    return "\n".join(lines)


@tool
def get_maintenance_priority_list(crew_slots: int = 20) -> str:
    """Get the top-priority assets for maintenance given a number of available crew slots,
    ranked by risk score. Use this when the user asks 'what should we fix first'."""
    r = requests.get(f"{API_BASE}/maintenance-priority", params={"budget_slots": crew_slots}, timeout=10)
    r.raise_for_status()
    assets = r.json()
    lines = [
        f"{i+1}. {a['asset_id']} ({a['asset_type']}) - risk {a['risk_score']:.2f}"
        for i, a in enumerate(assets)
    ]
    return "\n".join(lines)


@tool
def get_city_stats() -> str:
    """Get overall city-wide infrastructure risk statistics (totals by tier and type)."""
    r = requests.get(f"{API_BASE}/stats", timeout=10)
    r.raise_for_status()
    s = r.json()
    return (
        f"Total assets: {s['total_assets']}. "
        f"By risk tier: {s['by_tier']}. "
        f"Critical assets: {s['critical_count']}. "
        f"Average risk score: {s['avg_risk_score']:.3f}."
    )


TOOLS = [
    list_high_risk_assets,
    explain_asset_risk,
    find_nearby_risk,
    get_hotspots,
    get_maintenance_priority_list,
    get_city_stats,
]

SYSTEM_PROMPT = """You are the UrbanShield Infrastructure Investigation Assistant.
You help city engineers and planners understand infrastructure risk by querying
live risk-model data — you never invent numbers or asset IDs. Always call a tool
to get real data before answering a factual question. If a question is ambiguous
(e.g. no asset type given), ask a brief clarifying question OR default to showing
all types. Keep answers concise, engineer-facing, and cite specific asset IDs and
risk scores when relevant."""


class AgentAdapter:
    """Keep the existing input/output contract across LangChain versions."""

    def __init__(self, agent):
        self.agent = agent

    def invoke(self, payload):
        question = payload["input"]
        result = self.agent.invoke({"messages": [{"role": "user", "content": question}]})
        message = result["messages"][-1]
        content = message.content
        if isinstance(content, list):
            content = "".join(
                block.get("text", "") for block in content if isinstance(block, dict)
            )
        return {"output": content}


def build_agent():
    provider = os.environ.get("LLM_PROVIDER", "ollama").lower()
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        llm = ChatOllama(
            model=os.environ.get("OLLAMA_MODEL", "llama3.2"),
            temperature=0,
            base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key or api_key == "your_api_key_here":
            raise RuntimeError(
                "ANTHROPIC_API_KEY is missing. Add your key to the project .env file."
            )
        llm = ChatAnthropic(
            model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            temperature=0,
        )
    elif provider == "openai":
        from langchain_openai import ChatOpenAI

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key or api_key == "your_openai_api_key_here":
            raise RuntimeError(
                "OPENAI_API_KEY is missing. Add your key to the project .env file."
            )
        llm = ChatOpenAI(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0,
        )
    else:
        raise RuntimeError("LLM_PROVIDER must be 'ollama', 'openai', or 'anthropic'.")

    agent = create_agent(llm, tools=TOOLS, system_prompt=SYSTEM_PROMPT)
    return AgentAdapter(agent)


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "What's the overall city risk picture right now?"
    executor = build_agent()
    result = executor.invoke({"input": question})
    print("\n--- ANSWER ---")
    print(result["output"])
