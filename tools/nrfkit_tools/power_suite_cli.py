# SPDX-License-Identifier: BSD-3-Clause
"""Autonomous BLU939 acquisition for self-running firmware profiles."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path
import signal
import subprocess
import time
from typing import Any

from .blu939 import Blu939, Blu939Error, decode_capture, select
from .device import program_argv, read_memory_argv, reset_argv, resolve_probe_alias
from .power import PowerCaptureError, REQUIRED_PROFILES, summarize_capture
from .process import atomic_json, run_logged
from .reference import sha256


def add_commands(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "blu939-suite",
        help="capture a complete self-running firmware suite and restore the target",
    )
    parser.add_argument(
        "--profile", action="append", required=True, metavar="NAME=MANIFEST",
        help="profile name and audited device manifest; repeat in execution order",
    )
    parser.add_argument("--instrument-serial")
    parser.add_argument("--probe-serial")
    parser.add_argument("--voltage-mv", type=int, required=True)
    parser.add_argument("--duration", type=float, default=18.0)
    parser.add_argument(
        "--profile-duration", action="append", default=[], metavar="NAME=SECONDS",
    )
    parser.add_argument("--settle", type=float, default=0.0)
    parser.add_argument("--instrument", default="BLU939")
    parser.add_argument("--require-m7-profiles", action="store_true")
    parser.add_argument("--openocd", type=Path, required=True)
    parser.add_argument("--scripts", type=Path, required=True)
    parser.add_argument(
        "--speed-khz", type=int, choices=(1000, 2000, 4000), default=1000,
    )
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument(
        "--peer", action="append", default=[], metavar="NAME=MANIFEST",
        help="run a validated serial-token peer during the named profile",
    )
    parser.add_argument("--peer-probe")
    parser.add_argument("--nrfutil", default="nrfutil")
    parser.add_argument("--peer-timeout", type=float, default=30.0)
    parser.add_argument(
        "--gdb",
        help="inspect workload counters after every capture before power-off",
    )
    parser.set_defaults(handler=command)


def _profiles(values: list[str]) -> list[tuple[str, Path]]:
    profiles: list[tuple[str, Path]] = []
    names: set[str] = set()
    for value in values:
        name, separator, path = value.partition("=")
        if not separator or not name or not path:
            raise ValueError("power profiles must use NAME=MANIFEST")
        if name in names:
            raise ValueError(f"duplicate power profile: {name}")
        if any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in name):
            raise ValueError(f"invalid power profile name: {name}")
        names.add(name)
        profiles.append((name, Path(path).resolve()))
    return profiles


def _child(
    argv: list[str], log: Path, timeout: float,
) -> Path:
    result = run_logged(argv, log, timeout)
    if result.returncode:
        raise RuntimeError(f"child command failed; see {log.name}")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise RuntimeError(f"child command did not return one report; see {log.name}")
    report = Path(lines[0]).resolve()
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"invalid child report from {log.name}") from error
    if data.get("status") != "ok":
        raise RuntimeError(f"unsuccessful child report from {log.name}")
    return report


def _durations(values: list[str], profile_names: set[str], default: float) -> dict[str, float]:
    durations = {name: default for name in profile_names}
    seen: set[str] = set()
    for value in values:
        name, separator, text = value.partition("=")
        if not separator or name not in profile_names or name in seen:
            raise ValueError("profile durations must uniquely use a selected NAME=SECONDS")
        try:
            duration = float(text)
        except ValueError as error:
            raise ValueError(f"invalid duration for profile {name}") from error
        if not math.isfinite(duration) or not 1.0 <= duration <= 600.0:
            raise ValueError(f"invalid duration for profile {name}")
        durations[name] = duration
        seen.add(name)
    return durations


def _terminate(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def _read_peer(
    args: argparse.Namespace,
    manifest: dict[str, Any],
    serial: str,
    output: Path,
    log: Path,
    start: int,
    end: int,
) -> None:
    result = run_logged(
        read_memory_argv(
            args.nrfutil, str(output), serial, manifest["device_family"],
            manifest["core"], start, end - start,
        ),
        log,
        args.timeout,
    )
    if result.returncode:
        raise RuntimeError("peer application backup/readback failed")


_OBSERVATIONS: dict[str, tuple[str, ...]] = {
    "idle": ("nrfkit_power_stage",),
    "direct-1m": ("nrfkit_power_stage", "nrfkit_power_packets", "nrfkit_power_batches"),
    "direct-2m": ("nrfkit_power_stage", "nrfkit_power_packets", "nrfkit_power_batches"),
    "direct-4m": ("nrfkit_power_stage", "nrfkit_power_packets", "nrfkit_power_batches"),
    "timeslot-retry-4m": ("accepted", "completed", "retries", "dropped", "grants"),
    "ble": ("nrfkit_power_stage", "nrfkit_power_ble_events"),
    "ble-timeslot-4m": (
        "nrfkit_power_stage", "nrfkit_power_ble_events",
        "nrfkit_power_timeslot_grants", "nrfkit_power_timeslot_packets",
    ),
}


def _validate_observations(profile: str, values: dict[str, int]) -> None:
    if profile == "idle" and values.get("nrfkit_power_stage") != 1:
        raise RuntimeError("idle firmware did not reach its measurement state")
    if profile.startswith("direct-") and any((
        values.get("nrfkit_power_stage") != 2,
        values.get("nrfkit_power_packets") != 1000,
        values.get("nrfkit_power_batches") != 1000,
    )):
        raise RuntimeError(f"{profile} firmware did not complete 1000 scheduled packets")
    if profile == "timeslot-retry-4m" and any((
        values.get("accepted") != 64,
        values.get("completed") != 64,
        values.get("dropped") != 0,
        not 8 <= values.get("retries", 0) <= 192,
        values.get("grants", 0) < 64,
    )):
        raise RuntimeError("Timeslot retry counters are not conserved")
    if profile == "ble" and values.get("nrfkit_power_stage") != 1:
        raise RuntimeError("BLE firmware did not enable advertising")
    if profile == "ble-timeslot-4m" and any((
        values.get("nrfkit_power_stage") != 2,
        values.get("nrfkit_power_timeslot_grants") != 8,
        values.get("nrfkit_power_timeslot_packets") != 8,
    )):
        raise RuntimeError("BLE Timeslot firmware did not complete its eight-grant burst")


def command(args: argparse.Namespace) -> int:
    from .cli import ToolError, _new_run, _probe_lock, load_manifest, project_root

    run_dir, report = _new_run("blu939-suite")
    instrument: Blu939 | None = None
    backup_report: Path | None = None
    operation_error: BaseException | None = None
    restore_error: BaseException | None = None
    peer_restore_error: BaseException | None = None
    output_on = False
    peer_process: subprocess.Popen[str] | None = None
    peer_stream: Any = None
    peer_ready: Path | None = None
    peer_backup: Path | None = None
    peer_backup_manifest: dict[str, Any] | None = None
    peer_serial: str | None = None
    peer_span: tuple[int, int] | None = None
    try:
        try:
            profiles = _profiles(args.profile)
        except ValueError as error:
            raise ToolError(str(error)) from error
        if args.require_m7_profiles and {name for name, _ in profiles} != set(REQUIRED_PROFILES):
            missing = sorted(set(REQUIRED_PROFILES) - {name for name, _ in profiles})
            extra = sorted({name for name, _ in profiles} - set(REQUIRED_PROFILES))
            raise ToolError(f"M7 profile set differs from the contract; missing={missing}, extra={extra}")
        if args.require_m7_profiles and not args.gdb:
            raise ToolError("the M7 suite requires --gdb for post-capture workload checks")
        if not 500 <= args.voltage_mv <= 5000:
            raise ToolError("BLU939 voltage must be 500..5000 mV")
        if (
            not math.isfinite(args.duration) or not 1.0 <= args.duration <= 600.0
            or not math.isfinite(args.settle) or not 0.0 <= args.settle <= 60.0
            or not math.isfinite(args.timeout) or args.timeout <= 0.0
        ):
            raise ToolError("invalid duration, settle, or timeout")
        try:
            durations = _durations(
                args.profile_duration, {name for name, _ in profiles}, args.duration,
            )
            peers = dict(_profiles(args.peer))
        except ValueError as error:
            raise ToolError(str(error)) from error
        if not set(peers).issubset({name for name, _ in profiles}):
            raise ToolError("every peer must refer to a selected power profile")
        if peers and not args.peer_probe:
            raise ToolError("peer profiles require --peer-probe")
        peer_manifests = {name: load_manifest(path) for name, path in peers.items()}
        if any(
            manifest.get("soc") != "nrf54l15"
            or manifest.get("board_version") != "PCA10156"
            for manifest in peer_manifests.values()
        ):
            raise ToolError("power-suite peers must be nRF54L15 DK application images")

        manifests = []
        for name, path in profiles:
            manifest = load_manifest(path)
            if manifest.get("soc") != "nrf54lm20a":
                raise ToolError(f"profile {name} is not an LM20 application image")
            manifests.append(manifest)
        report.update({
            "status": "running",
            "instrument": args.instrument,
            "supply_voltage_v": args.voltage_mv / 1000.0,
            "default_duration_s": args.duration,
            "settle_s": args.settle,
            "profiles": [],
            "manifests": [
                {"name": name, "path": str(path), "sha256": sha256(path)}
                for name, path in profiles
            ],
        })
        atomic_json(run_dir / "run.json", report)

        cli = str(project_root() / "tools/nrfkit")
        common = [
            "--openocd", str(args.openocd.resolve()),
            "--scripts", str(args.scripts.resolve()),
            "--speed-khz", str(args.speed_khz),
            "--timeout", str(args.timeout),
        ]
        if args.probe_serial:
            common += ["--probe-serial", args.probe_serial]
        backup_argv = [cli, "openocd", "backup", *common]
        for _, path in profiles:
            backup_argv += ["--manifest", str(path)]

        device = select(args.instrument_serial)
        with _probe_lock("blu939:" + device["serial"], "blu939-suite"):
            instrument = Blu939(device["port"])
            before = instrument.metadata()
            instrument.power(False)
            configured = instrument.configure_voltage(args.voltage_mv)
            instrument.power(True)
            output_on = True
            report["instrument_metadata_before"] = before
            report["instrument_metadata"] = configured
            backup_report = _child(
                backup_argv, run_dir / "backup.log", args.timeout + 30.0,
            )
            report["backup_report"] = str(backup_report)
            if peer_manifests:
                peer_serial = resolve_probe_alias(
                    args.peer_probe,
                    "PCA10156",
                    project_root() / ".local/hardware-aliases.json",
                )
                if peer_serial is None:
                    raise ToolError("peer probe selection did not resolve")
                peer_backup_manifest = next(iter(peer_manifests.values()))
                if any(
                    (item["device_family"], item["core"])
                    != (peer_backup_manifest["device_family"], peer_backup_manifest["core"])
                    for item in peer_manifests.values()
                ):
                    raise ToolError("peer manifests disagree on device family or core")
                ranges = [
                    tuple(span)
                    for item in peer_manifests.values()
                    for image in item["images"]
                    for span in image["ranges"]
                ]
                peer_span = (min(start for start, _ in ranges), max(end for _, end in ranges))
                peer_backup_candidate = run_dir / "peer-backup.hex"
                peer_backup_repeat = run_dir / "peer-backup-repeat.hex"
                with _probe_lock(peer_serial, "blu939-suite-peer-backup"):
                    _read_peer(
                        args, peer_backup_manifest, peer_serial, peer_backup_candidate,
                        run_dir / "peer-backup.log", *peer_span,
                    )
                    _read_peer(
                        args, peer_backup_manifest, peer_serial, peer_backup_repeat,
                        run_dir / "peer-backup-repeat.log", *peer_span,
                    )
                if sha256(peer_backup_candidate) != sha256(peer_backup_repeat):
                    raise RuntimeError("two independent peer backup reads differ")
                peer_backup = peer_backup_candidate
                peer_backup.chmod(0o400)
                peer_backup_repeat.chmod(0o400)
                report["peer_backup"] = {
                    "path": str(peer_backup),
                    "sha256": sha256(peer_backup),
                    "range": list(peer_span),
                }
            atomic_json(run_dir / "run.json", report)

            for index, ((name, path), manifest) in enumerate(zip(profiles, manifests), 1):
                if not output_on:
                    instrument.power(True)
                    output_on = True
                flash_report = _child(
                    [cli, "openocd", "flash", *common, "--manifest", str(path)],
                    run_dir / f"{index:02d}-{name}-flash.log",
                    args.timeout + 30.0,
                )
                profile_dir = run_dir / f"{index:02d}-{name}"
                profile_dir.mkdir()
                raw = profile_dir / "samples.bin"
                csv_path = profile_dir / "current.csv"

                peer_report: Path | None = None
                if name in peers:
                    peer_log = profile_dir / "peer.log"
                    peer_ready = profile_dir / "peer-ready.json"
                    peer_stream = peer_log.open("w", encoding="utf-8")
                    peer_process = subprocess.Popen(
                        [
                            cli, "run", "--manifest", str(peers[name]),
                            "--probe-serial", args.peer_probe,
                            "--ready-file", str(peer_ready),
                            "--nrfutil", args.nrfutil,
                            "--timeout", str(args.timeout),
                            "--token-timeout", str(args.peer_timeout),
                        ],
                        stdin=subprocess.DEVNULL,
                        stdout=peer_stream,
                        stderr=subprocess.STDOUT,
                        text=True,
                        start_new_session=True,
                    )
                    deadline = time.monotonic() + args.peer_timeout
                    while not peer_ready.is_file():
                        if peer_process.poll() is not None:
                            raise RuntimeError(f"peer for {name} exited before readiness")
                        if time.monotonic() >= deadline:
                            raise RuntimeError(f"peer for {name} did not become ready")
                        time.sleep(0.05)

                # The image is halted after programming. A supply cycle starts it
                # without leaving a debug session attached during acquisition.
                instrument.power(False)
                time.sleep(0.5)
                instrument.power(True)
                output_on = True
                if args.settle:
                    time.sleep(args.settle)
                duration = durations[name]
                acquisition = instrument.capture(raw, duration)
                summary = decode_capture(raw, csv_path, configured, args.voltage_mv)
                normalized = summarize_capture(
                    csv_path,
                    supply_voltage_v=args.voltage_mv / 1000.0,
                    minimum_duration_s=duration,
                    maximum_sample_gap_s=10.1e-6,
                )
                observation_report: Path | None = None
                observations: dict[str, int] = {}
                symbols = _OBSERVATIONS.get(name, ()) if args.gdb else ()
                if symbols:
                    observation_argv = [
                        cli, "openocd", "gdb-smoke", *common,
                        "--manifest", str(path), "--gdb", args.gdb, "--attach",
                    ]
                    for symbol in symbols:
                        observation_argv += ["--observe", symbol]
                    observation_report = _child(
                        observation_argv,
                        profile_dir / "observe-child.log",
                        args.timeout + 30.0,
                    )
                    transcript = observation_report.with_name("gdb.log").read_text(
                        encoding="utf-8", errors="replace"
                    )
                    for symbol in symbols:
                        match = re.search(
                            rf"^OBSERVE {re.escape(symbol)}=([0-9a-fA-F]{{8}})$",
                            transcript,
                            re.MULTILINE,
                        )
                        if match is None:
                            raise RuntimeError(f"missing post-capture observation {symbol}")
                        observations[symbol] = int(match.group(1), 16)
                    _validate_observations(name, observations)
                instrument.power(False)
                output_on = False
                if peer_process is not None:
                    try:
                        peer_process.wait(timeout=args.peer_timeout)
                    except subprocess.TimeoutExpired as error:
                        raise RuntimeError(f"peer for {name} did not finish") from error
                    peer_stream.close()
                    peer_stream = None
                    if peer_process.returncode:
                        raise RuntimeError(f"peer for {name} failed; see peer.log")
                    lines = [
                        line for line in (profile_dir / "peer.log").read_text(
                            encoding="utf-8"
                        ).splitlines() if line.strip()
                    ]
                    if len(lines) != 1:
                        raise RuntimeError(f"peer for {name} returned no unique report")
                    peer_report = Path(lines[0]).resolve()
                    peer_process = None
                    peer_ready.unlink(missing_ok=True)
                    peer_ready = None
                entry = {
                    "name": name,
                    "manifest_sha256": sha256(path),
                    "elf_sha256": manifest["debug_elf"]["sha256"],
                    "flash_report": str(flash_report),
                    "raw": str(raw),
                    "raw_sha256": sha256(raw),
                    "csv": str(csv_path),
                    "csv_sha256": sha256(csv_path),
                    "acquisition": acquisition,
                    "decoder": summary,
                    "measurement": normalized,
                    "observations": observations,
                }
                if observation_report is not None:
                    entry["observation_report"] = str(observation_report)
                if peer_report is not None:
                    entry["peer_report"] = str(peer_report)
                report["profiles"].append(entry)
                atomic_json(run_dir / "run.json", report)

            if args.require_m7_profiles:
                measurements = {
                    item["name"]: item["measurement"] for item in report["profiles"]
                }
                idle = measurements["idle"]["average_current_a"]
                ble = measurements["ble"]["average_current_a"]
                report["comparison"] = {
                    "direct_1m_incremental_current_a":
                        measurements["direct-1m"]["average_current_a"] - idle,
                    "direct_2m_incremental_current_a":
                        measurements["direct-2m"]["average_current_a"] - idle,
                    "direct_4m_incremental_current_a":
                        measurements["direct-4m"]["average_current_a"] - idle,
                    "timeslot_retry_4m_incremental_current_a":
                        measurements["timeslot-retry-4m"]["average_current_a"] - idle,
                    "ble_timeslot_4m_incremental_current_a":
                        measurements["ble-timeslot-4m"]["average_current_a"] - ble,
                }
        report["status"] = "captured"
    except BaseException as error:
        operation_error = error
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
    finally:
        if peer_process is not None:
            _terminate(peer_process)
        if peer_stream is not None:
            peer_stream.close()
        if peer_ready is not None:
            peer_ready.unlink(missing_ok=True)
        if instrument is not None:
            if output_on:
                try:
                    instrument.power(False)
                    output_on = False
                except BaseException as error:
                    report["output_off_error"] = f"{type(error).__name__}: {error}"
            instrument.close()

        if backup_report is not None:
            try:
                # Restoration needs target power, but the output is always turned
                # off again even when verification fails.
                device = select(args.instrument_serial)
                with _probe_lock("blu939:" + device["serial"], "blu939-suite-restore"):
                    instrument = Blu939(device["port"])
                    instrument.power(False)
                    instrument.configure_voltage(args.voltage_mv)
                    time.sleep(0.5)
                    instrument.power(True)
                    output_on = True
                    cli = str(project_root() / "tools/nrfkit")
                    common = [
                        "--openocd", str(args.openocd.resolve()),
                        "--scripts", str(args.scripts.resolve()),
                        "--speed-khz", str(args.speed_khz),
                        "--timeout", str(args.timeout),
                    ]
                    if args.probe_serial:
                        common += ["--probe-serial", args.probe_serial]
                    restore_manifest = _profiles(args.profile)[0][1]
                    restore_report = _child(
                        [
                            cli, "openocd", "restore", *common,
                            "--manifest", str(restore_manifest),
                            "--backup-report", str(backup_report),
                        ],
                        run_dir / "restore.log", args.timeout + 30.0,
                    )
                    report["restore_report"] = str(restore_report)
                    report["restore_verified"] = True
                    instrument.power(False)
                    output_on = False
            except BaseException as error:
                restore_error = error
                report["status"] = "failed"
                report["restore_error"] = f"{type(error).__name__}: {error}"
            finally:
                if instrument is not None:
                    if output_on:
                        try:
                            instrument.power(False)
                        except BaseException as error:
                            report["restore_output_off_error"] = (
                                f"{type(error).__name__}: {error}"
                            )
                    instrument.close()
        if (
            peer_backup is not None and peer_backup_manifest is not None
            and peer_serial is not None and peer_span is not None
        ):
            try:
                with _probe_lock(peer_serial, "blu939-suite-peer-restore"):
                    restored = run_logged(
                        program_argv(
                            args.nrfutil, str(peer_backup), peer_serial,
                            peer_backup_manifest["device_family"],
                            peer_backup_manifest["core"],
                        ),
                        run_dir / "peer-restore.log",
                        args.timeout,
                    )
                    if restored.returncode:
                        raise RuntimeError("peer restoration program failed")
                    readback = run_dir / "peer-restored.hex"
                    _read_peer(
                        args, peer_backup_manifest, peer_serial, readback,
                        run_dir / "peer-restore-readback.log", *peer_span,
                    )
                    if sha256(readback) != sha256(peer_backup):
                        raise RuntimeError("peer restoration readback differs from backup")
                    reset = run_logged(
                        reset_argv(
                            args.nrfutil, peer_serial,
                            peer_backup_manifest["device_family"],
                            peer_backup_manifest["core"], "RESET_PIN",
                        ),
                        run_dir / "peer-restore-reset.log",
                        args.timeout,
                    )
                    if reset.returncode:
                        raise RuntimeError("peer reset after restoration failed")
                report["peer_restore_verified"] = True
            except BaseException as error:
                peer_restore_error = error
                report["status"] = "failed"
                report["peer_restore_error"] = f"{type(error).__name__}: {error}"
        if operation_error is None and restore_error is None:
            report["status"] = "ok" if peer_restore_error is None else "failed"
        report["cleanup"] = {
            "output_requested": "off",
            "restore_required": backup_report is not None,
            "restore_verified": restore_error is None and backup_report is not None,
            "peer_restore_required": peer_backup is not None,
            "peer_restore_verified": peer_backup is not None and peer_restore_error is None,
        }
        atomic_json(run_dir / "run.json", report)

    if restore_error is not None:
        if operation_error is not None:
            raise ToolError(
                f"suite failed ({operation_error}); restoration also failed: {restore_error}"
            ) from restore_error
        raise ToolError(f"restoration failed: {restore_error}") from restore_error
    if peer_restore_error is not None:
        if operation_error is not None:
            raise ToolError(
                f"suite failed ({operation_error}); peer restoration also failed: "
                f"{peer_restore_error}"
            ) from peer_restore_error
        raise ToolError(f"peer restoration failed: {peer_restore_error}") from peer_restore_error
    if operation_error is not None:
        if isinstance(operation_error, (ToolError, Blu939Error, PowerCaptureError)):
            raise operation_error
        raise ToolError(str(operation_error)) from operation_error
    print(run_dir / "run.json")
    return 0
