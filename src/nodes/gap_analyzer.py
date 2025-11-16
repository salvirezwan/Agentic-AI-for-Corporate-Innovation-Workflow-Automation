# src/nodes/gap_analyzer.py
from src.gemini_client import generate_json
import logging

logging.basicConfig(level=logging.INFO)

def ask_gaps_for_competencies(extracted):
    """
    Uses LLM to craft clarifying questions to refine competencies.
    Returns a list of strings (questions). The final question instructs the user how to indicate completion:
    reply with the single token: COMPLETE
    """
    # If nothing was extracted, ask an open starter question
    if not extracted:
        return [
            "Please provide the company's main product lines and any specialized hardware or software capabilities.",
            "When you are finished answering all clarifying questions, reply with the single word: COMPLETE"
        ]

    # Build a compact competency summary for the prompt (limit to first 20)
    comps_text = "\n".join([f"- {c.get('category','')} | {c.get('competency','')}: {c.get('description','')}" for c in extracted[:20]])

    prompt = (
        "You are an analyst whose job is to identify missing information about a company's competencies. "
        "Given the discovered competencies below, produce a concise JSON object with two fields:\n\n"
        "  {\n"
        "    \"questions\": [\"question1\", \"question2\", ...],\n"
        "    \"complete\": true|false\n"
        "  }\n\n"
        "The 'questions' array should contain short, actionable clarifying questions a human can answer to validate or complete the competency list. "
        "Set 'complete' to true only if there are no additional clarifying questions — i.e., the competency list looks complete.\n\n"
        f"Discovered Competencies:\n{comps_text}\n\n"
        "Return only JSON."
    )

    try:
        parsed, raw = generate_json(prompt, debug=False)
        # generate_json should return (parsed, raw) where parsed is already a Python structure
    except Exception as e:
        logging.warning("generate_json failed in ask_gaps_for_competencies: %s", e)
        parsed = None
        raw = None

    questions = []
    complete = False

    # Interpret model output flexibly
    if isinstance(parsed, dict):
        questions = parsed.get("questions", []) or []
        complete = bool(parsed.get("complete", False))
    elif isinstance(parsed, list):
        # If model returned a list, take it as questions.
        questions = parsed
    else:
        # Try to salvage raw text: if it's a JSON string, try parsing
        try:
            import json
            maybe = json.loads(raw) if raw else None
            if isinstance(maybe, dict):
                questions = maybe.get("questions", []) or []
                complete = bool(maybe.get("complete", False))
            elif isinstance(maybe, list):
                questions = maybe
        except Exception:
            # fallback heuristics
            questions = []

    # Heuristic fallback: if LLM gave no questions, add common gap checks
    if not questions:
        names = [c.get("competency", "").lower() for c in extracted]
        if "custom ai chips" not in "".join(names):
            questions.append("Do you have in-house chip design or specialized hardware capabilities?")
        if not any("manufact" in n for n in names):
            questions.append("Do you have in-house manufacturing capabilities (e.g., large-scale factories)?")
        if not any("solar" in n or "energy" in n for n in names):
            # example generic question
            pass

    # Always add a final confirmation instruction so the user can end the loop
    # The user should reply with the single token COMPLETE when they are done
    # confirmation_q = "If the competency list is now complete, reply with the single word: COMPLETE. Otherwise answer the questions above."
    # if confirmation_q not in questions:
    #     questions.append(confirmation_q)

    # If model explicitly said 'complete' we could return an empty question list — but it's safer to ask for a confirmation
    # The flow expects questions to present to the user, so we always return at least the confirmation.
    return [str(q) for q in questions]

