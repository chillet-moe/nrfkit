# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import argparse
import math
from pathlib import Path
import time
from typing import Any

from .blu939 import Blu939, Blu939Error, decode_capture, discover, select
from .process import atomic_json
from .reference import sha256


def add_commands(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "blu939", help="BLU939 discovery, power and bounded current captures"
    )
    actions = parser.add_subparsers(dest="blu939_action", required=True)
    for name in ("info", "power", "capture"):
        action = actions.add_parser(name)
        action.add_argument("--instrument-serial")
        if name == "info":
            action.add_argument("--list-only", action="store_true")
        else:
            action.add_argument("--voltage-mv", type=int)
        if name == "power":
            action.add_argument("--state", choices=("on", "off"), required=True)
            action.add_argument("--duration", type=float, default=60)
        if name == "capture":
            action.add_argument("--duration", type=float, default=10)
            action.add_argument("--settle", type=float, default=0)
            action.add_argument("--power-cycle", action="store_true")
            action.add_argument("--hold-after", type=float, default=0)
            action.add_argument("--label", required=True)
            action.add_argument("--manifest", type=Path)
        action.set_defaults(handler=command)


def command(args: argparse.Namespace) -> int:
    from .cli import _new_run, _probe_lock, load_manifest

    run_dir, report = _new_run("blu939-" + args.blu939_action)
    instrument = None
    try:
        if getattr(args, "manifest", None):
            manifest = load_manifest(args.manifest)
            report["firmware"] = {
                "manifest_sha256": sha256(args.manifest),
                "elf_sha256": manifest["debug_elf"]["sha256"],
                "identity_only": True,
            }
        voltage_mv = getattr(args, "voltage_mv", None)
        if voltage_mv is not None and not 500 <= voltage_mv <= 5000:
            raise Blu939Error("BLU939 voltage must be 500..5000 mV")
        if args.blu939_action == "power" and (
            not math.isfinite(args.duration) or not 1 <= args.duration <= 600
        ):
            raise Blu939Error("power session duration must be 1..600 seconds")
        if args.blu939_action == "capture":
            if (
                not math.isfinite(args.duration)
                or not 0.01 <= args.duration <= 600
                or not math.isfinite(args.settle)
                or not 0 <= args.settle <= 60
                or not math.isfinite(args.hold_after)
                or not 0 <= args.hold_after <= 60
            ):
                raise Blu939Error("invalid duration, settle or hold-after interval")
            if args.power_cycle and voltage_mv is None:
                raise Blu939Error("power-cycle requires an explicit voltage")
            if args.hold_after and not args.power_cycle:
                raise Blu939Error("hold-after requires power-cycle")
            report["label"] = args.label
        report["devices"] = discover(args.instrument_serial)
        if args.blu939_action == "info" and args.list_only:
            report["status"] = "ok"
        else:
            device = select(args.instrument_serial)
            with _probe_lock(
                "blu939:" + device["serial"], "blu939-" + args.blu939_action
            ):
                try:
                    instrument = Blu939(device["port"])
                    metadata = instrument.metadata()
                    report["metadata_before"] = metadata
                    atomic_json(run_dir / "run.json", report)
                    if args.blu939_action == "power":
                        if args.state == "on":
                            if voltage_mv is None:
                                raise Blu939Error("power on requires an explicit voltage")
                            instrument.power(False)
                            metadata = instrument.configure_voltage(voltage_mv)
                            report["metadata_after"] = metadata
                        instrument.power(args.state == "on")
                        report["output_requested"] = args.state
                        report["output_state_readback_available"] = False
                        if args.state == "on":
                            report["hold_duration_s"] = args.duration
                            report["phase"] = "powered"
                            atomic_json(run_dir / "run.json", report)
                            print(
                                f"BLU939 power session ready: {run_dir / 'run.json'}",
                                flush=True,
                            )
                            time.sleep(args.duration)
                    elif args.blu939_action == "capture":
                        if args.power_cycle:
                            instrument.power(False)
                            metadata = instrument.configure_voltage(voltage_mv)
                            time.sleep(0.5)
                            instrument.power(True)
                        elif voltage_mv is not None and metadata.get("vdd") != voltage_mv:
                            raise Blu939Error(
                                "requested voltage differs from the BLU939 setting"
                            )
                        voltage = metadata.get("vdd")
                        if (
                            not isinstance(voltage, (int, float))
                            or not 500 <= voltage <= 5000
                        ):
                            raise Blu939Error(
                                "BLU939 did not report a valid configured voltage"
                            )
                        report["metadata"] = metadata
                        time.sleep(args.settle)
                        raw = run_dir / "samples.bin"
                        report["acquisition"] = instrument.capture(raw, args.duration)
                        report["raw_sha256"] = sha256(raw)
                        csv_path = run_dir / "current.csv"
                        report["summary"] = decode_capture(
                            raw, csv_path, metadata, int(voltage)
                        )
                        report["csv"] = str(csv_path)
                        report["csv_sha256"] = sha256(csv_path)
                        if args.hold_after:
                            report["phase"] = "post-capture-powered"
                            report["hold_after_s"] = args.hold_after
                            atomic_json(run_dir / "run.json", report)
                            print(
                                f"BLU939 capture complete; inspection window: "
                                f"{run_dir / 'run.json'}",
                                flush=True,
                            )
                            time.sleep(args.hold_after)
                    report["status"] = "ok"
                finally:
                    if instrument is not None:
                        try:
                            response = getattr(instrument, "last_metadata_response", b"")
                            if isinstance(response, bytes) and response:
                                metadata_raw = run_dir / "metadata-response.bin"
                                metadata_raw.write_bytes(response)
                                report["metadata_response"] = {
                                    "path": str(metadata_raw),
                                    "bytes": len(response),
                                    "sha256": sha256(metadata_raw),
                                }
                            if (
                                args.blu939_action == "capture" and args.power_cycle
                            ) or (
                                args.blu939_action == "power" and args.state == "on"
                            ):
                                instrument.power(False)
                                report["cleanup_output_requested"] = "off"
                        finally:
                            instrument.close()
                            instrument = None
    except BaseException as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        atomic_json(run_dir / "run.json", report)
    print(run_dir / "run.json")
    return 0
