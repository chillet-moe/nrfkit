# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import argparse
import math
from pathlib import Path
import time
from typing import Any

from .ppk2 import Ppk2, Ppk2Error, decode_capture, discover, select
from .process import atomic_json
from .reference import sha256


def add_commands(subparsers: Any) -> None:
    parser = subparsers.add_parser("ppk2", help="PPK2 discovery, power and bounded current captures")
    actions = parser.add_subparsers(dest="ppk_action", required=True)
    for name in ("info", "power", "capture"):
        action = actions.add_parser(name)
        action.add_argument("--ppk-serial")
        if name == "info":
            action.add_argument("--list-only", action="store_true")
        else:
            action.add_argument("--voltage-mv", type=int)
        if name == "power":
            action.add_argument("--state", choices=("on", "off"), required=True)
            action.add_argument("--duration", type=float, default=60,
                                help="keep the source connection open for 1..600 seconds, then turn off")
        if name == "capture":
            action.add_argument("--duration", type=float, default=10)
            action.add_argument("--settle", type=float, default=0)
            action.add_argument("--power-cycle", action="store_true",
                                help="cold-start DUT and request power off in cleanup")
            action.add_argument("--hold-after", type=float, default=0,
                                help="with --power-cycle, keep power on 0..60 seconds after capture for inspection")
            action.add_argument("--label", required=True)
            action.add_argument("--manifest", type=Path,
                                help="bind audited firmware identity; does not program it")
        action.set_defaults(handler=command)


def command(args: argparse.Namespace) -> int:
    from .cli import _new_run, _probe_lock, load_manifest
    run_dir, report = _new_run("ppk2-" + args.ppk_action)
    instrument = None
    try:
        if getattr(args, "manifest", None):
            manifest = load_manifest(args.manifest)
            report["firmware"] = {"manifest_sha256": sha256(args.manifest),
                                  "elf_sha256": manifest["debug_elf"]["sha256"],
                                  "identity_only": True}
        if getattr(args, "voltage_mv", None) is not None and not 800 <= args.voltage_mv <= 5000:
            raise Ppk2Error("PPK2 voltage must be 800..5000 mV; choose the DUT's allowed voltage")
        if args.ppk_action == "power" and (
                not math.isfinite(args.duration) or not 1 <= args.duration <= 600):
            raise Ppk2Error("power session duration must be 1..600 seconds")
        if args.ppk_action == "capture":
            hold_after = getattr(args, "hold_after", 0)
            if (not math.isfinite(args.duration) or not 0.01 <= args.duration <= 600
                    or not math.isfinite(args.settle) or not 0 <= args.settle <= 60):
                raise Ppk2Error("invalid duration or settle interval")
            if args.power_cycle and args.voltage_mv is None:
                raise Ppk2Error("power-cycle requires an explicit voltage")
            if (not math.isfinite(hold_after) or not 0 <= hold_after <= 60 or
                    (hold_after and not args.power_cycle)):
                raise Ppk2Error("hold-after requires power-cycle and must be 0..60 seconds")
            report["label"] = args.label
        report["devices"] = discover(args.ppk_serial)
        if args.ppk_action == "info" and args.list_only:
            report["status"] = "ok"
        else:
            device = select(args.ppk_serial)
            with _probe_lock("ppk2:" + device["serial"], "ppk2-" + args.ppk_action):
                try:
                    instrument = Ppk2(device["port"])
                    metadata = instrument.metadata()
                    report["metadata_before"] = metadata
                    atomic_json(run_dir / "run.json", report)
                    if args.ppk_action == "power":
                        if args.state == "on":
                            if args.voltage_mv is None:
                                raise Ppk2Error("power on requires an explicit voltage")
                            instrument.power(False)
                            report["metadata_after"] = instrument.configure(args.voltage_mv, "source")
                        instrument.power(args.state == "on")
                        report["output_requested"] = args.state
                        report["output_state_readback_available"] = False
                        if args.state == "on":
                            report["hold_duration_s"] = args.duration
                            report["phase"] = "powered"
                            atomic_json(run_dir / "run.json", report)
                            print(f"PPK2 power session ready: {run_dir / 'run.json'}", flush=True)
                            # PPK2 disables output when its serial connection closes.
                            time.sleep(args.duration)
                    elif args.ppk_action == "capture":
                        if args.power_cycle:
                            instrument.power(False)
                            metadata = instrument.configure(args.voltage_mv, "source")
                            time.sleep(0.5)
                            instrument.power(True)
                        elif args.voltage_mv is not None and metadata.get("vdd") != args.voltage_mv:
                            raise Ppk2Error("requested voltage differs from current PPK2 setting")
                        voltage = metadata.get("vdd")
                        if not isinstance(voltage, (int, float)) or not 800 <= voltage <= 5000:
                            raise Ppk2Error("PPK2 did not report a valid configured voltage")
                        report["metadata"] = metadata
                        time.sleep(args.settle)
                        raw = run_dir / "samples.bin"
                        report["acquisition"] = instrument.capture(raw, args.duration)
                        report["raw_sha256"] = sha256(raw)
                        csv_path = run_dir / "current.csv"
                        report["summary"] = decode_capture(raw, csv_path, metadata, int(voltage))
                        report["csv"] = str(csv_path)
                        report["csv_sha256"] = sha256(csv_path)
                        if hold_after:
                            report["phase"] = "post-capture-powered"
                            report["hold_after_s"] = hold_after
                            atomic_json(run_dir / "run.json", report)
                            print(f"PPK2 capture complete; inspection window: {run_dir / 'run.json'}",
                                  flush=True)
                            time.sleep(hold_after)
                    report["status"] = "ok"
                finally:
                    if instrument is not None:
                        try:
                            if ((args.ppk_action == "capture" and args.power_cycle) or
                                    (args.ppk_action == "power" and args.state == "on")):
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
