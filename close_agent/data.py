"""Load the close inputs and config."""
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

REQUIRED_FILES = [
    "chart_of_accounts.csv", "trial_balance.csv", "prior_trial_balance.csv", "budget.csv",
    "gl_cash_detail.csv", "bank_statement.csv", "bank_statement_summary.csv",
    "ar_aging.csv", "ap_aging.csv", "unrecorded_invoices.csv",
    "prepaid_schedule.csv", "fixed_asset_register.csv", "deferred_revenue_schedule.csv",
]


@dataclass
class CloseInputs:
    folder: Path
    config: dict
    frames: dict = field(default_factory=dict)
    missing: list = field(default_factory=list)

    def __getitem__(self, name: str) -> pd.DataFrame:
        return self.frames[name]

    @property
    def period_end(self) -> pd.Timestamp:
        return pd.Period(self.config["period"], freq="M").end_time.normalize()

    def tb_balance(self, account: str) -> float:
        tb = self.frames["trial_balance"]
        return float(tb.loc[tb.account == account, "balance"].sum())


def load_config(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def load_inputs(folder: Path, config: dict) -> CloseInputs:
    folder = Path(folder)
    inputs = CloseInputs(folder=folder, config=config)
    for name in REQUIRED_FILES:
        p = folder / name
        if not p.exists():
            inputs.missing.append(name)
            continue
        inputs.frames[p.stem] = pd.read_csv(p, dtype={"account": str, "expense_account": str})
    return inputs
