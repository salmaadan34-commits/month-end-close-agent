"""Claude-driven close: the model decides the order of steps, reads results, and writes the commentary and memo.

Deterministic accounting (matching, math, JE construction) stays in Python. The model handles judgment
and narrative, and it cannot post anything: there is no tool for that.
"""
import json
import os

from .engine import CloseRun, StepOrderError

SYSTEM_PROMPT = """You are a staff accountant preparing the month-end close. A Controller reviews your work.

Rules:
- Use the tools in a sensible order: check inputs, bank rec, subledger recs, propose JEs, adjusted TB,
  flux, flux commentary, financial statements, close memo.
- Never invent numbers. Use only figures returned by the tools.
- You cannot post entries. Present JEs as proposals for approval.
- Do not propose a JE for an unexplained reconciling difference. List it as an open item to investigate.
- Flux commentary: one or two sentences per flagged line, naming the driver (a JE, a timing item, a
  known pattern). If the driver is not evident from the data, say what the reviewer should confirm.
- Close memo (markdown, under 350 words): status, key results, open items needing action,
  JEs needing approval, flux highlights. Lead with what needs the Controller's attention."""

TOOLS = [
    {"name": "check_inputs", "description": "Confirm all close input files are present. Returns entity, period, missing files and known patterns from prior closes.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "run_bank_rec", "description": "Match GL cash to the bank statement. Returns deposits in transit, outstanding checks, unrecorded bank items and any unexplained difference.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "run_subledger_recs", "description": "Tie AR, AP, prepaids, fixed assets, accumulated depreciation and deferred revenue to their supporting schedules.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "propose_journal_entries", "description": "Build proposed JEs: unrecorded bank items, expense accruals, prepaid amortization, depreciation, revenue recognition. Requires the bank rec.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "build_adjusted_tb", "description": "Apply proposed JEs to the unadjusted trial balance.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "run_flux", "description": "P&L flux vs prior month and budget. Lines with needs_commentary=true require an explanation.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "record_flux_commentary", "description": "Save commentary for flux lines, keyed by account number.",
     "input_schema": {"type": "object", "properties": {"comments": {"type": "object", "additionalProperties": {"type": "string"},
                                                                     "description": "Map of account number to commentary"}},
                      "required": ["comments"]}},
    {"name": "build_financials", "description": "Income statement and balance sheet from the adjusted TB, plus tie-out checks.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_open_items", "description": "List unreconciled differences, JEs needing approval, flagged JEs and failed checks.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "write_close_memo", "description": "Save the final close memo in markdown. Call last.",
     "input_schema": {"type": "object", "properties": {"memo_markdown": {"type": "string"}}, "required": ["memo_markdown"]}},
]


def _dispatch(run: CloseRun, name: str, args: dict):
    handlers = {
        "check_inputs": run.check_inputs, "run_bank_rec": run.run_bank_rec,
        "run_subledger_recs": run.run_subledger_recs, "propose_journal_entries": run.propose_journal_entries,
        "build_adjusted_tb": run.build_adjusted_tb, "run_flux": run.run_flux,
        "build_financials": run.build_financials, "get_open_items": run.open_items,
        "record_flux_commentary": lambda: run.record_flux_commentary(args["comments"]),
        "write_close_memo": lambda: run.write_close_memo(args["memo_markdown"]),
    }
    return handlers[name]()


def run_agent(run: CloseRun, model: str | None = None, max_turns: int = 25, verbose: bool = True) -> CloseRun:
    import anthropic

    client = anthropic.Anthropic()
    model = model or os.environ.get("CLOSE_AGENT_MODEL", "claude-sonnet-5-5")
    messages = [{"role": "user", "content":
                 f"Run the {run.config['period']} close for {run.config['entity']} and write the close memo."}]

    for _ in range(max_turns):
        resp = client.messages.create(model=model, max_tokens=4096, system=SYSTEM_PROMPT,
                                      tools=TOOLS, messages=messages)
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            break
        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            if verbose:
                print(f"  -> {block.name}")
            try:
                out, is_error = _dispatch(run, block.name, block.input), False
            except (StepOrderError, KeyError) as e:
                out, is_error = {"error": str(e)}, True
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": json.dumps(out, default=str), "is_error": is_error})
        messages.append({"role": "user", "content": results})

    if run.memo is None:
        raise RuntimeError("Agent stopped before writing the close memo.")
    return run
