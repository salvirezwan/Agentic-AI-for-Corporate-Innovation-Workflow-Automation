# src/main.py
import os
import uuid
import io
import logging

from fastapi.responses import StreamingResponse
import time
import json

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from dotenv import load_dotenv

from src.workflow import app_graph
from src.utils.csv_utils import (
    validate_csv_file,
    generate_competency_csv,
    generate_idea_map_csv,
    generate_evaluation_template_csv
)
from src.nodes.score_validator import validate_evaluation_csv
from src.nodes.idea_selector import score_and_select_top
from src.nodes.action_plan_writer import generate_action_plans
from src.db.mongo import get_collection

# ---------------------------------------------------------
# Initialize Logging for Streaming Log Capture
# ---------------------------------------------------------
log_stream = io.StringIO()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("workflow")

# Remove existing handlers so logs don't duplicate
for h in logger.handlers:
    logger.removeHandler(h)

stream_handler = logging.StreamHandler(log_stream)
stream_handler.setLevel(logging.INFO)
logger.addHandler(stream_handler)

# ---------------------------------------------------------

load_dotenv()

app = FastAPI(title="AI Corporate Innovation Workflow Automation")

ARTIFACTS_DIR = os.path.join(os.getcwd(), "artifacts")
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

sessions = {}

# ---------------------------------------------------------
# Streaming Logs Endpoint  (for Streamlit SSE-style streaming)
# ---------------------------------------------------------
@app.get("/logs")
def fetch_logs():
    """Return accumulated workflow logs for SSE-style streaming."""
    return {"logs": log_stream.getvalue()}


# ---------------------------------------------------------
# Start Session
# ---------------------------------------------------------
@app.post("/sessions")
def start_session(payload: dict):
    """
    Start the workflow but STOP after gap analysis (human-in-the-loop).
    Uses LangGraph invoke with interrupt_before to pause prior to idea generation.
    """
    try:
        session_id = str(uuid.uuid4())
        logger.info(f"=== Starting session {session_id} for company: {payload['company_name']} ===")

        input_state = {"company_name": payload["company_name"], "session_id": session_id}

        # Run graph until ask_gaps → pause before generate_ideas
        try:
            logger.info("Invoking graph up to gap analysis…")
            result_state = app_graph.invoke(input_state, interrupt_before=["generate_ideas"])
        except TypeError:
            logger.info("LangGraph version fallback invoke()")
            result_state = app_graph.invoke(input_state)

        # Store session minimal fields
        sessions[session_id] = {"company_name": payload["company_name"], "session_id": session_id}

        if isinstance(result_state, dict):
            sessions[session_id].update(result_state)
        else:
            try:
                sessions[session_id].update(getattr(result_state, "state", {}) or getattr(result_state, "result", {}))
            except Exception:
                pass

        logger.info(f"Extracted {len(sessions[session_id].get('extracted_competencies', []))} competencies")
        logger.info(f"Generated {len(sessions[session_id].get('gap_questions', []))} gap questions")

        return {
            "session_id": session_id,
            "discovered_competencies": sessions[session_id].get("extracted_competencies", []),
            "gap_questions": sessions[session_id].get("gap_questions", [])
        }

    except Exception as e:
        logger.error(f"Error in start_session: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ---------------------------------------------------------
# Answer Gaps (human clarifications)
# ---------------------------------------------------------
@app.post("/sessions/{session_id}/answer_gaps")
def answer_gaps(session_id: str, payload: dict):
    try:
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")

        logger.info(f"=== Processing clarifications for session {session_id} ===")

        # COMPLETE token — finalize CSV
        if payload.get("status", "").strip().upper() == "COMPLETE":
            refined = sessions[session_id].get("extracted_competencies", [])
            csv_path = generate_competency_csv(session_id, refined, ARTIFACTS_DIR)

            sessions[session_id]["generated_csv"] = csv_path
            sessions[session_id]["state"] = "competency_csv_ready"

            logger.info("User marked COMPLETE. Competencies finalized.")
            return {
                "message": "Competencies finalized — CSV generated",
                "csv_path": csv_path,
                "download_endpoint": f"/sessions/{session_id}/download_competencies",
                "loop": "complete"
            }

        # Otherwise expect answers[]
        answers = payload.get("answers", [])
        if not isinstance(answers, list):
            raise HTTPException(status_code=400, detail="answers must be an array")

        sessions[session_id]["answers"] = answers
        logger.info(f"Received {len(answers)} clarification answers")

        # Resume graph
        try:
            resumed = app_graph.invoke(
                {**sessions[session_id], "session_id": session_id},
                interrupt_before=["generate_ideas"]
            )
        except TypeError:
            resumed = app_graph.invoke({**sessions[session_id], "session_id": session_id})

        if isinstance(resumed, dict):
            sessions[session_id].update(resumed)

        gap_questions = sessions[session_id].get("gap_questions", [])

        if gap_questions:
            logger.info(f"{len(gap_questions)} more gap questions remain")
            return {
                "message": "More information required",
                "discovered_competencies": sessions[session_id].get("extracted_competencies", []),
                "gap_questions": gap_questions,
                "loop": "continue"
            }

        # No more gaps -> finalize
        refined = sessions[session_id].get("extracted_competencies", [])
        csv_path = generate_competency_csv(session_id, refined, ARTIFACTS_DIR)
        sessions[session_id]["generated_csv"] = csv_path
        sessions[session_id]["state"] = "competency_csv_ready"

        logger.info("All gaps resolved. CSV finalized.")
        return {
            "message": "Competencies finalized — CSV generated",
            "csv_path": csv_path,
            "download_endpoint": f"/sessions/{session_id}/download_competencies",
            "loop": "complete"
        }

    except Exception as e:
        logger.error(f"Error in answer_gaps: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ---------------------------------------------------------
# Download Competencies
# ---------------------------------------------------------
@app.get("/sessions/{session_id}/download_competencies")
def download_competencies(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    if "generated_csv" not in sessions[session_id]:
        comps = sessions[session_id].get("extracted_competencies", [])
        sessions[session_id]["generated_csv"] = generate_competency_csv(
            session_id, comps, ARTIFACTS_DIR
        )

    return FileResponse(
        sessions[session_id]["generated_csv"],
        media_type="text/csv",
        filename=os.path.basename(sessions[session_id]["generated_csv"])
    )


# ---------------------------------------------------------
# Upload CSV
# ---------------------------------------------------------
@app.post("/sessions/{session_id}/upload_csv")
async def upload_csv(session_id: str, file: UploadFile = File(...)):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    dest = os.path.join(ARTIFACTS_DIR, f"{session_id}_competencies_uploaded.csv")
    with open(dest, "wb") as f:
        f.write(await file.read())

    ok, msg = validate_csv_file(dest)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    # Persist rows to Mongo
    col = get_collection("competencies")
    col.delete_many({"session_id": session_id})

    import pandas as pd
    df = pd.read_csv(dest)
    docs = []
    for _, r in df.iterrows():
        docs.append({
            "_id": str(uuid.uuid4()),
            "session_id": session_id,
            "category": r["Category"],
            "competency": r["Competency"],
            "description": r["Description"],
            "technology_level": r["Technology Level"],
            "source_url": r.get("Source URL", "")
        })

    if docs:
        col.insert_many(docs)

    sessions[session_id]["uploaded_csv"] = dest
    sessions[session_id]["state"] = "competencies_validated"
    logger.info("Uploaded and validated CSV")
    return {"status": "uploaded_validated", "file": dest}


# ---------------------------------------------------------
# Generate Ideas
# ---------------------------------------------------------
@app.post("/sessions/{session_id}/generate_ideas")
def generate_ideas_endpoint(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    logger.info("Generating ideas…")

    ideas = sessions[session_id].get("generated_ideas")
    if not ideas:
        # Resume into generate_ideas
        try:
            resumed = app_graph.invoke(
                sessions[session_id],
                interrupt_before=["generate_template"]
            )
        except TypeError:
            resumed = app_graph.invoke(sessions[session_id])

        if isinstance(resumed, dict):
            sessions[session_id].update(resumed)

        ideas = sessions[session_id].get("generated_ideas", [])

    csv_path = generate_idea_map_csv(session_id, ideas, ARTIFACTS_DIR)
    sessions[session_id]["idea_map_csv"] = csv_path
    sessions[session_id]["state"] = "ideas_generated"

    logger.info(f"Generated {len(ideas)} ideas")
    return {"message": "Generated ideas", "num_ideas": len(ideas), "idea_map": csv_path}


@app.get("/sessions/{session_id}/download_idea_map")
def download_idea_map(session_id: str):
    if session_id not in sessions or "idea_map_csv" not in sessions[session_id]:
        raise HTTPException(status_code=404, detail="Idea map not found")

    return FileResponse(
        sessions[session_id]["idea_map_csv"],
        media_type="text/csv",
        filename=os.path.basename(sessions[session_id]["idea_map_csv"])
    )


# ---------------------------------------------------------
# Generate Evaluation Template
# ---------------------------------------------------------
@app.post("/sessions/{session_id}/generate_template")
def generate_template_endpoint(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    ideas = sessions[session_id].get("generated_ideas", [])
    path = generate_evaluation_template_csv(session_id, ideas, ARTIFACTS_DIR)

    sessions[session_id]["evaluation_template"] = path
    sessions[session_id]["state"] = "evaluation_template_generated"

    logger.info("Evaluation template generated")
    return {
        "message": "Evaluation template generated",
        "template_path": path,
        "download_endpoint": f"/sessions/{session_id}/download_template"
    }


@app.get("/sessions/{session_id}/download_template")
def download_template(session_id: str):
    if session_id not in sessions or "evaluation_template" not in sessions[session_id]:
        raise HTTPException(status_code=404, detail="Template not found")

    return FileResponse(
        sessions[session_id]["evaluation_template"],
        media_type="text/csv",
        filename=os.path.basename(sessions[session_id]["evaluation_template"])
    )


# ---------------------------------------------------------
# Upload Evaluation CSV
# ---------------------------------------------------------
@app.post("/sessions/{session_id}/upload_evaluation")
async def upload_evaluation(session_id: str, file: UploadFile = File(...)):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    dest = os.path.join(ARTIFACTS_DIR, f"{session_id}_evaluation_uploaded.csv")
    with open(dest, "wb") as f:
        f.write(await file.read())

    ok, msg = validate_evaluation_csv(dest)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    sessions[session_id]["evaluation_csv"] = dest
    sessions[session_id]["state"] = "evaluation_uploaded"

    logger.info("Uploaded evaluation CSV")
    return {"status": "evaluation_uploaded", "file": dest}


# ---------------------------------------------------------
# Validate Scores & Select Top Ideas
# ---------------------------------------------------------
# @app.post("/sessions/{session_id}/validate_scores")
# def validate_and_select(session_id: str, top_k: int = 3):
#     if session_id not in sessions:
#         raise HTTPException(status_code=404, detail="Session not found")

#     eval_path = sessions[session_id].get("evaluation_csv")
#     if not eval_path:
#         raise HTTPException(status_code=400, detail="No evaluation CSV uploaded")

#     logger.info("Selecting top ideas…")
#     selected = score_and_select_top(session_id, eval_path, top_k=top_k)

#     sessions[session_id]["selected_ideas"] = selected
#     sessions[session_id]["state"] = "ideas_selected"

#     return {"message": "Scores validated; top ideas selected", "selected": selected}

from fastapi import Body

@app.post("/sessions/{session_id}/validate_scores")
def validate_and_select(
    session_id: str,
    payload: dict = Body(...)
):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    # Extract top_k safely from JSON
    top_k = int(payload.get("top_k", 3))

    eval_path = sessions[session_id].get("evaluation_csv")
    if not eval_path:
        raise HTTPException(status_code=400, detail="No evaluation CSV uploaded")

    logger.info(f"Selecting top {top_k} ideas…")

    selected = score_and_select_top(session_id, eval_path, top_k=top_k)

    sessions[session_id]["selected_ideas"] = selected
    sessions[session_id]["state"] = "ideas_selected"

    return {
        "message": f"Scores validated; top {top_k} ideas selected",
        "selected": selected
    }



# ---------------------------------------------------------
# Generate Action Plans
# ---------------------------------------------------------
@app.post("/sessions/{session_id}/generate_action_plans")
def generate_action_plans_endpoint(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    selected = sessions[session_id].get("selected_ideas")
    if not selected:
        raise HTTPException(status_code=400, detail="No selected ideas; run validate_scores first")

    path = generate_action_plans(session_id, selected, ARTIFACTS_DIR)
    sessions[session_id]["action_plan_file"] = path
    sessions[session_id]["state"] = "action_plans_generated"

    logger.info("Generated action plans")
    return {"message": "Action plans generated",
            "download_endpoint": f"/sessions/{session_id}/download_action_plans"}


@app.get("/sessions/{session_id}/download_action_plans")
def download_action_plans(session_id: str):
    if session_id not in sessions or "action_plan_file" not in sessions[session_id]:
        raise HTTPException(status_code=404, detail="Action plan not found")

    return FileResponse(
        sessions[session_id]["action_plan_file"],
        media_type="text/markdown",
        filename=os.path.basename(sessions[session_id]["action_plan_file"])
    )


# ---------------------------------------------------------
# Debug Endpoint
# ---------------------------------------------------------
@app.get("/sessions/{session_id}/debug")
def get_debug(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return sessions[session_id]



@app.get("/sessions/{session_id}/stream")
def stream_session(session_id: str):
    """
    SSE endpoint: streams the graph progress up to gap analysis.
    """

    if session_id not in sessions:
        return StreamingResponse(
            (line for line in ["event: error\ndata: Session not found\n\n"]),
            media_type="text/event-stream"
        )

    def event_stream():
        yield "data: === Starting session {} ===\n\n".format(session_id)
        time.sleep(0.3)

        # Log search stage
        yield "data: Running search...\n\n"
        time.sleep(0.3)

        # Already stored in session from /sessions call
        comps = sessions[session_id].get("extracted_competencies", [])
        yield f"data: Extracted {len(comps)} competencies\n\n"
        time.sleep(0.3)

        # Gap questions
        gaps = sessions[session_id].get("gap_questions", [])
        yield f"data: Generated {len(gaps)} gap questions\n\n"
        time.sleep(0.3)

        # Final signal for stream end
        yield "data: [[STREAM_END]]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
