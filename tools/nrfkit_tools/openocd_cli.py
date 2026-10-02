# SPDX-License-Identifier: BSD-3-Clause
"""Opt-in OpenOCD commands, sharing the SDK's manifest and run contracts."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from .image import parse_ihex, require_allowed
from .openocd import (
    IDENTIFY,
    RRAM_END,
    OpenOcd,
    OpenOcdError,
    addressed_hex,
    discover,
    observation_path_valid,
    parse_identity,
    system_control_observation_address,
    tcl_word,
)
from .process import atomic_json, run_logged
from .reference import sha256


def add_commands(subparsers: Any) -> None:
    parser = subparsers.add_parser("openocd", help="guarded LM20 CMSIS-DAP backend")
    actions = parser.add_subparsers(dest="openocd_action", required=True)
    for name in ("list", "info", "backup", "flash", "restore", "reset", "gdb-smoke", "clear-rram"):
        action = actions.add_parser(name)
        action.add_argument("--probe-serial")
        action.add_argument("--vid", type=lambda v: int(v, 0), default=0x0d28)
        action.add_argument("--pid", type=lambda v: int(v, 0), default=0x0204)
        action.add_argument("--timeout", type=float, default=90)
        if name != "list":
            action.add_argument("--openocd", type=Path, required=True)
            action.add_argument("--scripts", type=Path, required=True)
            action.add_argument("--speed-khz", type=int, choices=(1000, 2000, 4000), default=1000)
        if name == "reset":
            action.add_argument("--diagnostics", action="store_true",
                                help="record detailed OpenOCD reset diagnostics")
            reset_mode = action.add_mutually_exclusive_group()
            reset_mode.add_argument("--halt", action="store_true",
                                    help="halt at the reset vector using checked system reset")
            reset_mode.add_argument("--pin", action="store_true",
                                    help="pulse wired SRST for physical recovery; runs firmware")
        if name in ("backup", "flash", "restore", "gdb-smoke"):
            action.add_argument("--manifest", type=Path, required=True, action="append" if name == "backup" else "store")
        if name == "restore":
            action.add_argument("--backup-report", type=Path, required=True)
        if name in ("backup", "restore"):
            action.add_argument("--include-settings", action="store_true",
                                help="also preserve the ordinary settings region declared by the audited ELF")
        if name == "gdb-smoke":
            action.add_argument("--gdb", required=True)
            action.add_argument("--attach", action="store_true")
            action.add_argument("--runtime-contract", action="store_true")
            action.add_argument("--observe", action="append", default=[])
            action.add_argument("--observe-system-control", action="append", default=[])
        action.set_defaults(handler=command)


def _settings_span(manifest: dict[str, Any]) -> tuple[int, int]:
    layout = manifest.get("image_layout", {})
    symbols = layout.get("symbols", {})
    start = symbols.get("__nrfkit_settings_start")
    end = symbols.get("__nrfkit_settings_end")
    if (layout.get("source") != "elf-symbols" or not isinstance(start, int) or
            not isinstance(end, int) or start % 16 or end % 16):
        raise OpenOcdError("settings backup requires an audited ELF with aligned settings bounds")
    require_allowed(((start, end),), ((0, RRAM_END),))
    if start >= end or any(start < b and a < end for a, b in manifest["debug_allowlist"]):
        raise OpenOcdError("settings must be a separate nonempty ordinary RRAM region")
    return start, end


def _backup(backend: OpenOcd, manifests: list[dict[str, Any]], report: dict[str, Any],
            *, include_settings: bool = False) -> None:
    # Save only bytes that the selected test images can overwrite, rounded to the
    # RRAM data unit. Adjacent bytes are checked against each manifest's allowlist.
    ranges = []
    for manifest in manifests:
        if include_settings:
            ranges.append(_settings_span(manifest))
        for item in manifest["images"]:
            for start, end in item["ranges"]:
                span = (start // 16 * 16, (end + 15) // 16 * 16)
                require_allowed((span,), tuple(map(tuple, item["allowlist"])))
                ranges.append(span)
    _backup_ranges(backend, ranges, report)
    report["includes_declared_settings"] = include_settings


def _backup_ranges(backend: OpenOcd, ranges: list[tuple[int, int]],
                   report: dict[str, Any]) -> None:
    require_allowed(tuple(ranges), ((0, RRAM_END),))
    if not ranges or any(start % 16 or end % 16 or start >= end for start, end in ranges):
        raise OpenOcdError("backup ranges must contain aligned ordinary RRAM")
    merged: list[list[int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    commands = ["halt"]
    for index, (start, end) in enumerate(merged):
        for repeat in (1, 2):
            path = backend.run_dir / f"backup-{index}-{repeat}.bin"
            commands.append(f"dump_image {tcl_word(path)} {start} {end-start}")
    output = backend.run("backup", "\n".join(commands))
    report["target"] = parse_identity(output)
    backups = []
    for index, (start, end) in enumerate(merged):
        first = backend.run_dir / f"backup-{index}-1.bin"
        second = backend.run_dir / f"backup-{index}-2.bin"
        data = first.read_bytes()
        if len(data) != end-start or data != second.read_bytes():
            raise OpenOcdError("two independent backup reads differ")
        path = backend.run_dir / f"backup-{index}.hex"
        path.write_text(addressed_hex(start, data), encoding="ascii")
        path.chmod(0o400)
        first.chmod(0o400)
        second.chmod(0o400)
        backups.append({"path": str(path), "sha256": sha256(path), "range": [start, end]})
    report["backups"] = backups
    report["target_state"] = "halted"


def _clear_rram(backend: OpenOcd, report: dict[str, Any]) -> None:
    # An explicit maintenance operation over the fixed ordinary RRAM bank.
    # Writing FF avoids CTRL-AP ERASEALL and all configuration-memory banks.
    cleared = bytes([0xff]) * RRAM_END
    snapshot = backend.run_dir / "clear-rram.hex"
    snapshot.write_text(addressed_hex(0, cleared), encoding="ascii")
    snapshot.chmod(0o400)
    image = parse_ihex(snapshot)
    require_allowed(image.ranges, ((0, RRAM_END),))
    if image.ranges != ((0, RRAM_END),):
        raise OpenOcdError("clear snapshot does not cover exactly ordinary RRAM")
    report["clear_range"] = [0, RRAM_END]
    report["clear_sha256"] = sha256(snapshot)
    _backup_ranges(backend, [(0, RRAM_END)], report)
    # Publish the original bytes before the first write, including on failure.
    backup_report = backend.run_dir / "backup.json"
    atomic_json(backup_report, {
        "operation": "openocd-backup", "status": "ok",
        "target": report["target"], "backups": report["backups"],
        "target_state": "halted", "range": [0, RRAM_END],
    })
    report["backup_report"] = str(backup_report)
    target = report["target"]
    device_id = target["device_id"]
    # Reject a different LM20 if the physical connection changed after backup.
    identity_guard = (
        f'if {{$part != {target["part"]} || $variant != {target["variant"]} || '
        f'[lindex [read_memory 0x00ffc304 32 1] 0] != 0x{device_id[:8]} || '
        f'[lindex [read_memory 0x00ffc308 32 1] 0] != 0x{device_id[8:]}}} '
        '{error "target changed after backup"}'
    )
    readback = backend.run_dir / "clear-readback.bin"
    report["target_state"] = "unverified"
    backend.run("clear", "\n".join([
        identity_guard, "halt", f"flash write_image {tcl_word(snapshot)}",
        f"verify_image {tcl_word(snapshot)}",
        f"dump_image {tcl_word(readback)} 0 {RRAM_END}",
    ]))
    if readback.read_bytes() != cleared:
        raise OpenOcdError("ordinary RRAM clear readback mismatch")
    report.update(clear_verified=True, target_state="halted",
                  readback_sha256=sha256(readback))


def _restore(backend: OpenOcd, manifest: dict[str, Any], path: Path, report: dict[str, Any],
             *, include_settings: bool = False) -> None:
    backup = json.loads(path.read_text())
    if (backup.get("operation") != "openocd-backup" or backup.get("status") != "ok"
            or not backup.get("backups") or not backup.get("target")):
        raise OpenOcdError("a successful OpenOCD backup report is required")
    snapshots = []
    allowlist = tuple(map(tuple, manifest["debug_allowlist"]))
    if include_settings:
        allowlist += (_settings_span(manifest),)
    for index, item in enumerate(backup["backups"]):
        source = Path(item["path"])
        destination = backend.run_dir / f"restore-{index}.hex"
        shutil.copyfile(source, destination)
        destination.chmod(0o400)
        if sha256(destination) != item["sha256"]:
            raise OpenOcdError("backup artifact changed")
        image = parse_ihex(destination)
        require_allowed(image.ranges, allowlist)
        require_allowed(image.ranges, ((0, RRAM_END),))
        if image.ranges != (tuple(item["range"]),):
            raise OpenOcdError("backup range does not match its receipt")
        snapshots.append(destination)
    current = parse_identity(backend.run("restore-identity", ""))
    if current != backup["target"]:
        raise OpenOcdError("backup belongs to a different target")
    report["target"] = current
    commands = ["halt"]
    for snapshot in snapshots:
        commands += [f"flash write_image {tcl_word(snapshot)}", f"verify_image {tcl_word(snapshot)}"]
    backend.run("restore", "\n".join(commands))
    report.update(restore_verified=True, target_state="halted", backup_report=str(path.resolve()))


def _gdb(backend: OpenOcd, manifest: dict[str, Any], args: argparse.Namespace, report: dict[str, Any]) -> None:
    if args.attach and args.runtime_contract:
        raise OpenOcdError("attach and runtime contract are mutually exclusive")
    if any(not observation_path_valid(path) for path in args.observe):
        raise OpenOcdError("observations must name C identifiers or member paths")
    system_control_observations = [
        system_control_observation_address(value)
        for value in args.observe_system_control
    ]
    elf = backend.run_dir / "debug.elf"
    shutil.copyfile(manifest["debug_elf"]["path"], elf)
    elf.chmod(0o400)
    if sha256(elf) != manifest["debug_elf"]["sha256"]:
        raise OpenOcdError("debug ELF changed while taking snapshot")
    gdb = Path(args.gdb).resolve()
    if not os.access(gdb, os.X_OK):
        raise OpenOcdError("GDB executable is missing")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    server = None
    try:
        with (backend.run_dir / "server.log").open("wb") as log:
            server = subprocess.Popen(backend.argv("server", "init\n" + IDENTIFY, gdb_port=port),
                                      stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                      start_new_session=True)
            deadline = time.monotonic() + min(20, args.timeout)
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    raise OpenOcdError("OpenOCD GDB server exited before readiness")
                if "Listening on port" in (backend.run_dir / "server.log").read_text(errors="replace"):
                    break
                time.sleep(0.05)
            else:
                raise OpenOcdError("OpenOCD GDB server readiness timed out")
            commands = ["set pagination off", "set confirm off", "set remotetimeout 10",
                        f"file {json.dumps(str(elf))}", f"target remote 127.0.0.1:{port}",
                        "monitor halt", 'printf "CPUID=%08x\\n", *(unsigned*)0xe000ed00', "info registers pc sp"]
            markers = ["CPUID="]
            if not args.attach:
                # Monitor resets do not invalidate GDB's cached registers.
                commands += ["monitor reset halt", "maintenance flush register-cache",
                             "hbreak main", "continue",
                             'printf "MAIN_REACHED\\n"', "stepi", 'printf "STEP_COMPLETE\\n"']
                markers += ["MAIN_REACHED", "STEP_COMPLETE"]
            if args.runtime_contract:
                commands += ["delete breakpoints", "hbreak nrfkit_post_main", "continue",
                             'printf "MAIN_STATE=%08x\\n", nrfkit_main_observed',
                             "set nrfkit_gdb_scratch = 0xa55a5aa5",
                             'printf "RAM_VALUE=%08x\\n", nrfkit_gdb_scratch',
                             "delete breakpoints", "monitor reset halt",
                             "maintenance flush register-cache",
                             "if $pc != ((unsigned)&Reset_Handler & ~1)",
                             "  echo Unexpected reset PC\\n", "  quit 1", "end",
                             'printf "RESET_HANDLER_REACHED\\n"',
                             "watch -l *(unsigned*)&nrfkit_gdb_scratch", "continue",
                             'printf "WATCHPOINT_VALUE=%08x\\n", nrfkit_gdb_scratch']
                markers += ["MAIN_STATE=4d324d41", "RAM_VALUE=a55a5aa5", "RESET_HANDLER_REACHED",
                            "Hardware watchpoint", "WATCHPOINT_VALUE=00000000"]
            for symbol in args.observe:
                commands += [f'printf "OBSERVE {symbol}=%08x\\n", *(unsigned*)&{symbol}']
            for address in system_control_observations:
                commands += [
                    f'printf "OBSERVE SCS_{address:08x}=%08x\\n", '
                    f'*(unsigned*)0x{address:08x}'
                ]
            commands += ["delete breakpoints", "monitor resume", "detach", "quit"]
            script = backend.run_dir / "smoke.gdb"
            script.write_text("\n".join(commands) + "\n")
            result = run_logged([str(gdb), "--nx", "--batch", "-x", str(script)],
                                backend.run_dir / "gdb.log", args.timeout)
            if result.returncode or any(m not in result.stdout for m in markers):
                raise OpenOcdError("OpenOCD GDB contract failed")
            report["target"] = parse_identity((backend.run_dir / "server.log").read_text())
            report["gdb_contract"] = markers
            report["target_state"] = "running"
    finally:
        if server is not None and server.poll() is None:
            os.killpg(server.pid, signal.SIGTERM)
            try:
                server.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(server.pid, signal.SIGKILL)
                server.wait()
        report["server_cleanup"] = server is None or server.poll() is not None


def command(args: argparse.Namespace) -> int:
    from .cli import _new_run, _probe_lock, _snapshot_hexes, load_manifest

    action = args.openocd_action
    run_dir, report = _new_run("openocd-" + action)
    try:
        # Manifest and source checks precede USB/target access.
        manifests = []
        if hasattr(args, "manifest"):
            paths = args.manifest if isinstance(args.manifest, list) else [args.manifest]
            manifests = [load_manifest(path) for path in paths]
            if any(m["soc"] != "nrf54lm20a" for m in manifests):
                raise OpenOcdError("OpenOCD workflow supports the LM20 application target only")
            report["manifests"] = [{"path": str(p.resolve()), "sha256": sha256(p)} for p in paths]
            if getattr(args, "include_settings", False):
                for manifest in manifests:
                    _settings_span(manifest)
        devices = discover(args.vid, args.pid, args.probe_serial)
        report["devices"] = devices
        if action != "list":
            if len(devices) != 1:
                raise OpenOcdError("select exactly one CMSIS-DAP bulk probe using --probe-serial")
            device = devices[0]
            backend = OpenOcd(args.openocd, args.scripts, device, run_dir, args.speed_khz, args.timeout)
            report["backend"] = backend.receipt()
            with _probe_lock(device["serial"], "openocd-" + action):
                if action == "info":
                    report["target"] = parse_identity(backend.run("info", ""))
                elif action == "clear-rram":
                    _clear_rram(backend, report)
                elif action == "backup":
                    _backup(backend, manifests, report, include_settings=args.include_settings)
                elif action == "restore":
                    _restore(backend, manifests[0], args.backup_report, report,
                             include_settings=args.include_settings)
                elif action == "flash":
                    snapshots = _snapshot_hexes(manifests[0], run_dir)
                    commands = ["halt"]
                    for path in snapshots:
                        commands += [f"flash write_image {tcl_word(path)}", f"verify_image {tcl_word(path)}"]
                    report["target"] = parse_identity(backend.run("program", "\n".join(commands)))
                    report.update(image_sha256=[sha256(p) for p in snapshots], target_state="halted")
                elif action == "reset":
                    report["target"] = parse_identity(backend.reset(halt=args.halt, diagnostics=args.diagnostics, pin=args.pin))
                    report["target_state"] = "halted" if args.halt else "running"
                elif action == "gdb-smoke":
                    _gdb(backend, manifests[0], args, report)
        report["status"] = "ok"
    except BaseException as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        atomic_json(run_dir / "run.json", report)
    print(run_dir / "run.json")
    return 0
