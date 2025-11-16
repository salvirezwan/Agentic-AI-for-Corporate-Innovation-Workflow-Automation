# src/utils/csv_utils.py
import pandas as pd
import os

REQUIRED_COLS = ["Category", "Competency", "Description", "Technology Level"]

def validate_csv_file(filepath: str):
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        return False, f"Failed to read CSV: {e}"
    for col in REQUIRED_COLS:
        if col not in df.columns:
            return False, f"Missing required column: {col}"
    if df[REQUIRED_COLS].isnull().any().any():
        return False, "Some required fields are empty"
    # Technology Level check
    allowed = {"Basic", "Intermediate", "Advanced", "Cutting-edge"}
    bad_levels = set(df["Technology Level"].unique()) - allowed
    if bad_levels:
        return False, f"Invalid technology levels found: {bad_levels}"
    return True, "CSV validated"

def generate_competency_csv(session_id: str, competencies: list, artifacts_dir: str):
    rows = []
    for c in competencies:
        rows.append({
            "Category": c.get("Category") or c.get("category") or "",
            "Competency": c.get("Competency") or c.get("competency") or "",
            "Description": c.get("Description") or c.get("description") or "",
            "Technology Level": c.get("Technology Level") or c.get("technology_level") or "",
            "Source URL": c.get("Source URL") or c.get("source_url") or ""
        })
    df = pd.DataFrame(rows)
    path = os.path.join(artifacts_dir, f"{session_id}_competencies.csv")
    df.to_csv(path, index=False)
    return path

def generate_idea_map_csv(session_id: str, ideas: list, artifacts_dir: str):
    rows = []
    for idea in ideas:
        rows.append({
            "Search Term": ", ".join(idea.get("components", [])),
            "Idea": idea.get("title"),
            "Application Area": idea.get("application_area"),
            "Example Analog": ", ".join(idea.get("example_analogs", [])) if idea.get("example_analogs") else "",
            "Strategic Rationale": idea.get("strategic_rationale")
        })
    df = pd.DataFrame(rows)
    path = os.path.join(artifacts_dir, f"{session_id}_idea_map.csv")
    df.to_csv(path, index=False)
    return path

def generate_evaluation_template_csv(session_id: str, ideas: list, artifacts_dir: str):
    rows = []
    for idea in ideas:
        rows.append({
            "Idea": idea.get("title"),
            "Application Area": idea.get("application_area"),
            "Strategic Fit (1-5)": "",
            "Market Attractiveness (1-5)": "",
            "Technical Feasibility (1-5)": "",
            "Priority (H/M/L)": ""
        })
    df = pd.DataFrame(rows)
    path = os.path.join(artifacts_dir, f"{session_id}_evaluation_template.csv")
    df.to_csv(path, index=False)
    return path
