# UrbanShield AI Assistant Setup Guide

## Quick Start (free local setup)

### Step 1: Install Ollama

1. Install Ollama from https://ollama.com/download/windows
2. Download the model:

```powershell
ollama pull llama3.2
```

### Step 2: Configure `.env`

Edit `urbanshield/.env` and add:

```env
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2
```

### Step 3: Run the AI Assistant

**Option A: Command Line (Simplest)**

```bash
cd urbanshield

# Start Ollama in another terminal first
ollama serve

# Ask a question directly
python ai_assistant/agent.py "Which bridges are at critical risk?"

# More examples:
python ai_assistant/agent.py "What's the overall city risk picture?"
python ai_assistant/agent.py "Show me the top 10 maintenance priorities"
python ai_assistant/agent.py "Find high-risk assets near latitude 17.25, longitude 80.15"
python ai_assistant/agent.py "Explain the risk for AST-00109"
```

**Option B: Web Chat Interface**

Terminal 1 - Start the AI server:
```bash
cd urbanshield
python ai_assistant/server.py
```

Terminal 2 - Open the chat:
```bash
# On Windows
start ai_assistant\chat.html

# On Mac
open ai_assistant/chat.html

# On Linux
xdg-open ai_assistant/chat.html
```

Or open in browser: `file:///path/to/urbanshield/ai_assistant/chat.html`

---

## Example Questions

The AI assistant can answer questions like:

**Asset Queries:**
- "Which water pipelines are at critical risk?"
- "Show me all road_segment assets with high risk"
- "What bridges have the highest risk scores?"

**Explanations:**
- "Why is AST-00109 at risk?"
- "What's driving the risk for AST-01552?"
- "Explain the top 3 risk factors for AST-00835"

**Geographic Queries:**
- "Find high-risk assets near latitude 17.25, longitude 80.15"
- "Are there any hotspots in the downtown area?"
- "What's the average risk within 1km of the city center?"

**Maintenance Planning:**
- "Show me the top 20 maintenance priorities"
- "Which 5 assets should we fix first with limited budget?"
- "What's our overall city risk picture?"

**Statistics:**
- "How many critical assets do we have?"
- "What's the average risk score?"
- "How many road segments are failing?"

---

## Features

✅ **Grounded Answers** - All responses backed by live API calls (no hallucination)
✅ **Multi-Tool** - Accesses all UrbanShield API endpoints
✅ **Natural Language** - Ask in plain English, get structured answers
✅ **Explainability** - Understand WHY assets are risky
✅ **Maintenance Prioritization** - Get ranked maintenance plans

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'langchain_anthropic'"

**Solution:** Install missing dependencies:
```bash
pip install langchain-anthropic langchain-core
```

### "ANTHROPIC_API_KEY not found"

**Solution:** Make sure to add your key to `.env`:
```bash
ANTHROPIC_API_KEY=sk-ant-your-actual-key
```

Or set as environment variable:
```bash
# Windows
set ANTHROPIC_API_KEY=sk-ant-your-key

# Mac/Linux
export ANTHROPIC_API_KEY=sk-ant-your-key
```

### "Connection refused" on web chat

**Solution:** Make sure the AI server is running:
```bash
python ai_assistant/server.py
```

It should show:
```
✅ ANTHROPIC_API_KEY found!
📍 AI Assistant Server running on http://localhost:8001
```

### "No assets found" responses

**Solution:** Make sure the main UrbanShield API is running:
```bash
python startup.py
```

Check it's working:
```bash
curl http://localhost:8000/stats
```

---

## Architecture

```
┌──────────────────────────────┐
│  Web Browser                 │
│  (chat.html)                 │
└──────────┬───────────────────┘
           │
           │ HTTP POST /ask
           ▼
┌──────────────────────────────┐
│  AI Assistant Server         │
│  (server.py on port 8001)    │
│  - Runs LangChain agent      │
│  - Manages tools             │
└──────────┬───────────────────┘
           │
           │ REST API calls
           ▼
┌──────────────────────────────┐
│  UrbanShield FastAPI         │
│  (main.py on port 8000)      │
│  - /assets                   │
│  - /nearby                   │
│  - /hotspots                 │
│  - /stats                    │
│  - /explain                  │
└──────────────────────────────┘
```

---

## What to Do Next

1. ✅ Add `ANTHROPIC_API_KEY` to `.env`
2. ✅ Test with CLI: `python ai_assistant/agent.py "question"`
3. ✅ Try web chat: `python ai_assistant/server.py` + open `chat.html`
4. ✅ Integrate into your infrastructure workflows

---

**Questions?** Check the agent.py file for the full list of available tools!
