# src/nodes/idea_generator.py
from src.gemini_client import generate_json
import uuid
from src.db.mongo import get_collection
from src.nodes.semantic_reasoner import index_competencies_for_session, retrieve_relevant_competencies

def generate_ideas_from_csv(session_id: str, max_ideas=10):
    # index existing competencies
    index_competencies_for_session(session_id)

    col = get_collection("competencies")
    comps = list(col.find({"session_id": session_id}))
    comps_text = "\n".join([f"{c['competency']} ({c['category']}): {c['description']}" for c in comps])

    prompt = (
        "You are a creative strategist. Given the following validated competencies, generate up to "
        f"{max_ideas} innovative ideas. Each idea must be an object with: title, components (list), "
        "application_area, strategic_rationale, example_analogs (list).\n\n"
        f"COMPETENCIES:\n{comps_text}\n\nReturn only a JSON array."
    )
    parsed, raw = generate_json(prompt, debug=False, cleanup_attempt=True)
    ideas = []
    if isinstance(parsed, list):
        idea_col = get_collection("ideas")
        for i in parsed:
            doc = {
                "_id": str(uuid.uuid4()),
                "session_id": session_id,
                "title": i.get("title"),
                "components": i.get("components"),
                "application_area": i.get("application_area"),
                "strategic_rationale": i.get("strategic_rationale"),
                "example_analogs": i.get("example_analogs", [])
            }
            idea_col.insert_one(doc)
            ideas.append(doc)
    # fallback: none
    return ideas
