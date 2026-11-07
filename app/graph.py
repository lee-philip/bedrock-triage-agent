"""
Settlement exception triage workflow.

Graph flow:
    classify -> retrieve -> draft_fix -> guardrail -> review -> execute | reject

Each node classifies, retrieves runbook context, drafts a fix, runs guardrails,
and goes through review. Approved fixes are executed; rejections end the flow.
Every node appends an audit entry with node name, timestamp, provider, model,
and latency.

Uses SQLite checkpointing for persistence across invocations.
"""
import sqlite3
import aiosqlite
import os

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.errors import GraphRecursionError

from app.state import TriageState
from app.nodes.input_guardrail import input_guardrail
from app.nodes.classify import classify
from app.nodes.retrieve import retrieve
from app.nodes.draft_fix import draft_fix
from app.nodes.guardrail import guardrail
from app.nodes.review import review
from app.nodes.execute import execute
from app.nodes.reject import reject
from app.audit import timed_node
from app.observability import check_token_budget

import pathlib
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
CHECKPOINT_DB_PATH = str(PROJECT_ROOT / "data" / "checkpoints.db")


def route_after_classify(state):
    if check_token_budget(state, 0):
        state["decision"] = "rejected"
        state["reason"] = "BUDGET_EXCEEDED"
        return "reject"
    return "retrieve"


def route_after_draft_fix(state):
    if check_token_budget(state, 0):
        state["decision"] = "rejected"
        state["reason"] = "BUDGET_EXCEEDED"
        return "reject"
    return "guardrail"


def route_after_guardrail(state):
    if state.get("guardrail_action") == "BLOCKED":
        return "reject"
    if check_token_budget(state, 0):
        state["decision"] = "rejected"
        state["reason"] = "BUDGET_EXCEEDED"
        return "reject"
    return "review"


def route_after_review(state):
    if state.get("decision") == "approved":
        return "execute"
    return "reject"


def build_graph():
    """Build and compile the workflow graph with SQLite checkpointing.
    
    Must be called inside an async context (where an event loop is running)
    because AsyncSqliteSaver requires one.
    """
    workflow = StateGraph(TriageState)
    workflow.add_node("input_guardrail", timed_node(input_guardrail, "input_guardrail"))
    workflow.add_node("classify", timed_node(classify, "classify"))
    workflow.add_node("retrieve", timed_node(retrieve, "retrieve"))
    workflow.add_node("draft_fix", timed_node(draft_fix, "draft_fix"))
    workflow.add_node("guardrail", timed_node(guardrail, "guardrail"))
    workflow.add_node("review", timed_node(review, "review"))
    workflow.add_node("execute", timed_node(execute, "execute"))
    workflow.add_node("reject", timed_node(reject, "reject"))

    workflow.set_entry_point("input_guardrail")
    workflow.add_edge("input_guardrail", "classify")
    workflow.add_conditional_edges("classify", route_after_classify, {"retrieve": "retrieve", "reject": "reject"})
    workflow.add_edge("retrieve", "draft_fix")
    workflow.add_conditional_edges("draft_fix", route_after_draft_fix, {"guardrail": "guardrail", "reject": "reject"})
    workflow.add_conditional_edges("guardrail", route_after_guardrail, {"reject": "reject", "review": "review"})
    workflow.add_conditional_edges("review", route_after_review, {"execute": "execute", "reject": "reject"})
    workflow.add_edge("execute", END)
    workflow.add_edge("reject", END)

    # Ensure data directory exists
    os.makedirs(os.path.dirname(CHECKPOINT_DB_PATH), exist_ok=True)
    
    # Compile with SQLite checkpointing (async)
    conn = aiosqlite.connect(CHECKPOINT_DB_PATH)
    checkpointer = AsyncSqliteSaver(conn)
    graph = workflow.compile(checkpointer=checkpointer)
    return graph, conn