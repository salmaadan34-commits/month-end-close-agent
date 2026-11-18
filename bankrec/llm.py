"""Pass 5: Claude reviews the items the rules could not explain.

Runs only with --llm and an ANTHROPIC_API_KEY. Without them, a rule-based fallback fills in the
same fields so the pipeline (and the demo) always works offline. Claude never posts anything:
it proposes a likely cause and next step, and the controller decides.
"""
import json
import os

from . import config as C

PROMPT = """You are a senior accountant reviewing open items on a bank reconciliation.
For each open item, give the most likely cause and the next step a controller should take.
If an item plausibly matches another open item, say which one.

Open items needing review:
{items}

Other open items on the reconciliation (context):
{context}

Reply with JSON only: a list of objects with keys
"id", "likely_cause" (one sentence), "action" (one sentence), "confidence" ("High"|"Medium"|"Low")."""


def _fallback(item) -> dict:
    d = item.description.upper()
    if "WIRE" in d and item.amount > 0:
        sender = d.split("FROM", 1)[-1].split(" REF")[0].strip().title().replace("Llc", "LLC") if "FROM" in d else "the sender"
        return {"likely_cause": f"Incoming wire from {sender} with no AR receipt or GL entry - likely an unapplied "
                                "customer payment, investor funding or loan proceeds.",
                "action": f"Confirm purpose with {sender} / AR; park in suspense until applied.",
                "confidence": "Medium"}
    if item.side == "bank":
        return {"likely_cause": "Bank activity with no GL entry and no keyword match.",
                "action": "Pull bank detail and supporting docs; book or dispute.", "confidence": "Low"}
    return {"likely_cause": "GL entry with no bank activity outside the timing window.",
            "action": "Check whether the payment was actually sent or the entry was posted to the wrong account.",
            "confidence": "Low"}


def review(items, use_llm: bool = False):
    """Fill likely_cause/action/confidence on items flagged needs_review (except stale checks)."""
    targets = [i for i in items if i.needs_review and i.category != "Stale item"]
    if not targets:
        return items

    answers = {}
    if use_llm and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            fmt = lambda i: f"- id={i.ids[0]} | {i.side} | {i.date} | {i.description} | {i.amount:,.2f}"
            others = [i for i in items if i not in targets]
            msg = anthropic.Anthropic().messages.create(
                model=C.LLM_MODEL, max_tokens=1500,
                messages=[{"role": "user", "content": PROMPT.format(
                    items="\n".join(fmt(i) for i in targets),
                    context="\n".join(fmt(i) for i in others) or "(none)")}])
            text = msg.content[0].text
            parsed = json.loads(text[text.find("["): text.rfind("]") + 1])
            answers = {a["id"]: a for a in parsed}
            source = f"Claude ({C.LLM_MODEL})"
        except Exception as e:  # never let the LLM step break the rec
            print(f"  LLM review skipped ({e.__class__.__name__}: {e}); using rule-based fallback.")
    for i in targets:
        a = answers.get(i.ids[0])
        if a:
            i.likely_cause, i.action, i.confidence, i.source = a["likely_cause"], a["action"], a["confidence"], source
        else:
            fb = _fallback(i)
            i.likely_cause, i.action, i.confidence = fb["likely_cause"], fb["action"], fb["confidence"]
            i.source = "Rule-based fallback (LLM off)"
    return items
