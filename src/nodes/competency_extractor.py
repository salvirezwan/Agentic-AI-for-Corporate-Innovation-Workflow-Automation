import json, uuid
from src.db.mongo import get_collection
from src.gemini_client import generate_json

# ------------------------------------------
# Normalization Layer (Enforces 4 Categories)
# ------------------------------------------
ALLOWED_TECH_LEVELS = ["Basic", "Intermediate", "Advanced", "Cutting-edge"]

def normalize_level(level: str):
    if not level:
        return "Basic"

    l = level.strip().lower()

    # Direct matches
    for a in ALLOWED_TECH_LEVELS:
        if l == a.lower():
            return a

    # Common mappings
    mapping = {
        "r&d": "Advanced",
        "research": "Advanced",
        "research & development": "Advanced",
        "research and development": "Advanced",
        "product": "Intermediate",
        "service": "Intermediate",
        "applied": "Intermediate",
        "development": "Intermediate",
        "core": "Intermediate",
        "unknown": "Basic",
        "": "Basic"
    }

    if l in mapping:
        return mapping[l]

    # Fallback default
    return "Intermediate"


# ==========================================
# Extractor: FROM SNIPPETS
# ==========================================
def extract_from_snippets(session_id: str, snippets_list: list):
    snippets_text = "\n\n".join([
        f"URL: {s.get('url','')}\nSNIPPET: {s.get('snippet','')}"
        for s in snippets_list
    ])

    prompt = (
        "You are a structured extractor. Given these website snippets, return ONLY a JSON array of competencies.\n\n"
        "Each item MUST follow this schema strictly:\n"
        "{\n"
        '  "category": "...",\n'
        '  "competency": "...",\n'
        '  "description": "...",\n'
        '  "technology_level": "...",\n'
        '  "source_url": "..." \n'
        "}\n\n"
        "❗ IMPORTANT:\n"
        "- technology_level MUST be one of EXACTLY these values:\n"
        "    Basic, Intermediate, Advanced, Cutting-edge\n"
        "- NEVER use any other labels such as Product, Service, R&D, Applied.\n"
        "- If unsure, pick the closest valid category.\n\n"
        f"SNIPPETS:\n{snippets_text}\n\nReturn ONLY the JSON array."
    )

    parsed, raw = generate_json(prompt, debug=False)
    results = []

    if isinstance(parsed, list):
        for c in parsed:
            level = normalize_level(
                c.get("technology_level") or c.get("Technology Level")
            )
            doc = {
                "_id": str(uuid.uuid4()),
                "session_id": session_id,
                "category": c.get("category") or c.get("Category"),
                "competency": c.get("competency") or c.get("Competency"),
                "description": c.get("description") or c.get("Description"),
                "technology_level": level,
                "source_url": c.get("source_url") or c.get("Source URL") or ""
            }
            get_collection("competencies").insert_one(doc)
            results.append(doc)

    else:
        # fallback lightweight heuristic
        text = snippets_text.lower()

        if "electric" in text:
            results.append({
                "_id": str(uuid.uuid4()),
                "session_id": session_id,
                "category": "Product & Technology",
                "competency": "Electric Powertrains",
                "description": "High-efficiency battery and motor systems",
                "technology_level": "Advanced",
                "source_url": ""
            })

        if "autonomous" in text:
            results.append({
                "_id": str(uuid.uuid4()),
                "session_id": session_id,
                "category": "Product & Technology",
                "competency": "Autonomous Driving",
                "description": "AI-based self-driving technology",
                "technology_level": "Cutting-edge",
                "source_url": ""
            })

        if not results:
            results.append({
                "_id": str(uuid.uuid4()),
                "session_id": session_id,
                "category": "Product & Technology",
                "competency": "Core Products",
                "description": f"Key products of {session_id}",
                "technology_level": "Intermediate",
                "source_url": ""
            })

        for doc in results:
            get_collection("competencies").insert_one(doc)

    return results


# ==========================================
# Extractor: WITH CLARIFICATIONS
# ==========================================
def extract_with_clarifications(session_id: str, snippets_list: list, clarifications: list):
    clar_text = "\n".join([
        f"Q: {q.get('question')} A: {q.get('answer')}"
        for q in clarifications
    ])

    snippets_text = "\n\n".join([
        f"URL: {s.get('url','')}\nSNIPPET: {s.get('snippet','')}"
        for s in snippets_list
    ])

    prompt = (
        "You are a structured extractor. Use the website snippets AND the human clarifications to produce a refined,\n"
        "validated JSON array of competencies.\n\n"
        "Each competency MUST include:\n"
        "{category, competency, description, technology_level, source_url}\n\n"
        "❗ IMPORTANT RULE:\n"
        "technology_level MUST be ONE OF:\n"
        "- Basic\n"
        "- Intermediate\n"
        "- Advanced\n"
        "- Cutting-edge\n\n"
        "NEVER output anything else. If the original text uses labels like R&D, Product, Applied, map them to the closest valid level.\n\n"
        f"SNIPPETS:\n{snippets_text}\n\n"
        f"CLARIFICATIONS:\n{clar_text}\n\n"
        "Return ONLY JSON array."
    )

    parsed, raw = generate_json(prompt, debug=False)
    results = []

    if isinstance(parsed, list):
        for c in parsed:
            level = normalize_level(
                c.get("technology_level") or c.get("Technology Level")
            )
            doc = {
                "_id": str(uuid.uuid4()),
                "session_id": session_id,
                "category": c.get("category") or c.get("Category"),
                "competency": c.get("competency") or c.get("Competency"),
                "description": c.get("description") or c.get("Description"),
                "technology_level": level,
                "source_url": c.get("source_url") or c.get("Source URL") or ""
            }
            get_collection("competencies").insert_one(doc)
            results.append(doc)

    else:
        # Fallback: derive competencies from clarifications
        for a in clarifications:
            ans = a.get("answer", "")
            if any(k in ans.lower() for k in ["chip", "semiconductor", "silicon", "processor"]):
                doc = {
                    "_id": str(uuid.uuid4()),
                    "session_id": session_id,
                    "category": "Product & Technology",
                    "competency": "Custom Silicon Design",
                    "description": ans,
                    "technology_level": "Advanced",
                    "source_url": ""
                }
                get_collection("competencies").insert_one(doc)
                results.append(doc)

    return results

