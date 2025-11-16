# src/nodes/semantic_reasoner.py
from src.vectorstore import add_competency_doc, query_similar
from src.db.mongo import get_collection

def index_competencies_for_session(session_id: str):
    col = get_collection("competencies")
    rows = list(col.find({"session_id": session_id}))
    for r in rows:
        text = f"{r.get('competency')} - {r.get('description')}"
        add_competency_doc(r["_id"], text, {"session_id": session_id, "category": r.get("category")})
    return len(rows)

def retrieve_relevant_competencies(session_id: str, text: str, n=5):
    resp = query_similar(text, n=n)
    return resp
