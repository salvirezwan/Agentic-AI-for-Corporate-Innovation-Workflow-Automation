# src/nodes/score_validator.py
import pandas as pd

def validate_evaluation_csv(filepath: str):
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        return False, f"Failed to read CSV: {e}"
    required = ["Idea", "Application Area", "Strategic Fit (1-5)", "Market Attractiveness (1-5)", "Technical Feasibility (1-5)", "Priority (H/M/L)"]
    for col in required:
        if col not in df.columns:
            return False, f"Missing column: {col}"
    # check numeric ranges
    for col in ["Strategic Fit (1-5)", "Market Attractiveness (1-5)", "Technical Feasibility (1-5)"]:
        if not pd.api.types.is_numeric_dtype(df[col]):
            return False, f"{col} must be numeric 1-5"
        if df[col].min() < 1 or df[col].max() > 5:
            return False, f"{col} values must be between 1 and 5"
    # priority check
    if not df["Priority (H/M/L)"].isin(["H", "M", "L", "High", "Medium", "Low"]).all():
        return False, "Priority contains invalid values. Use H/M/L or High/Medium/Low"
    return True, "Evaluation CSV validated"
