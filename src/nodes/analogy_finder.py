# src/nodes/analogy_finder.py
from src.nodes.search_agent import search_company
from src.gemini_client import generate_json

def find_analogies_for_idea(idea):
    """
    Try to find 1-3 real-world analogs by searching web or asking Gemini.
    """
    # simple LLM approach
    prompt = (
        "Given this idea description, produce 3 real-world analogous products or references (short list). "
        "Return as JSON array of strings.\n\n"
        f"IDEA:\nTitle: {idea.get('title')}\nRationale: {idea.get('strategic_rationale')}\n\nReturn only JSON array."
    )
    parsed, raw = generate_json(prompt, debug=False)
    if isinstance(parsed, list):
        return parsed
    return []
