# src/nodes/idea_selector.py
import pandas as pd
import os
from src.db.mongo import get_collection

def score_and_select_top(session_id: str, eval_csv_path: str, top_k=3, weights=(3,2,1)):
    df = pd.read_csv(eval_csv_path)
    # normalize priority mapping
    def prio_to_val(p):
        if str(p).strip().upper().startswith("H"):
            return 3
        if str(p).strip().upper().startswith("M"):
            return 2
        return 1
    df["priority_val"] = df["Priority (H/M/L)"].apply(prio_to_val)
    # compute weighted score (example weights)
    w1, w2, w3 = weights
    df["score"] = df["Strategic Fit (1-5)"]*w1 + df["Market Attractiveness (1-5)"]*w2 + df["Technical Feasibility (1-5)"]*w3 + df["priority_val"]*2
    top = df.sort_values("score", ascending=False).head(top_k)
    # fetch idea docs from Mongo to return full info
    idea_col = get_collection("ideas")
    selected = []
    for _, row in top.iterrows():
        title = row["Idea"]
        doc = idea_col.find_one({"session_id": session_id, "title": title}, {"_id":0})
        selected.append({"title": title, "score": row["score"], "priority": row["Priority (H/M/L)"], "idea_doc": doc})
    return selected
