"""CloseRun: holds the state of one close. Every step is a method the agent (or offline mode) can call."""
from pathlib import Path

from . import recs, reports
from .data import CloseInputs, load_config, load_inputs
from .jes import propose_entries


class StepOrderError(RuntimeError):
    pass


class CloseRun:
    def __init__(self, data_dir: Path, config_path: Path):
        self.config = load_config(config_path)
        self.inputs: CloseInputs = load_inputs(data_dir, self.config)
        self.bank = self.recs = self.jes = self.atb = self.flux = self.fs = self.checks = None
        self.memo: str | None = None
        self.log: list[str] = []

    def _require(self, *attrs):
        missing = [a for a in attrs if getattr(self, a) is None]
        if missing:
            raise StepOrderError(f"Run earlier steps first; missing: {', '.join(missing)}")

    # --- steps -----------------------------------------------------------------------------
    def check_inputs(self) -> dict:
        self.log.append("check_inputs")
        return {"entity": self.config["entity"], "period": self.config["period"],
                "files_loaded": sorted(self.inputs.frames), "missing": self.inputs.missing,
                "ready": not self.inputs.missing,
                "known_patterns": self.config.get("known_patterns", [])}

    def run_bank_rec(self) -> dict:
        self.bank = recs.bank_rec(self.inputs)
        self.log.append("bank_rec")
        return self.bank

    def run_subledger_recs(self) -> list:
        self.recs = recs.subledger_recs(self.inputs)
        self.log.append("subledger_recs")
        return self.recs

    def propose_journal_entries(self) -> list:
        self._require("bank")
        self.jes = propose_entries(self.inputs, self.bank)
        self.log.append("propose_journal_entries")
        return [j.to_dict() for j in self.jes]

    def build_adjusted_tb(self) -> list:
        self._require("jes")
        self.atb = reports.adjusted_tb(self.inputs, self.jes)
        self.log.append("adjusted_tb")
        return self.atb.to_dict("records")

    def run_flux(self) -> list:
        self._require("atb")
        self.flux = reports.flux(self.inputs, self.atb)
        self.log.append("flux")
        cols = ["account", "name", "current", "prior", "budget", "vs_prior", "vs_prior_pct",
                "vs_budget", "vs_budget_pct", "needs_commentary"]
        lines = self.flux[cols].to_dict("records")
        # Give the reviewer (human or model) the JE activity behind each flagged line
        for line in lines:
            line["proposed_je_activity"] = [
                {"je_id": j.je_id, "description": j.description}
                for j in self.jes if any(l[0] == line["account"] for l in j.lines)]
        return lines

    def record_flux_commentary(self, comments: dict) -> dict:
        self._require("flux")
        unknown = [a for a in comments if a not in set(self.flux.account)]
        for account, text in comments.items():
            self.flux.loc[self.flux.account == account, "commentary"] = text
        missing = self.flux[self.flux.needs_commentary & (self.flux.commentary == "")].account.tolist()
        self.log.append("flux_commentary")
        return {"recorded": len(comments) - len(unknown), "unknown_accounts": unknown,
                "flagged_lines_without_commentary": missing}

    def build_financials(self) -> dict:
        self._require("atb", "bank", "recs", "jes")
        self.fs = reports.financial_statements(self.atb)
        self.checks = reports.tie_out_checks(self.inputs, self.atb, self.jes, self.bank, self.recs, self.fs)
        self.log.append("financials")
        return {"financial_statements": self.fs, "tie_out_checks": self.checks}

    def open_items(self) -> list[dict]:
        items = []
        for r in self.recs or []:
            if not r["reconciled"]:
                items.append({"area": r["name"], "amount": r["difference"],
                              "detail": f"GL {r['gl_balance']:,.2f} vs {r['support_source']} "
                                        f"{r['support_balance']:,.2f}. Investigate before close; no JE proposed."})
        for j in self.jes or []:
            if j.needs_approval:
                items.append({"area": f"{j.je_id} approval", "amount": j.amount,
                              "detail": f"{j.description} is at or above the approval threshold."})
            for f in j.flags:
                items.append({"area": j.je_id, "amount": j.amount, "detail": f})
        for c in self.checks or []:
            if not c["passed"] and " ties to " not in c["check"]:  # rec failures are listed above
                items.append({"area": "Tie-out", "amount": None, "detail": f"FAILED: {c['check']}"})
        return items

    def write_close_memo(self, memo_markdown: str) -> dict:
        self.memo = memo_markdown
        self.log.append("close_memo")
        return {"saved": True, "characters": len(memo_markdown)}
