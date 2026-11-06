# Settlement Exception Triage Agent

Uses LangGraph with Bedrock (or local LM Studio) to classify, retrieve runbook context, draft fixes, and route trade settlement exceptions.

## Provider Configuration

Create `.env` with either:

**Bedrock:**
```
LLM_PROVIDER=bedrock
BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-6
AWS_REGION=us-west-2
GUARDRAIL_ID=kpbvstqxc7l5
GUARDRAIL_VERSION=2
GUARDRAIL_REGION=us-east-2
AWS_PROFILE=bedrock-triage
```

**Local LM Studio:**
```
LLM_PROVIDER=local
LMSTUDIO_MODEL=your-local-model
LMSTUDIO_BASE_URL=http://localhost:1234/v1
```

## Run Triage

```bash
source .venv/bin/activate
python scripts/triage_cli.py submit samples/exception_001.json
```

## Human-in-the-Loop

The workflow includes a review node that interrupts execution and waits for a human decision. The graph is checkpointed to SQLite (`data/checkpoints.db`), so it can be resumed later.

```bash
# Submit an exception (stops at review)
python scripts/triage_cli.py submit samples/exception_001.json

# Review and decide
python scripts/triage_cli.py review run-T-1042
```

Or use the web review page:

```bash
python scripts/review_server.py
# Opens http://0.0.0.0:8080 — no auth (intended for Tailscale)
```

## Idempotency

The execute node uses an idempotency key (SHA-256 of trade_id + category + proposed fix steps) to ensure fixes are applied exactly once. The simulated settlement system (`data/settlements.db`) stores executed fix keys with a UNIQUE constraint, so duplicate submissions are skipped.

## Audit Trail

All node executions are logged to `data/audit.db` with run_id, node name, timestamp, provider, model, and latency. The execute node also logs settlement application events.

## Build FAISS Index

Before running, build the FAISS index from the runbook:

```bash
python scripts/build_index.py
```

## Dependencies

- langgraph, langgraph-checkpoint-sqlite
- langchain-openai, langchain-aws
- boto3
- faiss-cpu
- numpy
- markdown
- python-dotenv
- fastapi, uvicorn
- aiosqlite