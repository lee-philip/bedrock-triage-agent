import json
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.nodes.input_guardrail import input_guardrail
from app.nodes.classify import classify
from app.nodes.retrieve import retrieve
from app.nodes.draft_fix import draft_fix
from app.nodes.guardrail import guardrail


async def run():
    sample_path = Path("samples/exception_004.json")
    with open(sample_path) as f:
        exception_data = json.load(f)

    state = {"exception": exception_data}

    # Node 1: input_guardrail
    ig_in = {"exception": state["exception"]}
    ig_out = await input_guardrail(ig_in)
    state.update(ig_out)
    print("=== NODE: input_guardrail ===")
    print("INPUT:", json.dumps(ig_in, indent=2))
    print("OUTPUT:", json.dumps(ig_out, indent=2))

    # Node 2: classify
    cl_in = {"exception": state["exception"]}
    cl_out = await classify(cl_in)
    state.update(cl_out)
    print("\n=== NODE: classify ===")
    print("INPUT:", json.dumps(cl_in, indent=2))
    print("OUTPUT:", json.dumps(cl_out, indent=2))

    # Node 3: retrieve
    r_in = {"category": state["category"], "exception": state["exception"]}
    r_out = await retrieve(r_in)
    state.update(r_out)
    print("\n=== NODE: retrieve ===")
    print("INPUT:", json.dumps(r_in, indent=2))
    print("OUTPUT:", json.dumps(r_out, indent=2))

    # Node 4: draft_fix
    d_in = {
        "category": state["category"],
        "exception": state["exception"],
        "runbook_chunks": state["runbook_chunks"]
    }
    d_out = await draft_fix(d_in)
    state.update(d_out)
    print("\n=== NODE: draft_fix ===")
    print("INPUT:", json.dumps(d_in, indent=2))
    print("OUTPUT:", json.dumps(d_out, indent=2))

    # Node 5: guardrail
    g_in = {"draft": state["draft"]}
    g_out = await guardrail(g_in)
    state.update(g_out)
    print("\n=== NODE: guardrail ===")
    print("INPUT:", json.dumps(g_in, indent=2))
    print("OUTPUT:", json.dumps(g_out, indent=2))


if __name__ == "__main__":
    asyncio.run(run())