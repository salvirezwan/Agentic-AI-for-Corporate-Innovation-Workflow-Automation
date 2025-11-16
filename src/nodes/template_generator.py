# src/nodes/template_generator.py
from src.db.mongo import get_collection
from src.utils.csv_utils import generate_evaluation_template_csv

def generate_evaluation_template(session_id: str, artifacts_dir: str):
    idea_col = get_collection("ideas")
    ideas = list(idea_col.find({"session_id": session_id}, {"_id": 0}))
    path = generate_evaluation_template_csv(session_id, ideas, artifacts_dir)
    return path
