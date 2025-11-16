# AI Corporate Innovation — Workflow Automation

A LangGraph + FastAPI + Streamlit system for fully-automated corporate innovation analysis with human-in-the-loop controls.

This project is a full-stack AI-powered corporate innovation workflow engine designed to mimic the structured work of an innovation analyst, strategy consultant, or R&D foresight team. It automates the entire journey from insights → competencies → ideas → evaluation → action plans, while still allowing humans to refine and guide the process.

This README explains the project structure, how to run it, environment variables, endpoints, Streamlit UI usage, and troubleshooting tips.


## Quick summary


*   Backend: **FastAPI** + **Uvicorn**
    
*   Orchestration / workflow engine: **LangGraph** (StateGraph API, v0.3.12 tested)
    
*   Vector search: **ChromaDB** (local persistence)
    
*   DB: **MongoDB** (for storing session artifacts)
    
*   LLM: **Google Gemini-2.5-Pro** (via google-genai SDK) with fallback to Tavily search for web snippets (if TAVILY\_API\_KEY provided)
    
*   Frontend: **Streamlit** app with SSE client for live logs/streaming
    
*   Data processing: **pandas**, CSV utilities, and custom node functions (under src/nodes)
    


## Getting started (development)


> These instructions target a Windows development environment (using PowerShell), but the commands are similar on macOS/Linux.

1.  Clone project and cd into repository root (the folder that contains src/).
    
2.  Create and activate a virtual environment:
    
```bash
# create
python -m venv .venv

# PowerShell (activate)
.\.venv\Scripts\Activate.ps1

# or CMD
.\.venv\Scripts\activate

# or Bash (mac/linux)
source .venv/bin/activate
```


3.  Install dependencies (requirements.txt):
    
```txt
fastapi
uvicorn[standard]
langgraph==0.3.12
pymongo
python-dotenv
requests
streamlit
pandas
chromadb
google-genai
xxhash
```

Install:

```bash
pip install -r requirements.txt
```

4.  Create a .env file in project root with these variables:
    
```ini    
MONGO_URI=mongodb+srv://username:Password@cluster0.....
GEMINI_API_KEY=......
GEMINI_MODEL=gemini-2.5-pro        # optional; default in code if unset
TAVILY_API_KEY=tvly....   # optional (preferred for web search)
FASTAPI_URL=http://127.0.0.1:8000 # used by Streamlit by default
CHROMA_DIR=./chroma_db
```

5.  Ensure artifacts/ directory exists (backend will create it automatically on startup).
    


## Run backend (FastAPI)


From project root (so src is a package sibling), run:

```bash
# run FastAPI
uvicorn src.main:app --reload
```

*   Make sure you run uvicorn from the project root. The import path src.main:app assumes your working directory contains src/.
    
*   The server will be available at http://127.0.0.1:8000. Docs: http://127.0.0.1:8000/docs.
    

## Run Streamlit UI (in separate terminal)

Open a second terminal window (you must activate the same .venv) and run:

```bash
.\.venv\Scripts\Activate.ps1
streamlit run src/streaming/streamlit_app.py
```


Streamlit will open at http://localhost:8501. The Streamlit UI calls the FastAPI endpoints and listens to SSE streams for live logs.



## Project structure & brief file descriptions

```graphql
.
├─ src/
│  ├─ main.py                    # FastAPI app — HTTP endpoints that call/drive the LangGraph workflow
│  ├─ workflow.py                # LangGraph StateGraph builder & compiled app_graph
│  ├─ nodes/
│  │  ├─ search_agent.py         # Tavily search + fallback Gemini synthetic snippets
│  │  ├─ competency_extractor.py # Uses Gemini to extract structured competencies and stores to Mongo
│  │  ├─ gap_analyzer.py         # Generates clarifying questions
│  │  ├─ idea_generator.py       # Generates ideas from competencies and stores to Mongo
│  │  ├─ idea_selector.py        # Scoring + selection logic (reads evaluation CSV)
│  │  ├─ template_generator.py   # Builds evaluation template CSV from ideas
│  │  ├─ score_validator.py      # Validator for evaluation CSV
│  │  ├─ action_plan_writer.py   # Renders selected ideas into action-plan files
│  │  ├─ semantic_reasoner.py    # Retrieves relevant_competencies
│  │  ├─ analogy_finder.py       # Finds analogies for generating ideas
│  ├─ utils/
│  │  └─ csv_utils.py            # generate/validate CSV helpers
│  ├─ db/
│  │  └─ mongo.py                # Mongo client helper
│  ├─ gemini_client.py           # thin wrapper for google-genai usage + JSON extraction helpers
│  ├─ vectorstore.py             # chroma db wrapper helpers
│  ├─ streaming/
│  │  ├─ streamlit_app.py        # Streamlit UI that drives the workflow and listens for SSE
│  │  └─ sse_utils.py            # small SSE client (generator) used by Streamlit
│  └─ schemas.py                 # pydantic shapes & schema helpers
├─ artifacts/                    # generated CSVs, idea maps, action plans (created at runtime)
└─ requirements.txt
```


## API Reference (important endpoints)

> All endpoints are mounted under / in src/main.py.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/sessions` | Start new session and run workflow up to gap analysis |
| POST | `/sessions/{session_id}/answer_gaps` | Provide clarifying answers |
| GET | `/sessions/{session_id}/download_competencies` | Download competencies CSV |
| POST | `/sessions/{session_id}/upload_csv` | Upload edited competencies CSV |
| POST | `/sessions/{session_id}/generate_ideas` | Generate ideas from stored competencies |
| GET | `/sessions/{session_id}/download_idea_map` | Download idea map CSV |
| POST | `/sessions/{session_id}/generate_template` | Generate evaluation template CSV |
| GET | `/sessions/{session_id}/download_template` | Download evaluation template |
| POST | `/sessions/{session_id}/upload_evaluation` | Upload filled evaluation CSV |
| POST | `/sessions/{session_id}/validate_scores` | Validate evaluation CSV and select top ideas |
| POST | `/sessions/{session_id}/generate_action_plans` | Generate action-plan MD from selected ideas |
| GET | `/sessions/{session_id}/download_action_plans` | Download action plans (.md) |
| GET | `/sessions/{session_id}/debug` | Return raw session state for debugging |
| GET | `/sessions/{session_id}/stream` | SSE streaming endpoint for live progress |
    

## Streamlit UI notes

*   The UI mirrors backend endpoints and streams the backend log for user feedback. It does the following:
    
    *   Start a session (calls POST /sessions) and displays SSE stream.
        
    *   Show extracted competencies and gap questions; supports iterative clarifications.
        
    *   Upload edited competency CSV (validates on server and persists to Mongo).
        
    *   Generate idea map, evaluation template, upload evaluation, validate/select top ideas, and generate action plans.
        
*   The Streamlit app expects the FastAPI backend to be reachable at FASTAPI\_URL (default http://127.0.0.1:8000) — you can override via .env or env var prior to launching Streamlit.
    
    

## Important development & troubleshooting tips

1.  If you must run from src/streaming (not recommended), add a PYTHONPATH insertion at top of streamlit\_app.py:

```bash
import sys, os
ROOT = os.path.abspath(os.path.join(os.path.dirname(\_\_file\_\_), "..", ".."))
sys.path.insert(0, ROOT)
```
```bash
    *   uvicorn src.main:app --reload
    *   streamlit run src/streaming/streamlit_app.py
```
        
2.  **LangGraph imports** — the code uses langgraph.graph.StateGraph (tested with langgraph==0.3.12). If you get ImportError: cannot import name 'Graph' or similar, check installed langgraph version and imports. Use the version that matches the API used in workflow.py.
    
3.  **SSE long-running tasks** — long-running LLM calls (Gemini) may take time. SSE endpoint should flush progress. The Streamlit SSE client respects a \[\[STREAM\_END\]\] marker to stop streaming. If you see the Streamlit spinner never stop, check that the backend sends the end marker or that the stream implementation returns naturally.
    
4.  **Timeouts on the client** — requests default read timeout can cause Read timed out if the server takes longer. Increase client timeout for upload/generate actions if needed. The backend endpoints may also need to be configured to allow longer worker timeouts.
    
5.  **Technology-level categories** — if you want AI outputs to conform to an allowed set (Basic, Intermediate, Advanced, Cutting-edge, etc.), change the extractor prompts to ask the model to choose one of those exact tokens and validate/normalize returned values before inserting to Mongo. (The project already includes this - competency\_extractor.py.)
    
6.  **Streamlit API changes** — if you see AttributeError: module 'streamlit' has no attribute 'experimental\_rerun', upgrade/downgrade Streamlit or use recommended replacement st.experimental\_rerun() vs st.experimental\_request\_rerun() depending on version. Current code avoids calling deprecated functions.
    
7.  **Windows PowerShell ExecutionPolicy** — PowerShell may refuse to run activation script. If so, run:
    
```bash
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

then activate venv.


## Example end-to-end flow

1.  Start backend: uvicorn src.main:app --reload
    
2.  Start UI: streamlit run src/streaming/streamlit\_app.py
    
3.  In the Streamlit UI → Workflow page:
    
    *   Enter company name (e.g. Apple, Microsoft, Google, Meta, Huawei, Tesla) → Start Session and Stream
        
    *   Observe live log; when gap questions show, go to next page
        
    *   Answer questions (or leave answers blank to signal COMPLETE)
        
    *   Download competencies CSV or upload an edited CSV
        
    *   Generate ideas → Download idea map
        
    *   Generate evaluation template → fill offline and upload evaluation
        
    *   Validate & select top ideas → generate action plans → download
        