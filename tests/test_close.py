from pathlib import Path
from types import SimpleNamespace

import pytest

from close_agent.engine import CloseRun, StepOrderError
from close_agent.export import export_package
from close_agent.offline import run_offline

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def run():
    return CloseRun(ROOT / "data" / "2026-10", ROOT / "close_config.yaml")


def test_bank_rec_finds_timing_and_unrecorded_items(run):
    b = run.run_bank_rec()
    assert b["reconciled"]
    assert [d["ref"] for d in b["deposits_in_transit"]] == ["DEP-1048"]
    assert {d["ref"] for d in b["outstanding_checks"]} == {"CHK-2051", "CHK-2052"}
    assert {d["ref"] for d in b["unrecorded_bank_items"]} == {"SVC-FEE", "INT-OCT"}


def test_unexplained_ar_difference_is_open_item_not_je(run):
    run_offline(run)
    ar = next(r for r in run.recs if r["account"] == "1100")
    assert ar["difference"] == 600 and not ar["reconciled"]
    assert not any(l[0] == "1100" for j in run.jes for l in j.lines)
    assert any(i["area"] == "Accounts Receivable" for i in run.open_items())


def test_entries_balance_and_statements_tie(run):
    run_offline(run)
    assert all(j.balanced for j in run.jes)
    assert round(run.atb.adjusted.sum(), 2) == 0
    bs = run.fs["balance_sheet"]
    assert bs["total_assets"] == bs["total_liabilities_and_equity"]
    amounts = {j.description: j.amount for j in run.jes}
    assert amounts["Monthly depreciation"] == 4000
    assert amounts["Prepaid amortization"] == 5000
    assert amounts["Recognize subscription revenue"] == 19000


def test_accrual_auto_reverses_and_approval_threshold(run):
    run_offline(run)
    accrual = next(j for j in run.jes if j.description.startswith("Accrue"))
    assert accrual.reversal_date == "2026-11-01"
    assert [j.je_id for j in run.jes if j.needs_approval] == ["JE-2026-10-06"]


def test_steps_enforce_order(run):
    with pytest.raises(StepOrderError):
        run.build_adjusted_tb()


def test_export(run, tmp_path):
    run_offline(run)
    files = export_package(run, tmp_path)
    assert all(p.exists() for p in files.values())


def test_agent_loop_with_stub_client(run, monkeypatch):
    """The agent loop dispatches tool calls and stops after the memo, with no network calls."""
    import anthropic
    from close_agent import agent

    script = ["check_inputs", "run_bank_rec", "run_subledger_recs", "propose_journal_entries",
              "build_adjusted_tb", "run_flux", "build_financials"]

    class StubMessages:
        def __init__(self):
            self.i = 0

        def create(self, **kw):
            self.i += 1
            if self.i <= len(script):
                block = SimpleNamespace(type="tool_use", id=f"t{self.i}", name=script[self.i - 1], input={})
            elif self.i == len(script) + 1:
                block = SimpleNamespace(type="tool_use", id="m", name="write_close_memo",
                                        input={"memo_markdown": "# Memo"})
            else:
                return SimpleNamespace(content=[SimpleNamespace(type="text", text="Done")], stop_reason="end_turn")
            return SimpleNamespace(content=[block], stop_reason="tool_use")

    monkeypatch.setattr(anthropic, "Anthropic", lambda: SimpleNamespace(messages=StubMessages()))
    agent.run_agent(run, verbose=False)
    assert run.memo == "# Memo" and run.fs is not None
