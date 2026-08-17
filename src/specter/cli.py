"""`python -m specter.cli <subcommand>`. The only module CLAUDE.md permits to
`print` — everything else stays on `structlog`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_LEDGER_PATH = _REPO_ROOT / "data" / "ledger.sqlite"


def _dashboard(args: argparse.Namespace) -> None:
    from specter.obs.dashboard import print_dashboard

    print_dashboard(args.ledger_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="specter", description="Project Specter CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dashboard_parser = subparsers.add_parser(
        "dashboard", help="Print the per-agent LLM call ledger (plan §11)."
    )
    dashboard_parser.add_argument(
        "--ledger-path",
        type=Path,
        default=_DEFAULT_LEDGER_PATH,
        help=f"Path to the ledger SQLite file (default: {_DEFAULT_LEDGER_PATH}).",
    )
    dashboard_parser.set_defaults(func=_dashboard)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
