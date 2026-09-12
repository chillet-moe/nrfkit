# SPDX-License-Identifier: BSD-3-Clause
"""Recovery-first CLI for read-only PPK2 EEPROM audits."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import math
from pathlib import Path
import re
import time
from typing import Any

from .device import nrfutil_prefix, parse_json_lines
from .ppk2 import Ppk2, Ppk2Error, select
from .ppk2_eeprom import (
    PPK2_EEPROM_PACKAGE_SHA256,
    PPK2_EEPROM_RELEASE,
    PPK2_EEPROM_SOURCE_COMMIT,
    Ppk2EepromShell,
    eeprom_shell_ports,
    find_new_eeprom_shell_port,
    verify_calibration_bytes,
    wait_new_eeprom_shell_port,
)
from .process import atomic_json, run_logged
from .reference import sha256


def add_commands(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "ppk2-eeprom", help="temporarily load a read-only PPK2 EEPROM audit firmware",
    )
    parser.add_argument("--ppk-serial")
    parser.add_argument("--temporary-package", type=Path, required=True)
    parser.add_argument("--restore-package", type=Path, required=True)
    parser.add_argument("--restore-package-sha256", required=True)
    parser.add_argument("--nrfutil", default="nrfutil")
    parser.add_argument("--timeout", type=float, default=90)
    parser.set_defaults(handler=command)


def _run_nrfutil(argv: list[str], log: Path, timeout: float, operation: str) -> str:
    result = run_logged(argv, log, timeout)
    if result.returncode:
        raise Ppk2Error(f"nrfutil {operation} failed; see {log}")
    return result.stdout


def _nrfutil_devices(nrfutil: str, log: Path, timeout: float) -> list[dict[str, Any]]:
    output = _run_nrfutil(
        nrfutil_prefix(nrfutil) + [
            "device", "list", "--traits", "nordicDfu,nordicUsb,serialPorts",
            "--timeout-ms", str(max(100, round(timeout * 1000))),
        ],
        log,
        timeout + 5,
        "device list",
    )
    devices = parse_json_lines(output, "devices")
    if not isinstance(devices, list):
        raise Ppk2Error("nrfutil returned an invalid PPK2 device inventory")
    return devices


def _selected_nrfutil_device(
    nrfutil: str, serial: str, log: Path, timeout: float,
) -> dict[str, Any]:
    matches = [
        device for device in _nrfutil_devices(nrfutil, log, timeout)
        if device.get("serialNumber") == serial
        and device.get("traits", {}).get("nordicDfu") is True
    ]
    if len(matches) != 1:
        raise Ppk2Error("selected PPK2 did not enumerate uniquely through Nordic DFU")
    return matches[0]


def _wait_nrfutil_state(
    nrfutil: str, serial: str, state: str, run_dir: Path, timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    attempt = 0
    last_error = "device did not enumerate"
    while time.monotonic() < deadline:
        attempt += 1
        try:
            device = _selected_nrfutil_device(
                nrfutil,
                serial,
                run_dir / f"wait-{state.lower()}-{attempt:02d}.log",
                min(2, max(0.1, deadline - time.monotonic())),
            )
            if device.get("currentMcuState") == state:
                return device
            last_error = f"device is in {device.get('currentMcuState')!r} state"
        except (Ppk2Error, OSError) as error:
            last_error = str(error)
        time.sleep(0.25)
    raise Ppk2Error(f"PPK2 did not enter {state} state: {last_error}")


def _firmware_identity(
    nrfutil: str, serial: str, log: Path, timeout: float,
) -> str:
    output = _run_nrfutil(
        nrfutil_prefix(nrfutil) + [
            "device", "device-info", "--serial-number", serial,
            "--traits", "nordicDfu,nordicUsb",
        ],
        log,
        timeout,
        "device-info",
    )
    devices = parse_json_lines(output, "devices")
    if not isinstance(devices, list) or len(devices) != 1:
        raise Ppk2Error("nrfutil returned ambiguous PPK2 device info")
    identity = devices[0].get("deviceInfo", {}).get("dfuTriggerVersion", {}).get("semVer")
    if not isinstance(identity, str) or not identity.strip():
        raise Ppk2Error("PPK2 firmware did not provide a restorable identity")
    return identity


def _switch_to_bootloader(
    nrfutil: str, serial: str, run_dir: Path, timeout: float,
) -> None:
    result = run_logged(
        nrfutil_prefix(nrfutil) + [
            "device", "mcu-state-set", "Programming", "--serial-number", serial,
            "--traits", "nordicDfu",
        ],
        run_dir / "enter-bootloader.log",
        timeout,
    )
    try:
        _wait_nrfutil_state(nrfutil, serial, "Programming", run_dir, timeout)
    except BaseException as error:
        if result.returncode:
            raise Ppk2Error(
                f"nrfutil bootloader transition failed; see {run_dir / 'enter-bootloader.log'}"
            ) from error
        raise


def _program_dfu(
    nrfutil: str, serial: str, package: Path, log: Path, timeout: float,
) -> None:
    _run_nrfutil(
        nrfutil_prefix(nrfutil) + [
            "device", "program", "--firmware", str(package),
            "--serial-number", serial, "--traits", "nordicDfu",
            "--options", "mcu_end_state=NRFDL_MCU_STATE_APPLICATION",
        ],
        log,
        timeout,
        "secure DFU program",
    )


def _validate_inputs(args: argparse.Namespace) -> None:
    if not args.temporary_package.is_file() or not args.restore_package.is_file():
        raise Ppk2Error("temporary and restore DFU packages must be existing files")
    if sha256(args.temporary_package) != PPK2_EEPROM_PACKAGE_SHA256:
        raise Ppk2Error(
            f"temporary package is not pinned ppk2-eeprom {PPK2_EEPROM_RELEASE}"
        )
    if re.fullmatch(r"[0-9a-f]{64}", args.restore_package_sha256) is None:
        raise Ppk2Error("restore package SHA-256 must be 64 lowercase hexadecimal digits")
    if sha256(args.restore_package) != args.restore_package_sha256:
        raise Ppk2Error("restore package SHA-256 mismatch")
    if not math.isfinite(args.timeout) or not 10 <= args.timeout <= 300:
        raise Ppk2Error("EEPROM audit timeout must be 10..300 seconds")


def command(args: argparse.Namespace) -> int:
    from .cli import _new_run, _probe_lock

    _validate_inputs(args)
    run_dir, report = _new_run("ppk2-eeprom-audit")
    report.update({
        "temporary_firmware": {
            "project": "fabiobaltieri/ppk2-eeprom",
            "release": PPK2_EEPROM_RELEASE,
            "source_commit": PPK2_EEPROM_SOURCE_COMMIT,
            "package_sha256": PPK2_EEPROM_PACKAGE_SHA256,
        },
        "restore_firmware": {"package_sha256": args.restore_package_sha256},
        "stages": [],
    })
    operation_error: BaseException | None = None
    restoration_error: BaseException | None = None
    restoration_required = False
    shell: Ppk2EepromShell | None = None
    serial = ""
    initial_firmware = ""
    preexisting_shell_ports: set[str] = set()
    contexts = ExitStack()

    def stage(name: str, **values: Any) -> None:
        report["stages"].append({"name": name, **values})
        atomic_json(run_dir / "run.json", report)

    try:
        device = select(args.ppk_serial)
        serial = device["serial"]
        contexts.enter_context(_probe_lock("ppk2:" + serial, "ppk2-eeprom-audit"))
        initial_firmware = _firmware_identity(
            args.nrfutil, serial, run_dir / "firmware-before.log", args.timeout,
        )
        report["restore_firmware"]["expected_identity"] = initial_firmware
        stage("official-firmware-verified-before", firmware=initial_firmware)

        # Confirm exclusive serial ownership before changing firmware. Another
        # Power Profiler client must not race this indivisible transaction.
        instrument = Ppk2(device["port"])
        try:
            report["metadata_before"] = instrument.metadata()
        finally:
            instrument.close()
        stage("exclusive-instrument-access")

        # Record matching ports instead of assuming a device node or USB topology.
        # The temporary firmware must add exactly one port with its pinned USB ID.
        preexisting_shell_ports = eeprom_shell_ports()
        restoration_required = True
        _switch_to_bootloader(args.nrfutil, serial, run_dir, args.timeout)
        stage("bootloader-entered")
        _program_dfu(
            args.nrfutil, serial, args.temporary_package,
            run_dir / "program-temporary.log", args.timeout,
        )
        shell_port = wait_new_eeprom_shell_port(preexisting_shell_ports, args.timeout)
        shell = Ppk2EepromShell(shell_port)
        stage("temporary-shell-ready")

        calibration_text, calibration = shell.calibration_read()
        (run_dir / "calibration-read.txt").write_text(calibration_text, encoding="utf-8")
        raw_text_1, eeprom_1 = shell.eeprom_read()
        raw_text_2, eeprom_2 = shell.eeprom_read()
        (run_dir / "eeprom-read-1.txt").write_text(raw_text_1, encoding="utf-8")
        (run_dir / "eeprom-read-2.txt").write_text(raw_text_2, encoding="utf-8")
        eeprom_path_1 = run_dir / "eeprom-1.bin"
        eeprom_path_2 = run_dir / "eeprom-2.bin"
        eeprom_path_1.write_bytes(eeprom_1)
        eeprom_path_2.write_bytes(eeprom_2)
        if eeprom_1 != eeprom_2:
            raise Ppk2Error("two complete EEPROM reads differ")
        verify_calibration_bytes(calibration, eeprom_1)
        report["eeprom"] = {
            "size": len(eeprom_1),
            "read_count": 2,
            "reads_identical": True,
            "sha256": sha256(eeprom_path_1),
            "calibration": calibration,
        }
        stage("eeprom-read-and-cross-check", sha256=report["eeprom"]["sha256"])
    except BaseException as error:
        operation_error = error
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
    finally:
        if restoration_required and serial and initial_firmware:
            try:
                current: dict[str, Any] | None = None
                try:
                    current = _selected_nrfutil_device(
                        args.nrfutil, serial, run_dir / "restore-state.log", 2,
                    )
                except (Ppk2Error, OSError):
                    pass
                already_restored = False
                if current is not None and current.get("currentMcuState") == "Application":
                    current_firmware = _firmware_identity(
                        args.nrfutil, serial,
                        run_dir / "restore-current-firmware.log", args.timeout,
                    )
                    if current_firmware == initial_firmware:
                        already_restored = True
                    else:
                        _switch_to_bootloader(args.nrfutil, serial, run_dir, args.timeout)
                elif current is None and shell is None:
                    port = find_new_eeprom_shell_port(preexisting_shell_ports)
                    if port is None:
                        port = wait_new_eeprom_shell_port(
                            preexisting_shell_ports, min(15, args.timeout),
                        )
                    shell = Ppk2EepromShell(port)
                if shell is not None:
                    reset_error: BaseException | None = None
                    try:
                        shell.reset_to_bootloader()
                    except BaseException as error:
                        reset_error = error
                    finally:
                        shell.close()
                        shell = None
                    try:
                        _wait_nrfutil_state(
                            args.nrfutil, serial, "Programming", run_dir, args.timeout,
                        )
                    except BaseException as error:
                        if reset_error is not None:
                            raise Ppk2Error(
                                f"temporary firmware reset failed: {reset_error}"
                            ) from error
                        raise
                if not already_restored:
                    _wait_nrfutil_state(
                        args.nrfutil, serial, "Programming", run_dir, args.timeout,
                    )
                    _program_dfu(
                        args.nrfutil, serial, args.restore_package,
                        run_dir / "program-restore.log", args.timeout,
                    )
                    _wait_nrfutil_state(
                        args.nrfutil, serial, "Application", run_dir, args.timeout,
                    )
                restored_firmware = _firmware_identity(
                    args.nrfutil, serial, run_dir / "firmware-after.log", args.timeout,
                )
                if restored_firmware != initial_firmware:
                    raise Ppk2Error(
                        f"restored firmware identity is {restored_firmware!r}, expected "
                        f"the initial identity {initial_firmware!r}"
                    )
                stage("official-firmware-restored", firmware=restored_firmware)
            except BaseException as error:
                restoration_error = error
                report["restoration_error"] = f"{type(error).__name__}: {error}"
                report["status"] = "failed"
        if shell is not None:
            shell.close()
        contexts.close()
        report["cleanup"] = {
            "restoration_required": restoration_required,
            "official_firmware_restored": restoration_required and restoration_error is None,
        }
        if operation_error is None and restoration_error is None:
            report["status"] = "ok"
        atomic_json(run_dir / "run.json", report)
    if restoration_error is not None:
        if operation_error is not None:
            raise Ppk2Error(
                f"EEPROM audit failed ({operation_error}); official firmware restoration also "
                f"failed: {restoration_error}; keep the PPK2 connected for recovery"
            ) from restoration_error
        raise restoration_error
    if operation_error is not None:
        raise operation_error
    print(run_dir / "run.json")
    return 0
