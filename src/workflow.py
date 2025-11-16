# src/workflow.py
import os
from typing_extensions import TypedDict

# LangGraph StateGraph primitives (installed version 0.3.12)
from langgraph.graph import StateGraph, START, END

from src.nodes.search_agent import search_company
from src.nodes.competency_extractor import extract_from_snippets, extract_with_clarifications
from src.nodes.gap_analyzer import ask_gaps_for_competencies
from src.nodes.idea_generator import generate_ideas_from_csv
from src.nodes.template_generator import generate_evaluation_template
from src.nodes.idea_selector import score_and_select_top
from src.nodes.action_plan_writer import generate_action_plans

# Define the shape of your graph state (optional fields allowed)
class SessionState(TypedDict, total=False):
    company_name: str
    session_id: str
    snippets: list
    extracted_competencies: list
    gap_questions: list
    answers: list
    generated_ideas: list
    evaluation_template_path: str
    selected_ideas: list
    action_plan_file: str
    evaluation_csv: str

# Build the graph builder
builder = StateGraph(SessionState)

# --- Nodes ---
def node_search(state: SessionState) -> dict:
    # perform the web search / snippet retrieval
    snippets = search_company(state["company_name"])
    return {"snippets": snippets}

def node_extract(state: SessionState) -> dict:
    comps = extract_from_snippets(state["session_id"], state.get("snippets", []))
    return {"extracted_competencies": comps}

def node_refine(state: SessionState) -> dict:
    # if answers/clarifications provided, refine extraction
    if state.get("answers"):
        refined = extract_with_clarifications(state["session_id"], state.get("snippets", []), state.get("answers", []))
        # update state in-place so later nodes see refined list
        state["extracted_competencies"] = refined
    questions = ask_gaps_for_competencies(state.get("extracted_competencies", []))
    return {"gap_questions": questions}

def node_generate_ideas(state: SessionState) -> dict:
    # generate/store ideas (unique key name to avoid collisions)
    ideas = generate_ideas_from_csv(state["session_id"], max_ideas=10)
    return {"generated_ideas": ideas}

def node_generate_template(state: SessionState) -> dict:
    # produce evaluation template CSV (writes to current working dir by default)
    path = generate_evaluation_template(state["session_id"], os.getcwd())
    return {"evaluation_template_path": path}

def node_select_ideas(state: SessionState) -> dict:
    # select top ideas from an evaluation CSV path stored in state["evaluation_csv"]
    selected = score_and_select_top(state["session_id"], state.get("evaluation_csv", ""), top_k=3)
    return {"selected_ideas": selected}

def node_generate_action_plans(state: SessionState) -> dict:
    path = generate_action_plans(state["session_id"], state.get("selected_ideas", []), os.getcwd())
    return {"action_plan_file": path}

# --- Add nodes (ensure node keys are unique and won't collide with state keys) ---
builder.add_node("search", node_search)
builder.add_node("extract", node_extract)
builder.add_node("ask_gaps", node_refine)
builder.add_node("generate_ideas", node_generate_ideas)
builder.add_node("generate_template", node_generate_template)
builder.add_node("select_ideas", node_select_ideas)
builder.add_node("generate_action_plans", node_generate_action_plans)

# --- Define edges (linear flow) ---
builder.add_edge(START, "search")
builder.add_edge("search", "extract")
builder.add_edge("extract", "ask_gaps")
# stop here by default (human-in-the-loop). Later we resume into generate_ideas
builder.add_edge("ask_gaps", "generate_ideas")
builder.add_edge("generate_ideas", "generate_template")
builder.add_edge("generate_template", "select_ideas")
builder.add_edge("select_ideas", "generate_action_plans")
builder.add_edge("generate_action_plans", END)

# Compile the graph into a runnable object
app_graph = builder.compile()
