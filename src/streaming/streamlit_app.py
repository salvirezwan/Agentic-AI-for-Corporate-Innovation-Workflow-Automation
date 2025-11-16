# src/streaming/streamlit_app.py
import sys
import os
from fastapi import Body

# Absolute path: /your-project-root/
CURRENT_FILE = os.path.abspath(__file__)                      # .../src/streaming/streamlit_app.py
STREAMING_DIR = os.path.dirname(CURRENT_FILE)                 # .../src/streaming
SRC_DIR = os.path.dirname(STREAMING_DIR)                      # .../src
PROJECT_ROOT = os.path.dirname(SRC_DIR)                       # .../

# Insert src/ and project root to PYTHONPATH BEFORE imports
for p in [SRC_DIR, PROJECT_ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

print("➜ PYTHONPATH FIXED. Project root added:", PROJECT_ROOT)

# =========================================================
# Now safe to import modules that live inside src/ package
# =========================================================
import streamlit as st
import requests
import json
import io
from typing import List, Dict

from src.streaming.sse_utils import sse_client 

# Configure this if your API lives elsewhere
FASTAPI_URL = os.environ.get("FASTAPI_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="AI Innovation UI", layout="wide")
st.title("🚀 AI Corporate Innovation Workflow Automation")

# ---- helpers ----
def api_post(path: str, json_payload=None, files=None, stream=False, timeout=600):
    url = f"{FASTAPI_URL}{path}"
    if stream:
        return requests.post(url, json=json_payload, stream=True, timeout=timeout)
    if files:
        return requests.post(url, files=files, timeout=timeout)
    return requests.post(url, json=json_payload, timeout=timeout)


def api_get(path: str, stream=False):
    url = f"{FASTAPI_URL}{path}"
    return requests.get(url, stream=stream, timeout=600)

def download_file_bytes(url: str) -> bytes:
    resp = requests.get(url, stream=True)
    resp.raise_for_status()
    return resp.content

def pretty(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False)

# ---- session state ----
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "extracted_competencies" not in st.session_state:
    st.session_state.extracted_competencies = []
if "gap_questions" not in st.session_state:
    st.session_state.gap_questions = []
if "generated_ideas" not in st.session_state:
    st.session_state.generated_ideas = []
if "idea_map_csv" not in st.session_state:
    st.session_state.idea_map_csv = None
if "evaluation_template" not in st.session_state:
    st.session_state.evaluation_template = None
if "evaluation_csv" not in st.session_state:
    st.session_state.evaluation_csv = None
if "selected_ideas" not in st.session_state:
    st.session_state.selected_ideas = []
if "action_plan_file" not in st.session_state:
    st.session_state.action_plan_file = None

# gap_round ensures fresh form keys each time backend asks additional questions
if "gap_round" not in st.session_state:
    st.session_state.gap_round = 0

# ---- sidebar navigation ----
page = st.sidebar.selectbox("Page", [
    "Workflow (start & stream)",
    "Clarify & Upload Competencies",
    "Ideas & Templates",
    "Evaluation & Selection",
    "Action Plans",
    "Debug / Console"
])

# ---------------- Page: Workflow ----------------
if page == "Workflow (start & stream)":
    st.header("Start session - ")
    company = st.text_input("Company name", value="Google")
    start = st.button("Start Session and Stream")

    if start and company:
        # start session
        with st.spinner("Requesting session and starting stream..."):
            try:
                r = api_post("/sessions", json_payload={"company_name": company})
            except Exception as e:
                st.error(f"Start session failed: {e}")
                r = None

            if r is None or r.status_code != 200:
                st.error(f"Start session failed: {getattr(r,'status_code', '')} {getattr(r,'text', '')}")
            else:
                data = r.json()
                sid = data["session_id"]
                st.session_state.session_id = sid
                # store returned fields if any
                st.session_state.extracted_competencies = data.get("discovered_competencies", [])
                st.session_state.gap_questions = data.get("gap_questions", [])
                # reset gap round for fresh clarifications
                st.session_state.gap_round = 0

                st.success(f"Session created: {sid}")

                # SSE stream
                stream_box = st.empty()
                log_lines = []
                stream_url = f"{FASTAPI_URL}/sessions/{sid}/stream"
                try:
                    for raw in sse_client(stream_url, timeout=600):
                        if raw.startswith("data: "):
                            msg = raw.replace("data: ", "")
                        else:
                            msg = raw
                        log_lines.append(msg)
                        stream_box.text("\n".join(log_lines[-200:]))
                        if "[[STREAM_END]]" in raw:
                            break
                except Exception as e:
                    st.error(f"Stream error: {e}")

                st.write("### Extracted competencies (preview)")
                st.dataframe(st.session_state.extracted_competencies[:20])

                st.write("### Gap questions")
                for q in st.session_state.gap_questions:
                    st.write(f"- {q}")

# ---------------- Page: Clarify & Upload Competencies ----------------
elif page == "Clarify & Upload Competencies":
    st.header("Answer gap questions and upload edited CSV")
    sid = st.text_input("Session ID", value=st.session_state.session_id or "")
    if sid:
        st.session_state.session_id = sid

    st.subheader("1) Gap questions")
    if not st.session_state.gap_questions:
        st.info("No gap questions in session state. Start a session first or fetch /sessions/{id}/debug.")
        st.markdown("If you have an existing session with questions on the server, paste the Session ID above and click **Fetch debug** below.")
        if st.button("Fetch debug"):
            try:
                r = api_get(f"/sessions/{sid}/debug")
                if r.status_code == 200:
                    debug_state = r.json()
                    st.session_state.extracted_competencies = debug_state.get("extracted_competencies", st.session_state.extracted_competencies)
                    st.session_state.gap_questions = debug_state.get("gap_questions", st.session_state.gap_questions)
                    st.success("Fetched session debug state from server.")
                else:
                    st.warning("Could not fetch session debug from server.")
            except Exception as e:
                st.error(f"Debug fetch failed: {e}")
    else:
        # Use gap_round to generate unique keys so new rounds don't retain old answers
        round_id = st.session_state.gap_round
        with st.form(f"gap_answers_form_round_{round_id}"):
            answers: List[Dict] = []
            for i, q in enumerate(st.session_state.gap_questions):
                key = f"ans_{round_id}_{i}"
                ans = st.text_area(label=q, key=key, height=80)
                answers.append({"question": q, "answer": ans})
            complete_btn = st.form_submit_button("Submit answers (or leave blank to mark COMPLETE)")

        if complete_btn:
            # if all answers empty -> submit {"status":"COMPLETE"}, else send answers
            all_empty = all(not a["answer"].strip() for a in answers)
            if all_empty:
                payload = {"status": "COMPLETE"}
            else:
                payload = {"answers": answers}

            try:
                resp = api_post(f"/sessions/{sid}/answer_gaps", json_payload=payload)
            except Exception as e:
                st.error(f"Answer gaps failed: {e}")
                resp = None

            if resp is None or resp.status_code != 200:
                st.error(f"Answer gaps failed: {getattr(resp,'status_code','')} {getattr(resp,'text','')}")
            else:
                data = resp.json()
                st.success("Answer submitted")

                # If backend asks for more clarifications, it will return loop: "continue" and new gap_questions
                loop_state = data.get("loop")
                if loop_state == "continue":
                    new_qs = data.get("gap_questions", [])
                    st.session_state.extracted_competencies = data.get("discovered_competencies", st.session_state.extracted_competencies)
                    st.session_state.gap_questions = new_qs
                    # increment round so next form uses new keys (fresh inputs)
                    st.session_state.gap_round = st.session_state.gap_round + 1
                    st.info("Backend requested further clarifications — please answer the new questions.")
                    # Streamlit will re-run and show the fresh form
                elif loop_state == "complete":
                    # Backend finalized competencies and generated CSV
                    st.success("Backend finalized competencies.")
                    csv_path = data.get("csv_path")
                    # attempt to download
                    try:
                        dl = api_get(f"/sessions/{sid}/download_competencies")
                        if dl.status_code == 200:
                            st.download_button("Download competencies CSV", data=dl.content, file_name=f"{sid}_competencies.csv")
                        else:
                            st.info("CSV is ready on server but automatic download failed.")
                    except Exception:
                        st.warning("Could not download CSV automatically — check the API.")
                    # clear questions from UI
                    st.session_state.gap_questions = []
                else:
                    # fallback: update questions if provided
                    st.session_state.extracted_competencies = data.get("discovered_competencies", st.session_state.extracted_competencies)
                    new_qs = data.get("gap_questions", [])
                    if new_qs:
                        st.session_state.gap_questions = new_qs
                        st.session_state.gap_round = st.session_state.gap_round + 1

    st.markdown("---")
    st.subheader("2) Upload edited competencies CSV (Category, Competency, Description, Technology Level)")
    uploaded = st.file_uploader("Upload edited competencies CSV", type=["csv"])
    if uploaded:
        if not st.session_state.session_id:
            st.error("Start session first.")
        else:
            files = {"file": (uploaded.name, uploaded.getvalue(), "text/csv")}
            try:
                r = requests.post(f"{FASTAPI_URL}/sessions/{st.session_state.session_id}/upload_csv", files=files, timeout=600)
            except Exception as e:
                st.error(f"Upload failed: {e}")
                r = None

            if r is None or r.status_code != 200:
                st.error(f"Upload failed: {getattr(r,'status_code','')} {getattr(r,'text','')}")
            else:
                st.success("CSV uploaded and validated by backend")
                st.session_state.extracted_competencies = []  # will get replaced when needed
                # st.write(r.json())

# ---------------- Page: Ideas & Templates ----------------
elif page == "Ideas & Templates":
    st.header("Ideas generation and evaluation template")
    sid = st.text_input("Session ID", value=st.session_state.session_id or "")
    if sid:
        st.session_state.session_id = sid

    st.subheader("Generate idea map from competencies")
    if st.button("Generate ideas"):
        try:
            r = api_post(f"/sessions/{sid}/generate_ideas")
        except Exception as e:
            st.error(f"Generate ideas failed: {e}")
            r = None

        if r is None or r.status_code != 200:
            st.error(f"Generate ideas failed: {getattr(r,'status_code','')} {getattr(r,'text','')}")
        else:
            data = r.json()
            st.success(data.get("message", "Ideas generated"))
            # try to download idea map
            dl = api_get(f"/sessions/{sid}/download_idea_map")
            if dl.status_code == 200:
                st.session_state.idea_map_csv = dl.content
                st.download_button("Download idea map CSV", data=dl.content, file_name=f"{sid}_idea_map.csv")
            else:
                st.warning("Idea map not available yet on server.")

    st.markdown("---")
    st.subheader("Generate evaluation template")
    if st.button("Generate evaluation template"):
        try:
            r = api_post(f"/sessions/{sid}/generate_template")
        except Exception as e:
            st.error(f"Generate template failed: {e}")
            r = None

        if r is None or r.status_code != 200:
            st.error(f"Generate template failed: {getattr(r,'status_code','')} {getattr(r,'text','')}")
        else:
            dl = api_get(f"/sessions/{sid}/download_template")
            if dl.status_code == 200:
                st.session_state.evaluation_template = dl.content
                st.download_button("Download evaluation template CSV", data=dl.content, file_name=f"{sid}_evaluation_template.csv")
            else:
                st.warning("Template not available for download.")

# ---------------- Page: Evaluation & Selection ----------------
elif page == "Evaluation & Selection":
    st.header("Upload completed evaluation, validate, select top ideas")
    sid = st.text_input("Session ID", value=st.session_state.session_id or "")
    if sid:
        st.session_state.session_id = sid

    st.subheader("Upload completed evaluation CSV")
    eval_file = st.file_uploader("Upload filled evaluation CSV", type=["csv"], key="eval")
    if eval_file:
        files = {"file": (eval_file.name, eval_file.getvalue(), "text/csv")}
        try:
            r = requests.post(f"{FASTAPI_URL}/sessions/{sid}/upload_evaluation", files=files, timeout=600)
        except Exception as e:
            st.error(f"Upload evaluation failed: {e}")
            r = None

        if r is None or r.status_code != 200:
            st.error(f"Upload evaluation failed: {getattr(r,'status_code','')} {getattr(r,'text','')}")
        else:
            st.success("Evaluation uploaded and validated")
            st.session_state.evaluation_csv = eval_file.getvalue()

    st.markdown("---")
    st.subheader("Validate & select top ideas")
    top_k = st.number_input("Top K", min_value=1, max_value=10, value=3)
    if st.button("Validate & Select"):
        try:
            r = api_post(f"/sessions/{sid}/validate_scores", json_payload={"top_k": top_k})
        except Exception as e:
            st.error(f"Validate/select failed: {e}")
            r = None

        if r is None or r.status_code != 200:
            st.error(f"Validate/select failed: {getattr(r,'status_code','')} {getattr(r,'text','')}")
        else:
            data = r.json()
            selected = data.get("selected", [])
            st.session_state.selected_ideas = selected
            st.success("Top ideas selected")

            # Display selected ideas as a nice table (not raw JSON)
            if selected:
                import pandas as pd
                df = pd.DataFrame(selected)
                # some selected rows include nested idea_doc; flatten for display if present
                if "idea_doc" in df.columns:
                    # show title, score, priority, and a truncated description if available
                    display_rows = []
                    for row in selected:
                        doc = row.get("idea_doc") or {}
                        display_rows.append({
                            "title": row.get("title") or doc.get("title"),
                            "score": row.get("score"),
                            "priority": row.get("priority"),
                            "application_area": (doc.get("application_area") if doc else row.get("application_area"))
                        })
                    df2 = pd.DataFrame(display_rows)
                    st.dataframe(df2)
                else:
                    st.dataframe(df)
            else:
                st.warning("No ideas selected.")

# ---------------- Page: Action Plans ----------------
elif page == "Action Plans":
    st.header("Generate and download action plans")
    sid = st.text_input("Session ID", value=st.session_state.session_id or "")
    if sid:
        st.session_state.session_id = sid

    if st.button("Generate action plans"):
        try:
            r = api_post(f"/sessions/{sid}/generate_action_plans")
        except Exception as e:
            st.error(f"Generate action plans failed: {e}")
            r = None

        if r is None or r.status_code != 200:
            st.error(f"Generate action plans failed: {getattr(r,'status_code','')} {getattr(r,'text','')}")
        else:
            dl = api_get(f"/sessions/{sid}/download_action_plans")
            if dl.status_code == 200:
                st.session_state.action_plan_file = dl.content
                st.download_button("Download action plans (.md)", data=dl.content, file_name=f"{sid}_action_plans.md")
            else:
                st.warning("Action plans not available for download.")

# ---------------- Page: Debug / Console ----------------
elif page == "Debug / Console":
    st.header("Debug & Manual Console")
    st.write("Session state preview (if any)")
    sid = st.text_input("Session ID for debug", value=st.session_state.session_id or "")
    if sid:
        st.session_state.session_id = sid
        try:
            r = api_get(f"/sessions/{sid}/debug")
            if r.status_code == 200:
                st.json(r.json())
            else:
                st.warning("No debug info returned (session may not exist).")
        except Exception as e:
            st.error(f"Debug fetch failed: {e}")

    st.markdown("---")
    st.subheader("Manual API Console")
    method = st.selectbox("Method", ["GET", "POST"])
    path = st.text_input("Endpoint path (e.g. /sessions, /sessions/{id}/answer_gaps)")
    body = st.text_area("JSON body (for POST)", height=160)
    if st.button("Send"):
        try:
            if method == "GET":
                r = api_get(path)
            else:
                json_payload = json.loads(body) if body.strip() else {}
                r = api_post(path, json_payload=json_payload)
            st.write(f"Status: {r.status_code}")
            # try to render JSON
            try:
                st.json(r.json())
            except Exception:
                st.text(r.text[:10000])
        except Exception as e:
            st.error(f"Request failed: {e}")

# ---- footer ----
st.markdown("---")
st.caption("This Streamlit UI mirrors the FastAPI workflow endpoints and provides convenient downloads/uploads and a simple SSE stream.")
