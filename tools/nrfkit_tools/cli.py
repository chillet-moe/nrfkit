# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import termios
import threading
import time
import tty
from typing import Any, Iterator

from .device import (
    DeviceContractError, nrfutil_prefix, parse_json_lines, program_argv,
    read_memory_argv, reset_argv, resolve_probe_alias, safe_backend_contract,
    select_device,
)
from .bond import (
    M6_SETTINGS_RANGE, M6_SETTINGS_SIZE, M6_SETTINGS_START,
    is_m6_bond_manifest, read_exact_m6_settings, require_exact_m6_settings_image,
    write_erased_m6_settings,
)
from .ble_validation import (
    BleValidationError, bluetooth_info_argv, run_ble_validation,
    scan_ble_advertisement,
)
from .image import ImageContractError, parse_elf, parse_ihex, require_allowed
from .equivalence import audit_equivalence
from .process import atomic_json, run_logged
from .reference import (
    ReferenceContractError, build, load_receipt, official_toolchain_compiler,
    oracle, prepare, sha256,
)
from .sdk import SdkContractError, create_device_manifest
from .usb_validation import (
    UsbValidationError, run_host_resume_validation, run_power_validation,
    run_reconnect_validation, run_transfer_validation,
)


class ToolError(RuntimeError):
    pass


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def executable(value: str | None, fallback: str) -> str:
    candidate = value or shutil.which(fallback)
    if not candidate or not os.access(candidate, os.X_OK):
        raise ToolError(f"required executable is missing: {value or fallback}")
    return str(Path(candidate).resolve())


def load_manifest(path: Path, *, artifacts: bool = True) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ToolError(f"cannot read image manifest {path}: {error}") from error
    required = {
        "schema", "oracle", "source_receipt_sha256", "soc", "core", "board",
        "board_version", "device_family", "expected_token", "vcom", "debug_allowlist",
        "debug_elf", "images", "backend",
    }
    if value.get("schema") != "nrfkit-image/v1" or set(value) != required:
        raise ToolError("image manifest schema or fields are invalid")
    if value["backend"] != safe_backend_contract():
        raise ToolError("image manifest backend contract is invalid")
    if not isinstance(value["debug_allowlist"], list) or not value["debug_allowlist"]:
        raise ToolError("image manifest debug allowlist is invalid")
    if artifacts:
        artifacts = [("debug ELF", value["debug_elf"], parse_elf, value["debug_allowlist"])]
        if not isinstance(value["images"], list) or not value["images"]:
            raise ToolError("image manifest has no ordered programming images")
        if [item.get("order") for item in value["images"]] != list(range(len(value["images"]))):
            raise ToolError("image manifest programming order is invalid")
        artifacts.extend(
            (f"{item.get('domain', 'unknown')} HEX", item, parse_ihex, item.get("allowlist"))
            for item in value["images"]
        )
        for name, artifact, parser, allowlist in artifacts:
            artifact_path = Path(artifact["path"])
            if not artifact_path.is_absolute() or sha256(artifact_path) != artifact["sha256"]:
                raise ToolError(f"manifest {name} artifact is missing or stale")
            parsed = parser(artifact_path)
            if not isinstance(allowlist, list) or not allowlist:
                raise ToolError(f"manifest {name} allowlist is invalid")
            ranges = tuple(tuple(item) for item in allowlist)
            require_allowed(parsed.ranges, ranges)
            if parsed.entry is not None and artifact.get("entry") != parsed.entry:
                raise ToolError(f"manifest {name} entry is stale")
            if [list(item) for item in parsed.ranges] != artifact["ranges"]:
                raise ToolError(f"manifest {name} ranges are stale")
    return value


def _new_run(operation: str) -> tuple[Path, dict[str, Any]]:
    root = project_root()
    run_dir = root / ".work/runs" / f"{time.strftime('%Y%m%d-%H%M%S')}-{operation}-{os.getpid()}"
    run_dir.mkdir(parents=True, exist_ok=False)
    report: dict[str, Any] = {
        "schema": "nrfkit-run/v1", "operation": operation,
        "status": "running", "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    commit = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    report["sdk_commit"] = commit.stdout.strip() if commit.returncode == 0 else None
    report["sdk_dirty"] = status.returncode != 0 or bool(status.stdout.strip())
    atomic_json(run_dir / "run.json", report)
    return run_dir, report


def _initialize_device_report(
    run_dir: Path,
    report: dict[str, Any],
    manifest_path: Path,
    manifest: dict[str, Any],
    args: argparse.Namespace,
) -> None:
    report.update({
        "manifest": str(manifest_path.resolve()),
        "oracle": manifest["oracle"],
        "source_receipt_sha256": manifest["source_receipt_sha256"],
        "timeout_seconds": args.timeout,
        "tools": {
            **report.get("tools", {}),
            "nrfutil": _run_version([args.nrfutil, "--log-output", "stdout", "--version"]),
        },
    })
    report.setdefault("stages", []).append({"name": "manifest-audit", "status": "ok"})
    atomic_json(run_dir / "run.json", report)


def _stage(run_dir: Path, report: dict[str, Any], name: str, **details: Any) -> None:
    report["stages"].append({"name": name, "status": "ok", **details})
    atomic_json(run_dir / "run.json", report)


def _run_version(argv: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10
        )
        return {"argv": argv, "returncode": completed.returncode, "output": completed.stdout.strip()}
    except (OSError, subprocess.SubprocessError) as error:
        return {"argv": argv, "returncode": None, "error": str(error)}


def _default_gdb() -> str | None:
    return (
        os.environ.get("NRF_GDB")
        or shutil.which("arm-none-eabi-gdb")
        or shutil.which("gdb-multiarch")
    )


def _doctor(
    args: argparse.Namespace, *, require_debug_tools: bool = True,
) -> tuple[dict[str, Any], bool]:
    tools = {
        "cmake": _run_version([args.cmake, "--version"]),
        "ninja": _run_version([args.ninja, "--version"]),
        "west": _run_version([args.west, "--version"]),
        "nrfutil": _run_version([args.nrfutil, "--log-output", "stdout", "--version"]),
        "jlink_gdb_server": _run_version([args.jlink, "-version"]),
    }
    gdb = args.gdb or _default_gdb()
    tools["gdb"] = _run_version([gdb, "--version"]) if gdb else {
        "returncode": None,
        "error": (
            "no Arm-capable GDB was found in PATH; pass --gdb or set NRF_GDB "
            "to arm-none-eabi-gdb or gdb-multiarch"
        ),
    }
    if gdb and tools["gdb"]["returncode"] == 0:
        lock_path = project_root() / "docs/provenance/toolchains.lock"
        try:
            toolchain_lock = json.loads(lock_path.read_text(encoding="utf-8"))
            locked_hashes = {
                item["executable_sha256"]
                for item in toolchain_lock["tools"].values()
                if "executable_sha256" in item
            }
            gdb_hash = sha256(Path(gdb))
            tools["gdb"].update({"sha256": gdb_hash, "locked": gdb_hash in locked_hashes})
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
            tools["gdb"].update({"locked": False, "lock_error": str(error)})
    official_toolchain = getattr(args, "official_toolchain", None)
    if official_toolchain:
        try:
            variant, compiler = official_toolchain_compiler(official_toolchain)
            compiler_report = _run_version([str(compiler), "--version"])
            tools["official_toolchain"] = {
                "root": str(official_toolchain.resolve()), "variant": variant,
                "returncode": compiler_report["returncode"], "compiler": compiler_report,
            }
        except ReferenceContractError as error:
            tools["official_toolchain"] = {"returncode": None, "error": str(error)}
    else:
        tools["official_toolchain"] = {
            "returncode": None, "error": "an official reference toolchain was not selected",
        }
    payload = {"schema": "nrfkit-doctor/v1", "tools": tools}
    required = ["cmake", "ninja", "west", "nrfutil"]
    if require_debug_tools:
        required.extend(("jlink_gdb_server", "gdb"))
    healthy = all(tools[name].get("returncode") == 0 for name in required)
    toolchain_healthy = tools["official_toolchain"].get("returncode") == 0
    debug_healthy = not require_debug_tools or tools["gdb"].get("locked") is True
    return payload, healthy and toolchain_healthy and debug_healthy


def command_doctor(args: argparse.Namespace) -> int:
    run_dir, report = _new_run("doctor")
    payload, healthy = _doctor(args)
    report.update({"status": "ok" if healthy else "failed", "tools": payload["tools"]})
    atomic_json(run_dir / "run.json", report)
    payload["run_report"] = str((run_dir / "run.json").resolve())
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if healthy else 1


def command_prepare(args: argparse.Namespace) -> int:
    run_dir, report = _new_run("reference-prepare")
    report.update({
        "oracle": args.oracle, "source_root": str(args.root.resolve()),
        "toolchain": str(args.toolchain.resolve()),
    })
    try:
        output = prepare(project_root(), args.oracle, args.root, args.toolchain)
        report.update({"status": "ok", "source_receipt": str(output.resolve())})
    except BaseException as error:
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        atomic_json(run_dir / "run.json", report)
        raise
    atomic_json(run_dir / "run.json", report)
    print(output)
    return 0


def command_build(args: argparse.Namespace) -> int:
    output = build(
        project_root(), args.oracle, args.timeout, args.west,
        getattr(args, "profile", None),
    )
    print(output)
    return 0


def command_equivalence_audit(args: argparse.Namespace) -> int:
    project = project_root()
    app_build = args.build_dir.resolve()
    output = audit_equivalence(
        args.root, app_build,
        app_build / "compile_commands.json",
        app_build / "zephyr/include/generated/zephyr/autoconf.h",
        project / "docs/provenance/nrf-bm-hids-s115-equivalence.json",
        project / "config/nrf-bm-hids-s115-autoconf.h",
        update=args.update,
    )
    print(json.dumps({
        "status": "ok", "updated": args.update,
        "compiled_source_count": output["compiled_source_count"],
        "nrf_bm_source_count": len(output["nrf_bm_sources"]),
        "autoconf_sha256": output["autoconf"]["sha256"],
    }, indent=2, sort_keys=True))
    return 0


def command_inspect(args: argparse.Namespace) -> int:
    run_dir, report = _new_run("inspect")
    try:
        manifest = load_manifest(args.manifest)
        payload = {
        "status": "ok", "oracle": manifest["oracle"],
        "elf_entry": manifest["debug_elf"]["entry"],
        "elf_ranges": manifest["debug_elf"]["ranges"],
        "images": [{"domain": item["domain"], "ranges": item["ranges"]} for item in manifest["images"]],
        "run_report": str((run_dir / "run.json").resolve()),
        }
        report.update({
            "status": "ok", "oracle": manifest["oracle"],
            "manifest": str(args.manifest.resolve()), "audit": payload,
        })
    except BaseException as error:
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        atomic_json(run_dir / "run.json", report)
        raise
    atomic_json(run_dir / "run.json", report)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def command_sdk_manifest(args: argparse.Namespace) -> int:
    output = create_device_manifest(
        project_root(), args.build_dir, args.target, args.expected_token
    )
    print(output)
    return 0


def command_device_list(args: argparse.Namespace) -> int:
    run_dir, report = _new_run("device-list")
    report["stages"] = []
    try:
        devices = _enumerate(args.nrfutil, run_dir / "device-list.log", args.timeout)
        inventory = [
            {
                "board_version": device.get("devkit", {}).get("boardVersion"),
                "jlink": device.get("traits", {}).get("jlink") is True,
                "vcom_count": len(device.get("serialPorts", [])),
                "msd": _probe_has_msd(device),
            }
            for device in devices
        ]
        _stage(run_dir, report, "device-enumeration", inventory=inventory)
        if args.board_version is not None:
            serial = resolve_probe_alias(
                args.probe_serial, args.board_version,
                project_root() / ".local" / "hardware-aliases.json",
            )
            selected = select_device(devices, args.board_version, serial)
            _stage(
                run_dir,
                report,
                "device-selection",
                board_version=selected.get("devkit", {}).get("boardVersion"),
                jlink=selected.get("traits", {}).get("jlink") is True,
                vcom_count=len(selected.get("serialPorts", [])),
                msd=_probe_has_msd(selected),
            )
        report.update({"status": "ok", "device_count": len(devices)})
    except BaseException as error:
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        atomic_json(run_dir / "run.json", report)
        raise
    atomic_json(run_dir / "run.json", report)
    print(run_dir / "run.json")
    return 0


def _enumerate(nrfutil: str, log: Path, timeout: float) -> list[dict[str, Any]]:
    result = run_logged(nrfutil_prefix(nrfutil) + ["device", "list"], log, timeout)
    if result.returncode:
        raise ToolError("nrfutil device enumeration failed")
    devices = parse_json_lines(result.stdout, "devices")
    if not isinstance(devices, list):
        raise ToolError("nrfutil returned a non-list device inventory")
    return devices


@contextmanager
def _probe_lock(serial: str, operation: str) -> Iterator[None]:
    digest = hashlib.sha256(serial.encode()).hexdigest()[:20]
    path = Path(tempfile.gettempdir()) / f"nrfkit-{os.getuid()}-{digest}.lock"
    with path.open("a+", encoding="utf-8") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ToolError("selected probe is locked by another operation") from error
        stream.seek(0)
        stream.truncate()
        stream.write(json.dumps({"pid": os.getpid(), "operation": operation}) + "\n")
        stream.flush()
        try:
            yield
        finally:
            stream.seek(0)
            stream.truncate()
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _select(manifest: dict[str, Any], args: argparse.Namespace, run_dir: Path) -> dict[str, Any]:
    devices = _enumerate(args.nrfutil, run_dir / "device-list.log", args.timeout)
    serial = resolve_probe_alias(
        args.probe_serial, manifest["board_version"],
        project_root() / ".local" / "hardware-aliases.json",
    )
    return select_device(devices, manifest["board_version"], serial)


def _probe_has_msd(device: dict[str, Any]) -> bool:
    return any(
        interface.get("class") == 8
        or interface.get("interfaceString") == "MSD interface"
        for interface in device.get("usb", {}).get("interfaces", [])
    )


def _probe_interface_contract(device: dict[str, Any], msd_enabled: bool) -> bool:
    vcoms = {port.get("vcom") for port in device.get("serialPorts", [])}
    return (
        _probe_has_msd(device) is msd_enabled
        and vcoms == {0, 1}
        and device.get("traits", {}).get("jlink") is True
    )


def _wait_for_probe_msd_state(
    nrfutil: str,
    serial: str,
    board_version: str,
    enabled: bool,
    run_dir: Path,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    attempt = 0
    last_error = "probe did not enumerate"
    while time.monotonic() < deadline:
        attempt += 1
        remaining = max(0.1, deadline - time.monotonic())
        try:
            devices = _enumerate(
                nrfutil, run_dir / f"device-list-{attempt:02d}.log", min(5, remaining)
            )
            device = select_device(devices, board_version, serial)
            if _probe_interface_contract(device, enabled):
                return device
            last_error = "probe enumerated without the required MSD/J-Link/dual-VCOM state"
        except (DeviceContractError, ToolError, OSError) as error:
            last_error = str(error)
        time.sleep(0.25)
    state = "enabled" if enabled else "disabled"
    raise ToolError(f"J-Link MSD did not become {state}: {last_error}")


def _set_probe_msd(
    jlink: str,
    nrfutil: str,
    device: dict[str, Any],
    enabled: bool,
    run_dir: Path,
    timeout: float,
) -> dict[str, Any]:
    action = "enable" if enabled else "disable"
    command = "MSDEnable" if enabled else "MSDDisable"
    run_dir.mkdir(parents=True, exist_ok=True)
    command_file = run_dir / f"msd-{action}.jlink"
    command_file.write_text(f"{command}\nReboot force\nExit\n", encoding="ascii")
    command_file.chmod(0o400)
    serial = device["serialNumber"]
    with _probe_lock(serial, f"probe-msd-{action}"):
        result = run_logged([
            jlink, "-USB", serial, "-NoGui", "1", "-ExitOnError", "1",
            "-CommandFile", str(command_file),
        ], run_dir / f"msd-{action}.log", timeout)
        markers = ("Probe configured successfully.", "Rebooted successfully.")
        if result.returncode or any(marker not in result.stdout for marker in markers):
            raise ToolError(f"J-Link MSD {action} command failed")
        return _wait_for_probe_msd_state(
            nrfutil, serial, device["devkit"]["boardVersion"], enabled,
            run_dir / f"msd-{action}-verification", timeout,
        )


def _snapshot_hexes(manifest: dict[str, Any], run_dir: Path) -> list[Path]:
    snapshots: list[Path] = []
    for item in manifest["images"]:
        source = Path(item["path"])
        snapshot = run_dir / f"{item['order']:02d}-{item['domain']}.hex"
        shutil.copyfile(source, snapshot)
        snapshot.chmod(0o400)
        if sha256(snapshot) != item["sha256"]:
            raise ToolError("image changed while creating the programming snapshot")
        parsed = parse_ihex(snapshot)
        require_allowed(parsed.ranges, tuple(tuple(entry) for entry in item["allowlist"]))
        snapshots.append(snapshot)
    return snapshots


def _program(
    manifest: dict[str, Any], device: dict[str, Any], snapshot: Path,
    args: argparse.Namespace, run_dir: Path,
) -> None:
    result = run_logged(program_argv(
        args.nrfutil, str(snapshot), device["serialNumber"],
        manifest["device_family"], manifest["core"],
    ), run_dir / f"program-{snapshot.stem}.log", args.timeout)
    if result.returncode:
        raise ToolError("safe program command failed")


def command_flash(args: argparse.Namespace) -> int:
    run_dir, report = _new_run("flash")
    try:
        manifest = load_manifest(args.manifest)
        _initialize_device_report(run_dir, report, args.manifest, manifest, args)
        device = _select(manifest, args, run_dir)
        _stage(run_dir, report, "device-selection", board_version=manifest["board_version"])
        with _probe_lock(device["serialNumber"], "flash"):
            _stage(run_dir, report, "probe-lock")
            snapshots = _snapshot_hexes(manifest, run_dir)
            _stage(
                run_dir, report, "image-snapshot",
                sha256=[sha256(snapshot) for snapshot in snapshots],
            )
            for snapshot in snapshots:
                _program(manifest, device, snapshot, args, run_dir)
                _stage(run_dir, report, "program", image_sha256=sha256(snapshot))
        report.update({
            "status": "ok",
            "image_sha256": [sha256(snapshot) for snapshot in snapshots],
        })
    except BaseException as error:
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        atomic_json(run_dir / "run.json", report)
        raise
    atomic_json(run_dir / "run.json", report)
    print(run_dir / "run.json")
    return 0


def _read_m6_settings(
    manifest: dict[str, Any], device: dict[str, Any], args: argparse.Namespace,
    output: Path, log: Path,
) -> bytes:
    result = run_logged(
        read_memory_argv(
            args.nrfutil, str(output), device["serialNumber"],
            manifest["device_family"], manifest["core"],
            M6_SETTINGS_START, M6_SETTINGS_SIZE,
        ),
        log,
        args.timeout,
    )
    if result.returncode:
        raise ToolError("M6 settings read failed")
    output.chmod(0o400)
    return read_exact_m6_settings(output)


def command_m6_bond_clear(args: argparse.Namespace) -> int:
    run_dir, report = _new_run("m6-bond-clear")
    clear_verified = False
    restore_attempted = False
    restore_verified = False
    backup: Path | None = None
    device: dict[str, Any] | None = None
    manifest: dict[str, Any] | None = None
    original: bytes | None = None
    try:
        if not args.authorize_bond_clear:
            raise ToolError("explicit --authorize-bond-clear is required")
        manifest = load_manifest(args.manifest)
        if (manifest["soc"] != "nrf54lm20a" or
                not is_m6_bond_manifest(manifest["oracle"])):
            raise ToolError("bond clear requires an LM20 M6 or locked BLE oracle manifest")
        if any(
            start < M6_SETTINGS_RANGE[1] and end > M6_SETTINGS_RANGE[0]
            for image in manifest["images"]
            for start, end in image["ranges"]
        ):
            raise ToolError("firmware image unexpectedly overlaps the M6 settings region")
        _initialize_device_report(run_dir, report, args.manifest, manifest, args)
        device = _select(manifest, args, run_dir)
        _stage(run_dir, report, "device-selection", board_version=manifest["board_version"])
        with _probe_lock(device["serialNumber"], "m6-bond-clear"):
            _stage(run_dir, report, "probe-lock")
            backup = run_dir / "settings-before.hex"
            original = _read_m6_settings(
                manifest, device, args, backup, run_dir / "settings-read-before.log"
            )
            _stage(run_dir, report, "settings-backup", sha256=sha256(backup))

            erased = run_dir / "settings-erased.hex"
            write_erased_m6_settings(erased)
            erased.chmod(0o400)
            require_exact_m6_settings_image(erased)
            result = run_logged(
                program_argv(
                    args.nrfutil, str(erased), device["serialNumber"],
                    manifest["device_family"], manifest["core"],
                ),
                run_dir / "settings-clear.log",
                args.timeout,
            )
            if result.returncode:
                raise ToolError("M6 bond clear program operation failed")
            readback = run_dir / "settings-after.hex"
            cleared = _read_m6_settings(
                manifest, device, args, readback, run_dir / "settings-read-after.log"
            )
            if cleared != b"\xFF" * M6_SETTINGS_SIZE:
                raise ToolError("M6 settings did not read back as erased")
            clear_verified = True
            _stage(
                run_dir, report, "settings-clear",
                range=[*M6_SETTINGS_RANGE], verified=True,
            )
            result = run_logged(
                reset_argv(
                    args.nrfutil, device["serialNumber"], manifest["device_family"],
                    manifest["core"], args.reset_kind,
                ),
                run_dir / "reset.log",
                args.timeout,
            )
            if result.returncode:
                raise ToolError("reset after M6 bond clear failed")
            _stage(run_dir, report, "reset")
        report.update({"status": "ok", "clear_verified": True})
    except BaseException as error:
        if (
            not clear_verified and original is not None and backup is not None
            and device is not None and manifest is not None
        ):
            restore_attempted = True
            try:
                with _probe_lock(device["serialNumber"], "m6-bond-restore"):
                    require_exact_m6_settings_image(backup)
                    restored = run_logged(
                        program_argv(
                            args.nrfutil, str(backup), device["serialNumber"],
                            manifest["device_family"], manifest["core"],
                        ),
                        run_dir / "settings-restore.log",
                        args.timeout,
                    )
                    if restored.returncode:
                        raise ToolError("M6 settings restoration program failed")
                    restored_readback = run_dir / "settings-restored.hex"
                    restored_bytes = _read_m6_settings(
                        manifest, device, args, restored_readback,
                        run_dir / "settings-read-restored.log",
                    )
                    restore_verified = restored_bytes == original
                    if not restore_verified:
                        raise ToolError("M6 settings restoration verification failed")
            except BaseException as restore_error:
                report["restore_error"] = f"{type(restore_error).__name__}: {restore_error}"
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        raise
    finally:
        report["cleanup"] = {
            "clear_verified": clear_verified,
            "restore_attempted": restore_attempted,
            "restore_verified": restore_verified,
        }
        atomic_json(run_dir / "run.json", report)
    atomic_json(run_dir / "run.json", report)
    print(run_dir / "run.json")
    return 0


def command_reset(args: argparse.Namespace) -> int:
    run_dir, report = _new_run("reset")
    try:
        manifest = load_manifest(args.manifest)
        _initialize_device_report(run_dir, report, args.manifest, manifest, args)
        device = _select(manifest, args, run_dir)
        _stage(run_dir, report, "device-selection", board_version=manifest["board_version"])
        with _probe_lock(device["serialNumber"], "reset"):
            _stage(run_dir, report, "probe-lock")
            result = run_logged(
                reset_argv(
                    args.nrfutil, device["serialNumber"],
                    manifest["device_family"], manifest["core"], args.reset_kind,
                ),
                run_dir / "reset.log", args.timeout,
            )
            if result.returncode:
                raise ToolError("device reset failed")
            _stage(
                run_dir, report, "reset", returncode=result.returncode,
                duration_seconds=result.duration_seconds,
            )
        report["status"] = "ok"
    except BaseException as error:
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        atomic_json(run_dir / "run.json", report)
        raise
    atomic_json(run_dir / "run.json", report)
    print(run_dir / "run.json")
    return 0


def command_m4_usb_gate(args: argparse.Namespace) -> int:
    run_dir, report = _new_run("m4-usb-gate")
    try:
        manifest = load_manifest(args.manifest)
        _initialize_device_report(run_dir, report, args.manifest, manifest, args)
        device = _select(manifest, args, run_dir)
        _stage(run_dir, report, "device-selection", board_version=manifest["board_version"])
        with _probe_lock(device["serialNumber"], "m4-usb-gate"):
            _stage(run_dir, report, "probe-lock")
            snapshots = _snapshot_hexes(manifest, run_dir)
            _stage(
                run_dir, report, "image-snapshot",
                sha256=[sha256(snapshot) for snapshot in snapshots],
            )
            for snapshot in snapshots:
                _program(manifest, device, snapshot, args, run_dir)
                _stage(run_dir, report, "program", image_sha256=sha256(snapshot))
            reset_result = run_logged(
                reset_argv(
                    args.nrfutil, device["serialNumber"], manifest["device_family"],
                    manifest["core"], args.reset_kind,
                ),
                run_dir / "reset.log", args.timeout,
            )
            if reset_result.returncode:
                raise ToolError("device reset failed")
            _stage(run_dir, report, "reset", duration_seconds=reset_result.duration_seconds)

        reconnect = run_reconnect_validation(cycles=args.reconnect_cycles, timeout=args.timeout)
        _stage(run_dir, report, "usb-reconnect", **reconnect)
        transfers = run_transfer_validation(
            stress_seconds=args.stress_seconds, timeout=args.timeout,
        )
        _stage(run_dir, report, "usb-control-bulk-hid", **transfers)
        if args.skip_power:
            power = {"status": "skipped", "reason": "requested by --skip-power"}
            _stage(run_dir, report, "usb-power-skipped", **power)
        else:
            host_resume = run_host_resume_validation(timeout=args.timeout)
            _stage(run_dir, report, "usb-host-resume", **host_resume)
            remote_wakeup = run_power_validation(timeout=args.timeout)
            _stage(run_dir, report, "usb-suspend-remote-wakeup", **remote_wakeup)
            power = {"host_resume": host_resume, "remote_wakeup": remote_wakeup}
        report.update({
            "status": "ok", "reconnect": reconnect, "transfers": transfers,
            "power": power,
        })
    except BaseException as error:
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        atomic_json(run_dir / "run.json", report)
        raise
    atomic_json(run_dir / "run.json", report)
    print(run_dir / "run.json")
    return 0


def command_m6_ble_gate(args: argparse.Namespace) -> int:
    run_dir, report = _new_run("m6-ble-gate")
    report["stages"] = []
    report["hci_trace"] = {
        "requested": args.hci_trace,
        "log": "hci.log" if args.hci_trace else None,
    }
    try:
        result = run_ble_validation(
            device_name=args.device_name,
            timeout=args.timeout,
            fresh_pairing=args.fresh_pairing,
            hci_trace_log=(run_dir / "hci.log") if args.hci_trace else None,
            btmon=args.btmon,
            phase=args.phase,
        )
        _stage(run_dir, report, "ble-pair-gatt-reconnect", **result)
        report.update({"status": "ok", "ble": result})
    except BaseException as error:
        if isinstance(error, BleValidationError) and error.details:
            details = dict(error.details)
            failure_stage = details.pop("failure_stage", "ble-pairing")
            report["stages"].append({
                "name": failure_stage,
                "status": "failed",
                **details,
            })
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        atomic_json(run_dir / "run.json", report)
        raise
    atomic_json(run_dir / "run.json", report)
    print(run_dir / "run.json")
    return 0


def command_m6_ble_scan(args: argparse.Namespace) -> int:
    run_dir, report = _new_run("m6-ble-scan")
    report["stages"] = []
    try:
        result = scan_ble_advertisement(
            device_name=args.device_name, timeout=args.timeout,
        )
        if not result["cleanup"]["verified"]:
            raise BleValidationError(
                "BLE scan cleanup could not be verified",
                details={
                    "failure_stage": "ble-advertisement",
                    "cleanup": result["cleanup"],
                },
            )
        _stage(run_dir, report, "ble-advertisement", **result)
        report.update({"status": "ok", "ble": result})
    except BaseException as error:
        if isinstance(error, BleValidationError) and error.details:
            details = dict(error.details)
            failure_stage = details.pop("failure_stage", "ble-advertisement")
            report["stages"].append({
                "name": failure_stage,
                "status": "failed",
                **details,
            })
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        atomic_json(run_dir / "run.json", report)
        raise
    atomic_json(run_dir / "run.json", report)
    print(run_dir / "run.json")
    return 0


def command_m6_host_info(args: argparse.Namespace) -> int:
    run_dir, report = _new_run("m6-host-info")
    report["stages"] = []
    try:
        result = run_logged(
            bluetooth_info_argv(
                btmgmt=args.btmgmt, index=args.index, timeout=args.timeout,
            ),
            run_dir / "btmgmt-info.log",
            args.timeout + 3,
        )
        if result.returncode:
            raise ToolError("bounded Bluetooth controller info query failed")
        output = (run_dir / "btmgmt-info.log").read_text(
            encoding="utf-8", errors="replace"
        )
        current = next(
            (
                line.split(":", 1)[1].strip().split()
                for line in output.splitlines()
                if line.strip().startswith("current settings:")
            ),
            [],
        )
        _stage(run_dir, report, "controller-info", current_settings=current)
        report.update({"status": "ok", "current_settings": current})
    except BaseException as error:
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        raise
    finally:
        atomic_json(run_dir / "run.json", report)
    print(run_dir / "run.json")
    return 0


def command_m4_usb_power(args: argparse.Namespace) -> int:
    run_dir, report = _new_run("m4-usb-power")
    report["stages"] = []
    try:
        report["active_stage"] = "usb-host-resume"
        atomic_json(run_dir / "run.json", report)
        host_resume = run_host_resume_validation(timeout=args.timeout)
        _stage(run_dir, report, "usb-host-resume", **host_resume)
        report["active_stage"] = "usb-suspend-remote-wakeup"
        atomic_json(run_dir / "run.json", report)
        remote_wakeup = run_power_validation(timeout=args.timeout)
        _stage(run_dir, report, "usb-suspend-remote-wakeup", **remote_wakeup)
        power = {"host_resume": host_resume, "remote_wakeup": remote_wakeup}
        report.pop("active_stage", None)
        report.update({"status": "ok", "power": power})
    except BaseException as error:
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        atomic_json(run_dir / "run.json", report)
        raise
    atomic_json(run_dir / "run.json", report)
    print(run_dir / "run.json")
    return 0


def command_m5_radio_dual(args: argparse.Namespace) -> int:
    if args.tx_probe == args.rx_probe:
        raise ToolError("M5 dual-board validation requires two distinct probes")
    tx_manifest = load_manifest(args.tx_manifest)
    rx_manifest = load_manifest(args.rx_manifest)
    if not tx_manifest["expected_token"].endswith("TX PASS"):
        raise ToolError("M5 transmitter manifest must declare a TX PASS token")
    if not rx_manifest["expected_token"].startswith("NRFKIT_M5_") or \
            "RX PASS" not in rx_manifest["expected_token"]:
        raise ToolError("M5 receiver manifest must declare an M5 RX PASS token")
    if args.rounds < 1 or args.rounds > 100:
        raise ToolError("M5 rounds must be between 1 and 100")

    run_dir, report = _new_run("m5-radio-dual")
    report.update({"status": "running", "stages": [], "child_reports": []})
    atomic_json(run_dir / "run.json", report)
    receiver: subprocess.Popen[str] | None = None
    receiver_stream = None
    ready_file: Path | None = None
    try:
        public_cli = str(project_root() / "tools/nrfkit")
        common = [
            "--nrfutil", args.nrfutil,
            "--timeout", str(args.timeout),
            "--token-timeout", str(args.token_timeout),
        ]
        for round_number in range(1, args.rounds + 1):
            receiver_log = run_dir / f"round-{round_number:03d}-receiver.log"
            ready_file = run_dir / f"round-{round_number:03d}-receiver-ready.json"
            receiver_stream = receiver_log.open("w", encoding="utf-8")
            receiver = subprocess.Popen(
                [
                    public_cli, "run", "--manifest", str(args.rx_manifest.resolve()),
                    "--probe-serial", args.rx_probe, "--ready-file", str(ready_file),
                    *common,
                ],
                text=True, stdout=receiver_stream, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            ready_deadline = time.monotonic() + args.gate_timeout
            while not ready_file.is_file():
                if receiver.poll() is not None:
                    raise ToolError(
                        f"M5 receiver exited before ready in round {round_number}; "
                        f"see {receiver_log.name}"
                    )
                if time.monotonic() >= ready_deadline:
                    raise ToolError(f"M5 receiver ready timeout in round {round_number}")
                time.sleep(0.05)
            _stage(run_dir, report, "receiver-ready", round=round_number)
            tx_report = _run_p0_child(
                [
                    public_cli, "run", "--manifest", str(args.tx_manifest.resolve()),
                    "--probe-serial", args.tx_probe, *common,
                ],
                run_dir / f"round-{round_number:03d}-transmitter.log", args.gate_timeout,
            )
            receiver.wait(timeout=args.gate_timeout)
            receiver_stream.close()
            receiver_stream = None
            if receiver.returncode:
                raise ToolError(
                    f"M5 receiver child failed in round {round_number}; see {receiver_log.name}"
                )
            lines = [line for line in receiver_log.read_text(encoding="utf-8").splitlines()
                     if line.strip()]
            if len(lines) != 1 or not Path(lines[0]).is_file():
                raise ToolError("M5 receiver child did not return one run report")
            rx_report = str(Path(lines[0]).resolve())
            report["child_reports"].extend((rx_report, tx_report))
            _stage(run_dir, report, "airborne-link", round=round_number,
                   receiver=rx_report, transmitter=tx_report)
            receiver = None
            ready_file.unlink(missing_ok=True)
        report["status"] = "ok"
    except BaseException as error:
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        raise
    finally:
        if receiver is not None and receiver.poll() is None:
            os.killpg(receiver.pid, signal.SIGTERM)
            try:
                receiver.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(receiver.pid, signal.SIGKILL)
                receiver.wait()
        if receiver_stream is not None:
            receiver_stream.close()
        if ready_file is not None:
            ready_file.unlink(missing_ok=True)
        report["cleanup"] = {"receiver_running": receiver is not None and receiver.poll() is None}
        atomic_json(run_dir / "run.json", report)
    print(run_dir / "run.json")
    return 0


def _serial_port(device: dict[str, Any], vcom: int) -> Path:
    matches = [item for item in device.get("serialPorts", []) if item.get("vcom") == vcom]
    if len(matches) != 1:
        raise ToolError(f"device does not expose exactly one VCOM {vcom}")
    return Path(matches[0]["path"])


def _serial_open(path: Path) -> int:
    descriptor = os.open(path, os.O_RDWR | os.O_NONBLOCK | os.O_NOCTTY)
    try:
        if hasattr(termios, "TIOCEXCL"):
            fcntl.ioctl(descriptor, termios.TIOCEXCL, 0)
        tty.setraw(descriptor)
        attributes = termios.tcgetattr(descriptor)
        attributes[2] |= termios.CLOCAL | termios.CREAD
        if hasattr(termios, "CRTSCTS"):
            attributes[2] &= ~termios.CRTSCTS
        attributes[4] = termios.B115200
        attributes[5] = termios.B115200
        attributes[6][termios.VMIN] = 0
        attributes[6][termios.VTIME] = 0
        termios.tcsetattr(descriptor, termios.TCSANOW, attributes)
        if hasattr(termios, "TIOCMBIS") and hasattr(termios, "TIOCMBIC"):
            control_lines = struct.pack("I", termios.TIOCM_DTR | termios.TIOCM_RTS)
            fcntl.ioctl(descriptor, termios.TIOCMBIC, control_lines)
            time.sleep(0.05)
            fcntl.ioctl(
                descriptor, termios.TIOCMBIS, control_lines,
            )
        termios.tcflush(descriptor, termios.TCIFLUSH)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _serial_reader(descriptor: int) -> tuple[threading.Event, threading.Thread, bytearray, list[OSError]]:
    stop = threading.Event()
    transcript = bytearray()
    failures: list[OSError] = []

    def drain() -> None:
        try:
            while not stop.is_set():
                readable, _, _ = select.select([descriptor], [], [], 0.05)
                if readable:
                    transcript.extend(os.read(descriptor, 65536))
        except OSError as error:
            failures.append(error)

    thread = threading.Thread(target=drain, name="nrf-vcom-reader", daemon=True)
    thread.start()
    return stop, thread, transcript, failures


def _serial_reader_stop(
    reader: tuple[threading.Event, threading.Thread, bytearray, list[OSError]],
) -> bytearray:
    stop, thread, transcript, failures = reader
    stop.set()
    thread.join(timeout=1)
    if thread.is_alive():
        raise ToolError("serial reader did not stop")
    if failures:
        raise ToolError(f"serial reader failed: {failures[0]}")
    return transcript


def _serial_cleanup(
    run_dir: Path,
    reader: tuple[threading.Event, threading.Thread, bytearray, list[OSError]] | None,
    descriptor: int | None,
) -> tuple[dict[str, Any], ToolError | None]:
    cleanup: dict[str, Any] = {
        "serial_reader_stopped": reader is None,
        "serial_closed": descriptor is None,
    }
    errors: list[str] = []
    if reader is not None:
        try:
            transcript = _serial_reader_stop(reader)
        except BaseException as error:
            transcript = reader[2]
            errors.append(f"serial reader cleanup failed: {error}")
        try:
            (run_dir / "serial.log").write_bytes(transcript)
        except BaseException as error:
            errors.append(f"serial transcript write failed: {error}")
        cleanup["serial_reader_stopped"] = not reader[1].is_alive()
    if descriptor is not None:
        try:
            os.close(descriptor)
            cleanup["serial_closed"] = True
        except BaseException as error:
            errors.append(f"serial close failed: {error}")
    if errors:
        cleanup["errors"] = errors
        return cleanup, ToolError("; ".join(errors))
    return cleanup, None


def command_run(args: argparse.Namespace) -> int:
    run_dir, report = _new_run("run")
    descriptor: int | None = None
    reader: tuple[threading.Event, threading.Thread, bytearray, list[OSError]] | None = None
    cleanup_error: ToolError | None = None
    try:
        manifest_path = getattr(args, "manifest", None)
        if getattr(args, "oracle", None):
            if getattr(args, "official_toolchain", None) is None:
                _, args.official_toolchain, _ = load_receipt(project_root(), args.oracle)
            doctor_payload, healthy = _doctor(args, require_debug_tools=False)
            report["tools"] = doctor_payload["tools"]
            report["stages"] = []
            if not healthy:
                raise ToolError("doctor preflight failed")
            _stage(run_dir, report, "doctor")
            manifest_path = build(
                project_root(), args.oracle, args.build_timeout, args.west
            )
            _stage(
                run_dir, report, "reference-build",
                oracle=args.oracle, manifest=str(manifest_path.resolve()),
            )
        assert manifest_path is not None
        manifest = load_manifest(manifest_path)
        _initialize_device_report(run_dir, report, manifest_path, manifest, args)
        report["token_timeout_seconds"] = args.token_timeout
        report["serial_ready_delay_seconds"] = args.serial_ready_delay
        atomic_json(run_dir / "run.json", report)
        device = _select(manifest, args, run_dir)
        _stage(run_dir, report, "device-selection", board_version=manifest["board_version"])
        with _probe_lock(device["serialNumber"], "run"):
            _stage(run_dir, report, "probe-lock")
            snapshots = _snapshot_hexes(manifest, run_dir)
            _stage(
                run_dir, report, "image-snapshot",
                sha256=[sha256(snapshot) for snapshot in snapshots],
            )
            for snapshot in snapshots:
                _program(manifest, device, snapshot, args, run_dir)
                _stage(run_dir, report, "program", image_sha256=sha256(snapshot))
            descriptor = _serial_open(_serial_port(device, manifest["vcom"]))
            time.sleep(args.serial_ready_delay)
            reader = _serial_reader(descriptor)
            _stage(run_dir, report, "serial-ready", vcom=manifest["vcom"])
            reset = run_logged(
                reset_argv(
                    args.nrfutil, device["serialNumber"],
                    manifest["device_family"], manifest["core"], args.reset_kind,
                ),
                run_dir / "reset.log", args.timeout,
            )
            if reset.returncode:
                raise ToolError("device reset failed")
            _stage(
                run_dir, report, "reset", returncode=reset.returncode,
                duration_seconds=reset.duration_seconds,
            )
            ready_file = getattr(args, "ready_file", None)
            if ready_file is not None:
                ready_file = ready_file.resolve()
                if not ready_file.is_relative_to((project_root() / ".work").resolve()):
                    raise ToolError("ready marker must stay inside the ignored .work directory")
                atomic_json(ready_file, {"schema": "nrfkit-ready/v1", "status": "ready"})
                _stage(run_dir, report, "ready-marker")
            deadline = time.monotonic() + args.token_timeout
            token = manifest["expected_token"].encode()
            while time.monotonic() < deadline and token not in reader[2]:
                time.sleep(0.05)
            transcript = _serial_reader_stop(reader)
            reader = None
            (run_dir / "serial.log").write_bytes(transcript)
            if token not in transcript:
                raise ToolError("expected serial token was not observed before timeout")
            _stage(run_dir, report, "wait-token", bytes_received=len(transcript))
        report.update({
            "status": "ok", "token_observed": True,
            "image_sha256": [sha256(snapshot) for snapshot in snapshots],
        })
    except BaseException as error:
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        atomic_json(run_dir / "run.json", report)
        raise
    finally:
        report["cleanup"], cleanup_error = _serial_cleanup(run_dir, reader, descriptor)
        if cleanup_error is not None and report.get("status") == "ok":
            report.update({
                "status": "failed",
                "error": f"{type(cleanup_error).__name__}: {cleanup_error}",
            })
        atomic_json(run_dir / "run.json", report)
    if cleanup_error is not None:
        raise cleanup_error
    atomic_json(run_dir / "run.json", report)
    print(run_dir / "run.json")
    return 0


def command_gdb_smoke(args: argparse.Namespace) -> int:
    run_dir, report = _new_run("gdb-smoke")
    server: subprocess.Popen[bytes] | None = None
    serial_descriptor: int | None = None
    serial_reader: tuple[threading.Event, threading.Thread, bytearray, list[OSError]] | None = None
    cleanup_error: ToolError | None = None
    try:
        manifest = load_manifest(args.manifest)
        _initialize_device_report(run_dir, report, args.manifest, manifest, args)
        device = _select(manifest, args, run_dir)
        _stage(run_dir, report, "device-selection", board_version=manifest["board_version"])
        gdb = executable(args.gdb, "arm-none-eabi-gdb")
        jlink = executable(args.jlink, "JLinkGDBServerCLExe")
        report["tools"].update({
            "gdb": _run_version([gdb, "--version"]),
            "jlink_gdb_server": _run_version([jlink, "-version"]),
        })
        atomic_json(run_dir / "run.json", report)
        with _probe_lock(device["serialNumber"], "gdb-smoke"):
            _stage(run_dir, report, "probe-lock")
            if args.verify_token:
                serial_descriptor = _serial_open(_serial_port(device, manifest["vcom"]))
                time.sleep(args.serial_ready_delay)
                serial_reader = _serial_reader(serial_descriptor)
            listener = socket.socket()
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
            listener.close()
            server_log = (run_dir / "gdb-server.log").open("wb")
            server_argv = [
                jlink, "-device", "nRF54LM20A_M33", "-if", "SWD", "-speed", "4000",
                "-port", str(port), "-swoport", "0", "-telnetport", "0", "-singlerun",
                "-nogui", "-select", f"USB={device['serialNumber']}",
            ]
            try:
                server = subprocess.Popen(
                    server_argv, stdin=subprocess.DEVNULL, stdout=server_log,
                    stderr=subprocess.STDOUT, start_new_session=True,
                )
                deadline = time.monotonic() + min(args.timeout, 20)
                while time.monotonic() < deadline:
                    if server.poll() is not None:
                        raise ToolError("J-Link GDB server exited before opening its port")
                    try:
                        connection = socket.create_connection(("127.0.0.1", port), timeout=0.2)
                    except OSError:
                        time.sleep(0.1)
                    else:
                        connection.close()
                        _stage(run_dir, report, "gdb-server-ready", port=port)
                        break
                else:
                    raise ToolError("J-Link GDB server did not open its port before timeout")
                commands = [
                    "set pagination off", "set confirm off",
                    f"file {manifest['debug_elf']['path']}", f"target remote 127.0.0.1:{port}",
                    "monitor halt", "printf \"P0_CPUID=0x%x\\n\", *(unsigned int*)0xE000ED00",
                    "info registers pc sp",
                ]
                if args.attach:
                    pass
                elif args.sdk_runtime_contract:
                    commands.extend((
                        "break Reset_Handler", "monitor reset 0", "continue",
                        "printf \"M2_RESET_HANDLER_REACHED\\n\"",
                        "break main", "continue", "printf \"P0_MAIN_REACHED\\n\"",
                        "stepi", "printf \"M2_SINGLE_STEP_COMPLETE\\n\"",
                        "set *(unsigned int*)&nrfkit_gdb_scratch = 0xa55a5aa5",
                        "printf \"M2_RAM=0x%x\\n\", *(unsigned int*)&nrfkit_gdb_scratch",
                    ))
                else:
                    commands.extend((
                        "break main", "monitor reset 0", "continue",
                        "printf \"P0_MAIN_REACHED\\n\"", "stepi",
                    ))
                if args.fault_contract:
                    commands.extend((
                        "break nrfkit_fault_observed", "continue",
                        "printf \"M2_FAULT_MAGIC=0x%x\\n\", *(unsigned int*)&nrfkit_last_fault",
                        "printf \"M2_FAULT_PC=0x%x\\n\", *((unsigned int*)&nrfkit_last_fault + 8)",
                    ))
                if args.post_main_break:
                    commands.extend((
                        "delete breakpoints", f"break {args.post_main_break}", "continue",
                        "printf \"P0_POST_MAIN_BREAK_REACHED\\n\"",
                    ))
                    if args.sdk_runtime_contract:
                        commands.extend((
                            "printf \"M2_MAIN_OBSERVED=0x%x\\n\", *(unsigned int*)&nrfkit_main_observed",
                            "printf \"M2_RESET_REASON=0x%x\\n\", *(unsigned int*)&nrfkit_reset_reason",
                        ))
                for symbol in args.observe:
                    commands.append(
                        f'printf "OBSERVE {symbol}=0x%x\\n", '
                        f'*(unsigned int*)&{symbol}'
                    )
                    commands.append(f"info address {symbol}")
                if args.attach:
                    # Attach-only diagnostics must not leave a running target halted.
                    commands.append("monitor go")
                commands.extend(("detach", "quit"))
                argv = [gdb, "--nx", "--batch"]
                for command in commands:
                    argv.extend(("-ex", command))
                result = run_logged(argv, run_dir / "gdb.log", args.timeout)
                markers = ("P0_CPUID=",) if args.attach else (
                    "P0_MAIN_REACHED", "P0_CPUID=",
                )
                if args.sdk_runtime_contract:
                    markers += (
                        "M2_RESET_HANDLER_REACHED", "M2_SINGLE_STEP_COMPLETE",
                        "M2_RAM=0xa55a5aa5", "M2_MAIN_OBSERVED=0x4d324d41",
                        "M2_RESET_REASON=0x",
                    )
                if args.fault_contract:
                    markers += ("M2_FAULT_MAGIC=0x4e524646", "M2_FAULT_PC=0x")
                if args.post_main_break:
                    markers += ("P0_POST_MAIN_BREAK_REACHED",)
                if result.returncode or any(marker not in result.stdout for marker in markers):
                    raise ToolError("GDB smoke contract failed")
                _stage(
                    run_dir, report, "gdb-contract", returncode=result.returncode,
                    duration_seconds=result.duration_seconds,
                )
                if serial_descriptor is not None:
                    deadline = time.monotonic() + args.token_timeout
                    token = manifest["expected_token"].encode()
                    assert serial_reader is not None
                    while time.monotonic() < deadline and token not in serial_reader[2]:
                        time.sleep(0.05)
                    transcript = _serial_reader_stop(serial_reader)
                    serial_reader = None
                    (run_dir / "serial.log").write_bytes(transcript)
                    if token not in transcript:
                        raise ToolError("GDB smoke reached main but its serial token was not observed")
                    _stage(run_dir, report, "wait-token", bytes_received=len(transcript))
            finally:
                server_log.close()
                if server is not None and server.poll() is None:
                    try:
                        os.killpg(server.pid, signal.SIGTERM)
                        server.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(server.pid, signal.SIGKILL)
                        server.wait()
                _stage(
                    run_dir, report, "gdb-server-cleanup",
                    server_running=server is not None and server.poll() is None,
                )
        report.update({"status": "ok", "gdb": gdb, "jlink": jlink})
    except BaseException as error:
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        atomic_json(run_dir / "run.json", report)
        raise
    finally:
        report["cleanup"], cleanup_error = _serial_cleanup(
            run_dir, serial_reader, serial_descriptor
        )
        report["cleanup"]["gdb_server_running"] = (
            server is not None and server.poll() is None
        )
        if cleanup_error is not None and report.get("status") == "ok":
            report.update({
                "status": "failed",
                "error": f"{type(cleanup_error).__name__}: {cleanup_error}",
            })
        atomic_json(run_dir / "run.json", report)
    if cleanup_error is not None:
        raise cleanup_error
    atomic_json(run_dir / "run.json", report)
    print(run_dir / "run.json")
    return 0


def _run_p0_child(argv: list[str], log: Path, timeout: float) -> str:
    result = run_logged(argv, log, timeout)
    if result.returncode:
        raise ToolError(f"child command failed; see {log}")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise ToolError("child command did not return exactly one run report")
    report = Path(lines[0])
    if not report.is_absolute() or not report.is_file():
        raise ToolError("child command returned an invalid run report")
    return str(report)


def command_probe_msd(args: argparse.Namespace) -> int:
    action = "enable" if args.enabled else "disable"
    run_dir, report = _new_run(f"probe-msd-{action}")
    report.update({
        "status": "running",
        "requested_state": "enabled" if args.enabled else "disabled",
        "stages": [],
    })
    atomic_json(run_dir / "run.json", report)
    try:
        board_version = getattr(args, "board_version", "PCA10184")
        nrfutil = executable(args.nrfutil, "nrfutil")
        devices = _enumerate(nrfutil, run_dir / "device-list.log", args.timeout)
        serial = resolve_probe_alias(
            args.probe_serial, board_version,
            project_root() / ".local" / "hardware-aliases.json",
        )
        device = select_device(devices, board_version, serial)
        original_msd = _probe_has_msd(device)
        backup = run_dir / "probe-state-before.json"
        atomic_json(backup, device)
        backup.chmod(0o400)
        report.update({
            "probe_msd_originally_enabled": original_msd,
            "probe_state_backup": str(backup.resolve()),
        })
        _stage(
            run_dir, report, "device-selection",
            board_version=board_version, msd_enabled=original_msd,
        )
        if original_msd != args.enabled:
            if not args.authorize_persistent_change:
                raise ToolError(
                    f"probe MSD is currently {'enabled' if original_msd else 'disabled'}; "
                    "explicit --authorize-persistent-change is required"
                )
            jlink = executable(args.jlink_commander, "JLinkExe")
            device = _set_probe_msd(
                jlink, nrfutil, device, args.enabled,
                run_dir / "probe-msd", args.timeout,
            )
            _stage(
                run_dir, report, f"probe-msd-{action}",
                command=f"MSD{action.capitalize()}", rebooted=True, verified=True,
            )
            report["persistent_change_applied"] = True
        else:
            if not _probe_interface_contract(device, args.enabled):
                raise ToolError(
                    "probe has the requested MSD state but not the required "
                    "J-Link and dual-VCOM interface contract"
                )
            _stage(
                run_dir, report, "probe-msd-already-requested-state", verified=True,
            )
            report["persistent_change_applied"] = False
        after = run_dir / "probe-state-after.json"
        atomic_json(after, device)
        after.chmod(0o400)
        report.update({
            "probe_msd_finally_enabled": _probe_has_msd(device),
            "probe_state_after": str(after.resolve()),
            "status": "ok",
        })
    except BaseException as error:
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        atomic_json(run_dir / "run.json", report)
        raise
    atomic_json(run_dir / "run.json", report)
    print(run_dir / "run.json")
    return 0


def command_p0_gate(args: argparse.Namespace) -> int:
    run_dir, report = _new_run("p0-gate")
    operation_error: BaseException | None = None
    restoration_error: BaseException | None = None
    restore_msd = False
    device: dict[str, Any] | None = None
    report.update({
        "status": "running",
        "hello_world_required_passes": 3,
        "child_reports": [],
        "stages": [],
    })
    atomic_json(run_dir / "run.json", report)
    try:
        nrfutil = executable(args.nrfutil, "nrfutil")
        jlink_commander = executable(args.jlink_commander, "JLinkExe")
        gdb = executable(args.gdb, "arm-none-eabi-gdb")
        jlink_server = executable(args.jlink, "JLinkGDBServerCLExe")
        contract = oracle(project_root(), "ncs-hello-world")
        devices = _enumerate(nrfutil, run_dir / "device-list.log", args.timeout)
        serial = resolve_probe_alias(
            args.probe_serial, contract["board_version"],
            project_root() / ".local" / "hardware-aliases.json",
        )
        device = select_device(devices, contract["board_version"], serial)
        original_msd = _probe_has_msd(device)
        if not _probe_interface_contract(device, original_msd):
            raise ToolError("selected probe does not expose J-Link and exactly VCOM0/VCOM1")
        report["probe_msd_originally_enabled"] = original_msd
        _stage(
            run_dir, report, "device-selection",
            board_version=contract["board_version"], msd_enabled=original_msd,
        )
        if original_msd:
            if not args.authorize_temporary_msd_disable:
                raise ToolError(
                    "probe MSD is enabled; use 'probe-msd disable' after separate "
                    "authorization for the preferred persistent fix, or pass explicit "
                    "--authorize-temporary-msd-disable for the backed-up, automatically "
                    "restored compatibility path; explicit authorization is required"
                )
            restore_msd = True
            device = _set_probe_msd(
                jlink_commander, nrfutil, device, False,
                run_dir / "probe-msd", args.timeout,
            )
            _stage(run_dir, report, "probe-msd-disable", verified=True)

        public_cli = str(project_root() / "tools/nrfkit")
        common_run = [
            public_cli, "run", "--probe-serial", device["serialNumber"],
            "--nrfutil", nrfutil, "--timeout", str(args.timeout),
            "--build-timeout", str(args.build_timeout),
            "--token-timeout", str(args.token_timeout),
            "--serial-ready-delay", str(args.serial_ready_delay),
            "--cmake", args.cmake, "--ninja", args.ninja, "--west", args.west,
            "--jlink", jlink_server, "--gdb", gdb,
        ]
        child_number = 0
        for iteration in range(1, 4):
            child_number += 1
            child_report = _run_p0_child(
                common_run + ["--oracle", "ncs-hello-world"],
                run_dir / f"child-{child_number:02d}-hello-{iteration}.log",
                args.gate_timeout,
            )
            report["child_reports"].append(child_report)
            _stage(
                run_dir, report, "hello-world",
                iteration=iteration, child_report=child_report,
            )
        child_number += 1
        bm_report = _run_p0_child(
            common_run + ["--oracle", "nrf-bm-leds-s115"],
            run_dir / f"child-{child_number:02d}-bare-metal.log",
            args.gate_timeout,
        )
        report["child_reports"].append(bm_report)
        _stage(run_dir, report, "bare-metal-s115", child_report=bm_report)

        child_number += 1
        manifest = (
            project_root()
            / ".work/reference/build/nrf-bm-leds-s115/image-manifest.json"
        )
        gdb_report = _run_p0_child([
            public_cli, "gdb-smoke", "--manifest", str(manifest),
            "--probe-serial", device["serialNumber"], "--nrfutil", nrfutil,
            "--timeout", str(args.timeout), "--gdb", gdb, "--jlink", jlink_server,
            "--verify-token", "--token-timeout", str(args.token_timeout),
            "--serial-ready-delay", str(args.serial_ready_delay),
        ], run_dir / f"child-{child_number:02d}-gdb-smoke.log", args.gate_timeout)
        report["child_reports"].append(gdb_report)
        _stage(run_dir, report, "gdb-smoke", child_report=gdb_report)
        device = _wait_for_probe_msd_state(
            nrfutil, device["serialNumber"], contract["board_version"], False,
            run_dir / "final-interface-verification", args.timeout,
        )
        _stage(
            run_dir, report, "probe-interface-verification",
            msd_enabled=False, jlink=True, vcoms=[0, 1],
        )
        report["status"] = "ok"
    except BaseException as error:
        operation_error = error
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
    finally:
        if restore_msd:
            assert device is not None
            try:
                _set_probe_msd(
                    jlink_commander, nrfutil, device, True,
                    run_dir / "probe-msd", args.timeout,
                )
                _stage(run_dir, report, "probe-msd-restore", verified=True)
            except BaseException as error:
                restoration_error = error
                report["status"] = "failed"
                report["restoration_error"] = f"{type(error).__name__}: {error}"
        report["cleanup"] = {
            "probe_msd_restored": not restore_msd or restoration_error is None,
            "probe_msd_unchanged": not restore_msd,
        }
        atomic_json(run_dir / "run.json", report)
    if restoration_error is not None:
        if operation_error is not None:
            raise ToolError(
                f"P0 gate failed ({operation_error}); MSD restoration also failed: "
                f"{restoration_error}"
            ) from restoration_error
        raise restoration_error
    if operation_error is not None:
        raise operation_error
    print(run_dir / "run.json")
    return 0


def command_m2_gate(args: argparse.Namespace) -> int:
    run_dir, report = _new_run("m2-gate")
    operation_error: BaseException | None = None
    restoration_error: BaseException | None = None
    normal_audited = False
    hardware_started = False
    nrfutil: str | None = None
    report.update({
        "status": "running",
        "required_program_reset_cycles": 20,
        "child_reports": [],
        "stages": [],
    })
    atomic_json(run_dir / "run.json", report)
    public_cli = str(project_root() / "tools/nrfkit")
    try:
        normal = load_manifest(args.normal_manifest)
        fault = load_manifest(args.fault_manifest)
        if normal["oracle"] != "sdk-hardware_validation":
            raise ToolError("M2 normal manifest must target hardware_validation")
        if fault["oracle"] != "sdk-fault":
            raise ToolError("M2 fault manifest must target fault")
        if normal["source_receipt_sha256"] != fault["source_receipt_sha256"]:
            raise ToolError("M2 manifests were not generated from the same source lock")
        source_lock_hash = sha256(project_root() / "docs/provenance/sources.lock")
        if normal["source_receipt_sha256"] != source_lock_hash:
            raise ToolError("M2 manifests are stale relative to the current source lock")
        if not normal["expected_token"].startswith("NRFKIT_BOOT "):
            raise ToolError("M2 normal manifest does not contain a build-ID boot token")
        normal_audited = True
        nrfutil = executable(args.nrfutil, "nrfutil")
        gdb = executable(args.gdb, "arm-none-eabi-gdb")
        jlink = executable(args.jlink, "JLinkGDBServerCLExe")
        common = [
            "--nrfutil", nrfutil, "--timeout", str(args.timeout),
        ]
        if args.probe_serial:
            common.extend(("--probe-serial", args.probe_serial))
        run_options = [
            "--token-timeout", str(args.token_timeout),
            "--serial-ready-delay", str(args.serial_ready_delay),
        ]
        _stage(run_dir, report, "manifest-audit")
        for iteration in range(1, 21):
            hardware_started = True
            child_report = _run_p0_child(
                [public_cli, "run", "--manifest", str(args.normal_manifest),
                 *common, *run_options],
                run_dir / f"child-{iteration:02d}-run.log", args.gate_timeout,
            )
            report["child_reports"].append(child_report)
            _stage(
                run_dir, report, "program-reset-token",
                iteration=iteration, child_report=child_report,
            )

        child_number = 21
        normal_gdb = _run_p0_child([
            public_cli, "gdb-smoke", "--manifest", str(args.normal_manifest),
            *common, "--gdb", gdb, "--jlink", jlink,
            "--sdk-runtime-contract", "--verify-token", *run_options,
            "--post-main-break", "nrfkit_post_main",
        ], run_dir / f"child-{child_number:02d}-gdb-runtime.log", args.gate_timeout)
        report["child_reports"].append(normal_gdb)
        _stage(run_dir, report, "gdb-runtime-contract", child_report=normal_gdb)

        child_number += 1
        fault_flash = _run_p0_child([
            public_cli, "flash", "--manifest", str(args.fault_manifest), *common,
        ], run_dir / f"child-{child_number:02d}-fault-flash.log", args.gate_timeout)
        report["child_reports"].append(fault_flash)
        _stage(run_dir, report, "fault-image-program", child_report=fault_flash)

        child_number += 1
        fault_gdb = _run_p0_child([
            public_cli, "gdb-smoke", "--manifest", str(args.fault_manifest),
            *common, "--gdb", gdb, "--jlink", jlink, "--fault-contract",
        ], run_dir / f"child-{child_number:02d}-gdb-fault.log", args.gate_timeout)
        report["child_reports"].append(fault_gdb)
        _stage(run_dir, report, "gdb-fault-contract", child_report=fault_gdb)
    except BaseException as error:
        operation_error = error
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
    finally:
        if normal_audited and hardware_started:
            try:
                child_number = len(report["child_reports"]) + 1
                restore = _run_p0_child([
                    public_cli, "run", "--manifest", str(args.normal_manifest),
                    "--nrfutil", nrfutil or args.nrfutil,
                    "--timeout", str(args.timeout),
                    "--token-timeout", str(args.token_timeout),
                    "--serial-ready-delay", str(args.serial_ready_delay),
                    *(["--probe-serial", args.probe_serial] if args.probe_serial else []),
                ], run_dir / f"child-{child_number:02d}-restore-normal.log", args.gate_timeout)
                report["child_reports"].append(restore)
                _stage(run_dir, report, "normal-image-restored", child_report=restore)
            except BaseException as error:
                restoration_error = error
                report["status"] = "failed"
                report["restoration_error"] = f"{type(error).__name__}: {error}"
        if operation_error is None and restoration_error is None:
            report["status"] = "ok"
        report["cleanup"] = {
            "normal_image_restored": hardware_started and restoration_error is None,
            "restoration_required": hardware_started,
        }
        atomic_json(run_dir / "run.json", report)
    if restoration_error is not None:
        if operation_error is not None:
            raise ToolError(
                f"M2 gate failed ({operation_error}); normal-image restoration also failed: "
                f"{restoration_error}"
            ) from restoration_error
        raise restoration_error
    if operation_error is not None:
        raise operation_error
    print(run_dir / "run.json")
    return 0


def add_device_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--probe-serial", default=os.environ.get("NRF_PROBE_SERIAL"))
    parser.add_argument("--nrfutil", default=shutil.which("nrfutil") or "nrfutil")
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument(
        "--reset-kind", choices=("RESET_DEFAULT", "RESET_PIN"),
        default="RESET_DEFAULT",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build, audit, and safely run nRF reference images")
    subparsers = parser.add_subparsers(dest="command", required=True)
    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--cmake", default=shutil.which("cmake") or "cmake")
    doctor.add_argument("--ninja", default=shutil.which("ninja") or "ninja")
    doctor.add_argument("--west", default=shutil.which("west") or "west")
    doctor.add_argument("--nrfutil", default=shutil.which("nrfutil") or "nrfutil")
    doctor.add_argument("--jlink", default=shutil.which("JLinkGDBServerCLExe") or "JLinkGDBServerCLExe")
    doctor.add_argument("--gdb", default=_default_gdb())
    doctor.add_argument("--official-toolchain", type=Path, required=True)
    doctor.set_defaults(handler=command_doctor)

    device_list = subparsers.add_parser(
        "device-list", help="enumerate probes and optionally resolve one local board alias"
    )
    device_list.add_argument(
        "--board-version", choices=("PCA10184", "PCA10156")
    )
    device_list.add_argument("--probe-serial", default=os.environ.get("NRF_PROBE_SERIAL"))
    device_list.add_argument("--nrfutil", default=shutil.which("nrfutil") or "nrfutil")
    device_list.add_argument("--timeout", type=float, default=10.0)
    device_list.set_defaults(handler=command_device_list)

    reference = subparsers.add_parser("reference")
    reference_commands = reference.add_subparsers(dest="reference_command", required=True)
    reference_prepare = reference_commands.add_parser("prepare")
    reference_prepare.add_argument(
        "oracle",
        choices=(
            "ncs-hello-world", "nrf-bm-leds-s115",
            "ncs-m5-radio-peer", "nrf-bm-ble-hids-mouse-s115",
            "nrf-bm-m6-s145-central",
        ),
    )
    reference_prepare.add_argument("--root", type=Path, required=True)
    reference_prepare.add_argument("--toolchain", type=Path, required=True)
    reference_prepare.set_defaults(handler=command_prepare)
    reference_build = reference_commands.add_parser("build")
    reference_build.add_argument(
        "oracle",
        choices=(
            "ncs-hello-world", "nrf-bm-leds-s115",
            "ncs-m5-radio-peer", "nrf-bm-ble-hids-mouse-s115",
            "nrf-bm-m6-s145-central",
        ),
    )
    reference_build.add_argument(
        "--profile",
        choices=(
            "p2", "p3", "bonding", "hid", "product", "reconnect",
            "bluez-kdist", "tx", "rx", "tx-1m", "rx-1m",
        ),
    )
    reference_build.add_argument("--timeout", type=float, default=900)
    reference_build.add_argument("--west", default=shutil.which("west") or "west")
    reference_build.set_defaults(handler=command_build)
    reference_audit = reference_commands.add_parser("equivalence-audit")
    reference_audit.add_argument("--root", type=Path, required=True)
    reference_audit.add_argument("--build-dir", type=Path, required=True)
    reference_audit.add_argument("--update", action="store_true")
    reference_audit.set_defaults(handler=command_equivalence_audit)

    sdk = subparsers.add_parser("sdk")
    sdk_commands = sdk.add_subparsers(dest="sdk_command", required=True)
    sdk_manifest = sdk_commands.add_parser("manifest")
    sdk_manifest.add_argument("--build-dir", type=Path, required=True)
    sdk_manifest.add_argument("--target", required=True)
    sdk_manifest.add_argument("--expected-token", required=True)
    sdk_manifest.set_defaults(handler=command_sdk_manifest)

    inspect = subparsers.add_parser("inspect")
    inspect.add_argument("--manifest", type=Path, required=True)
    inspect.set_defaults(handler=command_inspect)
    for name, handler in (("flash", command_flash), ("reset", command_reset)):
        command = subparsers.add_parser(name)
        add_device_arguments(command)
        command.set_defaults(handler=handler)
    run = subparsers.add_parser("run")
    run_input = run.add_mutually_exclusive_group(required=True)
    run_input.add_argument("--manifest", type=Path)
    run_input.add_argument(
        "--oracle",
        choices=(
            "ncs-hello-world", "nrf-bm-leds-s115",
            "nrf-bm-ble-hids-mouse-s115",
        ),
    )
    run.add_argument("--probe-serial", default=os.environ.get("NRF_PROBE_SERIAL"))
    run.add_argument("--nrfutil", default=shutil.which("nrfutil") or "nrfutil")
    run.add_argument("--timeout", type=float, default=90)
    run.add_argument("--build-timeout", type=float, default=900)
    run.add_argument("--token-timeout", type=float, default=10)
    run.add_argument("--serial-ready-delay", type=float, default=0.5)
    run.add_argument("--ready-file", type=Path, help=argparse.SUPPRESS)
    run.add_argument(
        "--reset-kind", choices=("RESET_DEFAULT", "RESET_PIN"),
        default="RESET_DEFAULT",
    )
    run.add_argument("--cmake", default=shutil.which("cmake") or "cmake")
    run.add_argument("--ninja", default=shutil.which("ninja") or "ninja")
    run.add_argument("--west", default=shutil.which("west") or "west")
    run.add_argument(
        "--jlink", default=shutil.which("JLinkGDBServerCLExe") or "JLinkGDBServerCLExe"
    )
    run.add_argument("--gdb", default=_default_gdb())
    run.add_argument("--official-toolchain", type=Path)
    run.set_defaults(handler=command_run)
    gdb = subparsers.add_parser("gdb-smoke")
    add_device_arguments(gdb)
    gdb.add_argument("--gdb", default=_default_gdb())
    gdb.add_argument("--jlink", default=shutil.which("JLinkGDBServerCLExe") or "JLinkGDBServerCLExe")
    gdb.add_argument("--verify-token", action="store_true")
    gdb.add_argument("--post-main-break")
    gdb.add_argument("--observe", action="append", default=[])
    contract = gdb.add_mutually_exclusive_group()
    contract.add_argument(
        "--attach", action="store_true",
        help="observe the running target without resetting or stopping in main",
    )
    contract.add_argument("--sdk-runtime-contract", action="store_true")
    contract.add_argument("--fault-contract", action="store_true")
    gdb.add_argument("--token-timeout", type=float, default=10)
    gdb.add_argument("--serial-ready-delay", type=float, default=0.5)
    gdb.set_defaults(handler=command_gdb_smoke)
    m4_usb = subparsers.add_parser("m4-usb-gate")
    add_device_arguments(m4_usb)
    m4_usb.add_argument("--reconnect-cycles", type=int, default=100)
    m4_usb.add_argument("--stress-seconds", type=float, default=60.0)
    m4_usb.add_argument(
        "--skip-power", action="store_true",
        help="skip the root-only Linux runtime-PM check during development",
    )
    m4_usb.set_defaults(handler=command_m4_usb_gate)
    m4_power = subparsers.add_parser("m4-usb-power")
    m4_power.add_argument("--timeout", type=float, default=30.0)
    m4_power.set_defaults(handler=command_m4_usb_power)
    m5_dual = subparsers.add_parser("m5-radio-dual")
    m5_dual.add_argument("--tx-manifest", type=Path, required=True)
    m5_dual.add_argument("--rx-manifest", type=Path, required=True)
    m5_dual.add_argument("--tx-probe", required=True)
    m5_dual.add_argument("--rx-probe", required=True)
    m5_dual.add_argument("--nrfutil", default=shutil.which("nrfutil") or "nrfutil")
    m5_dual.add_argument("--timeout", type=float, default=90)
    m5_dual.add_argument("--token-timeout", type=float, default=30)
    m5_dual.add_argument("--gate-timeout", type=float, default=120)
    m5_dual.add_argument("--rounds", type=int, default=3)
    m5_dual.set_defaults(handler=command_m5_radio_dual)
    m6_ble = subparsers.add_parser("m6-ble-gate")
    m6_ble.add_argument("--device-name", default="nrfkit-m6")
    m6_ble.add_argument("--timeout", type=float, default=60.0)
    m6_ble.add_argument(
        "--fresh-pairing", action="store_true",
        help="remove only the matching test device from the host before pairing",
    )
    m6_ble.add_argument("--hci-trace", action="store_true")
    m6_ble.add_argument("--btmon", default=shutil.which("btmon") or "btmon")
    m6_ble.add_argument(
        "--phase",
        choices=(
            "plaintext", "bonding", "hid", "persistence", "oracle",
        ),
        default="oracle",
    )
    m6_ble.set_defaults(handler=command_m6_ble_gate)
    m6_scan = subparsers.add_parser("m6-ble-scan")
    m6_scan.add_argument("--device-name", default="nrfkit-m6-adv")
    m6_scan.add_argument("--timeout", type=float, default=30.0)
    m6_scan.set_defaults(handler=command_m6_ble_scan)
    m6_host = subparsers.add_parser("m6-host-info")
    m6_host.add_argument("--index", type=int, default=0)
    m6_host.add_argument("--timeout", type=float, default=5.0)
    m6_host.add_argument("--btmgmt", default=shutil.which("btmgmt") or "btmgmt")
    m6_host.set_defaults(handler=command_m6_host_info)
    m6_bond_clear = subparsers.add_parser("m6-bond-clear")
    add_device_arguments(m6_bond_clear)
    m6_bond_clear.add_argument("--authorize-bond-clear", action="store_true")
    m6_bond_clear.set_defaults(handler=command_m6_bond_clear)
    probe_msd = subparsers.add_parser(
        "probe-msd",
        help="apply one fixed, explicitly authorized persistent J-Link MSD setting",
    )
    probe_msd_commands = probe_msd.add_subparsers(
        dest="probe_msd_command", required=True
    )
    for name, enabled in (("disable", False), ("enable", True)):
        command = probe_msd_commands.add_parser(name)
        command.add_argument("--probe-serial", default=os.environ.get("NRF_PROBE_SERIAL"))
        command.add_argument(
            "--board-version", choices=("PCA10184", "PCA10156"),
            default="PCA10184",
        )
        command.add_argument("--nrfutil", default=shutil.which("nrfutil") or "nrfutil")
        command.add_argument(
            "--jlink-commander", default=shutil.which("JLinkExe") or "JLinkExe"
        )
        command.add_argument("--timeout", type=float, default=90)
        command.add_argument("--authorize-persistent-change", action="store_true")
        command.set_defaults(handler=command_probe_msd, enabled=enabled)
    p0_gate = subparsers.add_parser("p0-gate")
    p0_gate.add_argument("--probe-serial", default=os.environ.get("NRF_PROBE_SERIAL"))
    p0_gate.add_argument("--nrfutil", default=shutil.which("nrfutil") or "nrfutil")
    p0_gate.add_argument("--jlink-commander", default=shutil.which("JLinkExe") or "JLinkExe")
    p0_gate.add_argument(
        "--jlink", default=shutil.which("JLinkGDBServerCLExe") or "JLinkGDBServerCLExe"
    )
    p0_gate.add_argument("--gdb", required=True)
    p0_gate.add_argument("--cmake", default=shutil.which("cmake") or "cmake")
    p0_gate.add_argument("--ninja", default=shutil.which("ninja") or "ninja")
    p0_gate.add_argument("--west", default=shutil.which("west") or "west")
    p0_gate.add_argument("--timeout", type=float, default=90)
    p0_gate.add_argument("--build-timeout", type=float, default=900)
    p0_gate.add_argument("--gate-timeout", type=float, default=1200)
    p0_gate.add_argument("--token-timeout", type=float, default=10)
    p0_gate.add_argument("--serial-ready-delay", type=float, default=0.5)
    p0_gate.add_argument("--authorize-temporary-msd-disable", action="store_true")
    p0_gate.set_defaults(handler=command_p0_gate)
    m2_gate = subparsers.add_parser("m2-gate")
    m2_gate.add_argument("--normal-manifest", type=Path, required=True)
    m2_gate.add_argument("--fault-manifest", type=Path, required=True)
    m2_gate.add_argument("--probe-serial", default=os.environ.get("NRF_PROBE_SERIAL"))
    m2_gate.add_argument("--nrfutil", default=shutil.which("nrfutil") or "nrfutil")
    m2_gate.add_argument(
        "--jlink", default=shutil.which("JLinkGDBServerCLExe") or "JLinkGDBServerCLExe"
    )
    m2_gate.add_argument("--gdb", required=True)
    m2_gate.add_argument("--timeout", type=float, default=90)
    m2_gate.add_argument("--gate-timeout", type=float, default=180)
    m2_gate.add_argument("--token-timeout", type=float, default=10)
    m2_gate.add_argument("--serial-ready-delay", type=float, default=0.5)
    m2_gate.set_defaults(handler=command_m2_gate)
    args = parser.parse_args(argv)
    if getattr(args, "timeout", 1) <= 0:
        parser.error("--timeout must be positive")
    for name in ("build_timeout", "gate_timeout", "token_timeout"):
        if getattr(args, name, 1) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    if getattr(args, "serial_ready_delay", 0) < 0:
        parser.error("--serial-ready-delay must not be negative")
    if getattr(args, "reconnect_cycles", 1) <= 0:
        parser.error("--reconnect-cycles must be positive")
    if getattr(args, "stress_seconds", 1) <= 0:
        parser.error("--stress-seconds must be positive")
    if getattr(args, "sdk_runtime_contract", False) and not args.post_main_break:
        parser.error("--sdk-runtime-contract requires --post-main-break")
    for symbol in getattr(args, "observe", []):
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", symbol) is None:
            parser.error("--observe must name a C identifier")
    try:
        return args.handler(args)
    except (
        DeviceContractError, ImageContractError, ReferenceContractError,
        SdkContractError, ToolError, UsbValidationError, BleValidationError, OSError,
    ) as error:
        parser.exit(1, f"error: {error}\n")
