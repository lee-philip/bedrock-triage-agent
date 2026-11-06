#!/usr/bin/env python3
"""
FastAPI review web page for human-in-the-loop triage decisions.

Binds to 0.0.0.0 so it's accessible over Tailscale without auth.
Displays pending review cases with Approve/Reject buttons.
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.chdir(Path(__file__).resolve().parents[1])  # ensure relative paths resolve correctly

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from app.graph import build_graph

app = FastAPI(title="Triage Review")

# Use in-memory queue to track thread_ids
# In production, this would query the checkpoints database
async def get_pending_threads(graph):
    """Query checkpoint database for threads at review node."""
    import sqlite3
    db_path = "/Users/phillee/Projects/bedrock-triage/bedrock-triage-agent/data/checkpoints.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT thread_id FROM checkpoints")
    thread_ids = [row[0] for row in cursor.fetchall()]
    conn.close()

    print(f"[WEB] Found {len(thread_ids)} threads in checkpoint DB: {thread_ids}")

    pending = []
    for thread_id in thread_ids:
        config = {"configurable": {"thread_id": thread_id}}
        try:
            state = await graph.aget_state(config)
            print(f"[WEB] Thread {thread_id}: next={state.next}")
            if state.next and "review" in state.next:
                exception = state.values.get("exception", {})
                pending.append({
                    "thread_id": thread_id,
                    "trade_id": exception.get("trade_id", "N/A"),
                    "category": state.values.get("category", "UNKNOWN"),
                    "confidence": state.values.get("confidence", 0),
                })
        except Exception as e:
            print(f"[WEB] Error checking thread {thread_id}: {e}")
    return pending

GRAPH = None  # Lazy init


def get_graph():
    global GRAPH
    if GRAPH is None:
        graph, conn = build_graph()
        GRAPH = graph
    return GRAPH


@app.get("/", response_class=HTMLResponse)
async def index():
    """List pending review cases."""
    graph = get_graph()
    
    # Query checkpoint database for all pending review threads
    pending = await get_pending_threads(graph)
    
    cases_html = ""
    for case in pending:
        thread_id = case["thread_id"]
        trade_id = case["trade_id"]
        category = case["category"]
        confidence = case["confidence"]
        
        cases_html += f"""
        <div class="case-card">
            <h3>{trade_id}</h3>
            <p>Category: <strong>{category}</strong></p>
            <p>Confidence: {confidence:.2%}</p>
            <div class="actions">
                <a href="/case/{thread_id}" class="btn btn-review">Review</a>
            </div>
        </div>
        """
    
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Triage Review</title>
        <style>
            body {{ font-family: system-ui, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
            h1 {{ color: #1a1a1a; }}
            .case-card {{ border: 1px solid #e0e0e0; border-radius: 8px; padding: 16px; margin: 12px 0; }}
            .case-card h3 {{ margin: 0 0 8px 0; color: #2563eb; }}
            .actions {{ margin-top: 12px; }}
            .btn {{ display: inline-block; padding: 8px 16px; border-radius: 4px; text-decoration: none; font-weight: 500; }}
            .btn-review {{ background: #2563eb; color: white; }}
            .btn-approve {{ background: #16a34a; color: white; }}
            .btn-reject {{ background: #dc2626; color: white; }}
            .status {{ padding: 16px; background: #f0f9ff; border-radius: 8px; margin: 12px 0; }}
        </style>
    </head>
    <body>
        <h1>Triage Review</h1>
        <div class="status">
            <strong>{len(pending)}</strong> case(s) awaiting review
        </div>
        {cases_html if cases_html else '<p>No cases waiting for review.</p>'}
    </body>
    </html>
    """


@app.get("/case/{thread_id}", response_class=HTMLResponse)
async def show_case(thread_id: str):
    """Show details of a case for review."""
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    state = await graph.aget_state(config)
    if not state or not state.next or "review" not in state.next:
        return HTMLResponse("Case not found or already reviewed.", status_code=404)

    exception = state.values.get("exception", {})
    trade_id = exception.get("trade_id", "N/A")
    category = state.values.get("category", "UNKNOWN")
    confidence = state.values.get("confidence", 0)
    citations = state.values.get("citations", [])
    draft = state.values.get("draft", "")

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Review {trade_id}</title>
        <style>
            body {{ font-family: system-ui, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
            h1 {{ color: #1a1a1a; }}
            .detail {{ margin: 8px 0; }}
            .detail strong {{ color: #374151; }}
            .draft-box {{ background: #f9fafb; border: 1px solid #e0e0e0; border-radius: 8px; padding: 16px; margin: 16px 0; white-space: pre-wrap; }}
            .actions {{ margin-top: 20px; display: flex; gap: 12px; }}
            .btn {{ display: inline-block; padding: 10px 20px; border-radius: 4px; text-decoration: none; font-weight: 500; }}
            .btn-approve {{ background: #16a34a; color: white; }}
            .btn-reject {{ background: #dc2626; color: white; }}
            .btn-back {{ background: #6b7280; color: white; }}
            .comment-box {{ width: 100%; min-height: 80px; border: 1px solid #e0e0e0; border-radius: 4px; padding: 8px; margin: 12px 0; }}
        </style>
    </head>
    <body>
        <h1>Review {trade_id}</h1>
        <div class="detail"><strong>Category:</strong> {category}</div>
        <div class="detail"><strong>Confidence:</strong> {confidence:.2%}</div>
        <div class="detail"><strong>Citations:</strong> {', '.join(citations)}</div>
        <h2>Draft Fix</h2>
        <div class="draft-box">{draft}</div>
        <form method="post" action="/case/{thread_id}/approve">
            <label for="comment">Comment:</label><br>
            <textarea id="comment" name="comment" class="comment-box"></textarea><br>
            <div class="actions">
                <button type="submit" class="btn btn-approve">Approve</button>
                <a href="/case/{thread_id}/reject" class="btn btn-reject">Reject</a>
                <a href="/" class="btn btn-back">Back</a>
            </div>
        </form>
    </body>
    </html>
    """


@app.post("/case/{thread_id}/approve")
async def approve_case(thread_id: str, request: Request):
    try:
        form = await request.form()
        comment = form.get("comment", "")

        graph = get_graph()
        config = {"configurable": {"thread_id": thread_id}}

        from langgraph.types import Command
        final_state = await graph.ainvoke(
            Command(resume={
                "decision": "approved",
                "reviewer": "phillee",
                "comment": comment,
            }),
            config=config
        )
        return RedirectResponse("/", status_code=303)
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        return HTMLResponse(f"<h1>Error</h1><pre>{error_msg}</pre>", status_code=500)


@app.get("/case/{thread_id}/reject")
async def reject_case(thread_id: str):
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    from langgraph.types import Command
    final_state = await graph.ainvoke(
        Command(resume={
            "decision": "rejected",
            "reviewer": "phillee",
            "comment": "",
        }),
        config=config
    )

    return RedirectResponse("/", status_code=303)


@app.get("/api/pending")
async def api_pending():
    """API endpoint to list pending cases (for programmatic use)."""
    graph = get_graph()
    pending = await get_pending_threads(graph)
    return JSONResponse(pending)


if __name__ == "__main__":
    print("Starting Triage Review server at http://0.0.0.0:8080")
    print("Bind to 0.0.0.0 for Tailscale access — no auth required.")
    uvicorn.run(app, host="0.0.0.0", port=8080)