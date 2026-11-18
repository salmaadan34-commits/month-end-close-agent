"""Optional: Claude rewrites the template commentary into CFO-ready prose.

The numbers and drivers are computed in code; Claude only words them. Runs with --llm and an
ANTHROPIC_API_KEY; otherwise the template commentary is kept as is.
"""
import json
import os

from . import gl as G

PROMPT = """You write month-end flux commentary for a CFO. For each account below, write 1-2 plain
sentences that state the change, name the drivers with their amounts, and mention any pre-close
finding reference (e.g. PC-07) exactly as given. Use only the facts provided; do not invent causes.

{payload}

Reply with JSON only: a list of {{"account": "...", "commentary": "..."}}."""


def polish(flux_lines, use_llm=False):
    targets = [f for f in flux_lines if f.commentary]
    if not (use_llm and targets and os.environ.get("ANTHROPIC_API_KEY")):
        return flux_lines
    payload = [{"account": f.account, "name": f.name, "change": f.var, "pct": f.pct, "vs_budget": f.bud_var,
                "drivers": [{"driver": d.key, "change": d.change, "status": d.status, "memo": d.memo,
                             "findings": [f"{x.id} {x.check}" for x in d.finding_refs]} for d in f.drivers]}
               for f in targets]
    try:
        import anthropic
        msg = anthropic.Anthropic().messages.create(
            model=G.LLM_MODEL, max_tokens=2000,
            messages=[{"role": "user", "content": PROMPT.format(payload=json.dumps(payload, indent=1))}])
        text = msg.content[0].text
        out = {r["account"]: r["commentary"] for r in json.loads(text[text.find("["): text.rfind("]") + 1])}
        for f in targets:
            if out.get(f.account):
                f.commentary, f.commentary_source = out[f.account], f"Claude ({G.LLM_MODEL})"
    except Exception as e:  # never let the LLM step break the close
        print(f"  LLM polish skipped ({e.__class__.__name__}: {e}); keeping template commentary.")
    return flux_lines
