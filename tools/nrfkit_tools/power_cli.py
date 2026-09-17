# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .power import PowerCaptureError, REQUIRED_PROFILES, summarize_capture
from .process import atomic_json
from .reference import sha256


def add_commands(subparsers: Any) -> None:
    parser = subparsers.add_parser("m7-power-audit")
    parser.add_argument(
        "--capture", action="append", required=True, metavar="PROFILE=PATH"
    )
    parser.add_argument("--instrument", required=True)
    parser.add_argument("--supply-voltage-v", type=float, required=True)
    parser.add_argument("--minimum-duration", type=float, default=1.0)
    parser.add_argument("--maximum-sample-gap-us", type=float, default=10.1)
    parser.set_defaults(handler=command)


def command(args: argparse.Namespace) -> int:
    from .cli import ToolError, _new_run, _stage

    captures: dict[str, Path] = {}
    for value in args.capture:
        profile, separator, path = value.partition("=")
        if not separator or not profile or not path:
            raise ToolError("power captures must use PROFILE=PATH")
        if profile in captures:
            raise ToolError(f"duplicate power capture profile: {profile}")
        captures[profile] = Path(path)
    if set(captures) != set(REQUIRED_PROFILES):
        missing = sorted(set(REQUIRED_PROFILES) - set(captures))
        extra = sorted(set(captures) - set(REQUIRED_PROFILES))
        raise ToolError(
            "power capture profiles do not match the contract; "
            f"missing={missing}, extra={extra}"
        )

    run_dir, report = _new_run("m7-power-audit")
    report.update({
        "status": "running",
        "stages": [],
        "instrument": args.instrument,
        "supply_voltage_v": args.supply_voltage_v,
        "minimum_duration_s": args.minimum_duration,
        "maximum_sample_gap_us": args.maximum_sample_gap_us,
    })
    atomic_json(run_dir / "run.json", report)
    try:
        summaries: dict[str, dict[str, Any]] = {}
        for profile in REQUIRED_PROFILES:
            path = captures[profile]
            summary = summarize_capture(
                path,
                supply_voltage_v=args.supply_voltage_v,
                minimum_duration_s=args.minimum_duration,
                maximum_sample_gap_s=args.maximum_sample_gap_us / 1_000_000.0,
            )
            summary["capture_sha256"] = sha256(path)
            summaries[profile] = summary
            _stage(run_dir, report, "power-capture", profile=profile, **summary)
        idle = summaries["idle"]["average_current_a"]
        ble = summaries["ble"]["average_current_a"]
        comparison = {
            "direct_1m_incremental_current_a":
                summaries["direct-1m"]["average_current_a"] - idle,
            "direct_2m_incremental_current_a":
                summaries["direct-2m"]["average_current_a"] - idle,
            "direct_4m_incremental_current_a":
                summaries["direct-4m"]["average_current_a"] - idle,
            "timeslot_retry_4m_incremental_current_a":
                summaries["timeslot-retry-4m"]["average_current_a"] - idle,
            "ble_timeslot_4m_incremental_current_a":
                summaries["ble-timeslot-4m"]["average_current_a"] - ble,
        }
        _stage(run_dir, report, "power-comparison", **comparison)
        report.update(status="ok", captures=summaries, comparison=comparison)
    except (OSError, PowerCaptureError) as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise ToolError(str(error)) from error
    finally:
        atomic_json(run_dir / "run.json", report)
    print(run_dir / "run.json")
    return 0
