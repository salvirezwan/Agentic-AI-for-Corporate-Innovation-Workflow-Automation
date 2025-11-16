# src/nodes/action_plan_writer.py
from src.gemini_client import generate_text
import os
import logging

logging.basicConfig(level=logging.INFO)

def build_context_for_idea(session_id: str, idea):
    comps = ", ".join(idea.get("components") or [])
    rationale = idea.get("strategic_rationale") or "No rationale provided."
    return f"Idea: {idea.get('title', 'Untitled Idea')}\nComponents: {comps}\nRationale: {rationale}\n"

def generate_action_plans(session_id: str, selected_ideas: list, artifacts_dir: str):
    full_md = "# Action Plans\n\n"

    for idea in selected_ideas:
        context = build_context_for_idea(session_id, idea.get("idea_doc") or idea)
        prompt = (
            "You are a senior corporate strategist. Produce a detailed action plan for the following idea. "
            "Include: Executive Summary, Market Analysis, Required Competencies & Gaps, Partnering Strategy, "
            "Resources & Timeline, Risk Assessment. Return the output in markdown.\n\n"
            f"{context}"
        )

        try:
            resp = generate_text(prompt)
        except Exception as e:
            logging.warning(f"Gemini API call failed for idea '{idea.get('title', 'Untitled Idea')}': {e}")
            resp = "_Action plan generation failed due to API error._"

        full_md += f"## {idea.get('title', 'Untitled Idea')}\n\n"
        full_md += resp + "\n\n---\n\n"

    os.makedirs(artifacts_dir, exist_ok=True)
    path = os.path.join(artifacts_dir, f"{session_id}_top3_action_plans.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(full_md)

    logging.info(f"Action plans saved to: {path}")
    return path

