"""Command line entry point.

  python -m close_agent --offline            # rule-based, no API key
  python -m close_agent                      # Claude-driven (needs ANTHROPIC_API_KEY)
"""
import argparse
import os
from pathlib import Path

from .data import load_config
from .engine import CloseRun
from .export import export_package

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    p = argparse.ArgumentParser(description="Month-end close agent")
    p.add_argument("--data", type=Path, default=None, help="Folder of close inputs (default: data/<period>)")
    p.add_argument("--config", type=Path, default=ROOT / "close_config.yaml")
    p.add_argument("--out", type=Path, default=ROOT / "output")
    p.add_argument("--offline", action="store_true", help="Run without Claude (rule-based commentary)")
    p.add_argument("--model", default=None, help="Claude model (default: claude-sonnet-5-5)")
    args = p.parse_args(argv)

    data_dir = args.data or ROOT / "data" / str(load_config(args.config)["period"])
    run = CloseRun(data_dir, args.config)

    if args.offline or not os.environ.get("ANTHROPIC_API_KEY"):
        if not args.offline:
            print("ANTHROPIC_API_KEY not set: running in offline mode.")
        from .offline import run_offline
        run_offline(run)
    else:
        from .agent import run_agent
        print(f"Running close agent for {run.config['period']}...")
        run_agent(run, model=args.model)

    files = export_package(run, args.out)
    passed = sum(c["passed"] for c in run.checks)
    print(f"\nChecks passed: {passed}/{len(run.checks)} | Open items: {len(run.open_items())}")
    for label, path in files.items():
        print(f"  {label:10} {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")


if __name__ == "__main__":
    main()
