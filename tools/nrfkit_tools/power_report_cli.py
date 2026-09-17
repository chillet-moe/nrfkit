# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .power_report import PowerReportError, generate_report


def add_commands(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "power-report", help="generate an offline report for a BLU939 suite"
    )
    parser.add_argument("run", nargs="?", type=Path)
    parser.add_argument("--output", type=Path)
    parser.set_defaults(handler=command)


def _latest_successful(runs: Path) -> Path:
    for directory in sorted(
        runs.glob("*-blu939-suite-*"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ):
        report = directory / "run.json"
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("operation") == "blu939-suite" and data.get("status") == "ok":
            return report
    raise PowerReportError("no successful BLU939 suite report was found")


def command(args: argparse.Namespace) -> int:
    from .cli import ToolError, project_root

    try:
        report = args.run or _latest_successful(
            project_root() / ".work/power/runs"
        )
        print(generate_report(report, args.output))
    except PowerReportError as error:
        raise ToolError(str(error)) from error
    return 0
