# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import termios
import time
import tty
from typing import Any, Iterator

from .device import (
    DeviceContractError, nrfutil_prefix, parse_json_lines, program_argv,
    reset_argv, select_device,
)
from .image import ImageContractError, parse_elf, parse_ihex, require_allowed
from .process import atomic_json, run_logged
from .reference import ReferenceContractError, build, oracle, prepare, sha256


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
        "debug_elf", "images",
    }
    if value.get("schema") != "nrf-cmake-sdk-image/v1" or set(value) != required:
        raise ToolError("image manifest schema or fields are invalid")
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
            if [list(item) for item in parsed.ranges] != artifact["ranges"]:
                raise ToolError(f"manifest {name} ranges are stale")
    return value


def _new_run(operation: str) -> tuple[Path, dict[str, Any]]:
    root = project_root()
    run_dir = root / ".work/runs" / f"{time.strftime('%Y%m%d-%H%M%S')}-{operation}-{os.getpid()}"
    run_dir.mkdir(parents=True, exist_ok=False)
    report: dict[str, Any] = {
        "schema": "nrf-cmake-sdk-run/v1", "operation": operation,
        "status": "running", "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    atomic_json(run_dir / "run.json", report)
    return run_dir, report


def _run_version(argv: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10
        )
        return {"argv": argv, "returncode": completed.returncode, "output": completed.stdout.strip()}
    except (OSError, subprocess.SubprocessError) as error:
        return {"argv": argv, "returncode": None, "error": str(error)}


def command_doctor(args: argparse.Namespace) -> int:
    tools = {
        "cmake": _run_version([args.cmake, "--version"]),
        "ninja": _run_version([args.ninja, "--version"]),
        "west": _run_version([args.west, "--version"]),
        "nrfutil": _run_version([args.nrfutil, "--log-output", "stdout", "--version"]),
        "jlink_gdb_server": _run_version([args.jlink, "-version"]),
    }
    gdb = args.gdb or shutil.which("arm-none-eabi-gdb") or shutil.which("gdb-multiarch")
    tools["gdb"] = _run_version([gdb, "--version"]) if gdb else {
        "returncode": None, "error": "arm-none-eabi-gdb and gdb-multiarch are both missing"
    }
    if gdb and tools["gdb"]["returncode"] == 0:
        lock_path = project_root() / "docs/provenance/toolchains.lock"
        try:
            toolchain_lock = json.loads(lock_path.read_text(encoding="utf-8"))
            locked_hashes = {
                item["executable_sha256"] for item in toolchain_lock["tools"].values()
            }
            gdb_hash = sha256(Path(gdb))
            tools["gdb"].update({"sha256": gdb_hash, "locked": gdb_hash in locked_hashes})
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
            tools["gdb"].update({"locked": False, "lock_error": str(error)})
    print(json.dumps({"schema": "nrf-cmake-sdk-doctor/v1", "tools": tools}, indent=2, sort_keys=True))
    required = ("cmake", "ninja", "west", "nrfutil", "jlink_gdb_server", "gdb")
    healthy = all(tools[name].get("returncode") == 0 for name in required)
    return 0 if healthy and tools["gdb"].get("locked") is True else 1


def command_prepare(args: argparse.Namespace) -> int:
    output = prepare(project_root(), args.oracle, args.root, args.toolchain)
    print(output)
    return 0


def command_build(args: argparse.Namespace) -> int:
    output = build(project_root(), args.oracle, args.timeout)
    print(output)
    return 0


def command_inspect(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    print(json.dumps({
        "status": "ok", "oracle": manifest["oracle"],
        "elf_ranges": manifest["debug_elf"]["ranges"],
        "images": [{"domain": item["domain"], "ranges": item["ranges"]} for item in manifest["images"]],
    }, indent=2, sort_keys=True))
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
    path = Path(tempfile.gettempdir()) / f"nrf-cmake-sdk-{os.getuid()}-{digest}.lock"
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
    return select_device(devices, manifest["board_version"], args.probe_serial)


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
    manifest = load_manifest(args.manifest)
    run_dir, report = _new_run("flash")
    try:
        device = _select(manifest, args, run_dir)
        with _probe_lock(device["serialNumber"], "flash"):
            snapshots = _snapshot_hexes(manifest, run_dir)
            for snapshot in snapshots:
                _program(manifest, device, snapshot, args, run_dir)
        report.update({
            "status": "ok", "manifest": str(args.manifest.resolve()),
            "image_sha256": [sha256(snapshot) for snapshot in snapshots],
        })
    except BaseException as error:
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        atomic_json(run_dir / "run.json", report)
        raise
    atomic_json(run_dir / "run.json", report)
    print(run_dir / "run.json")
    return 0


def command_reset(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    run_dir, report = _new_run("reset")
    try:
        device = _select(manifest, args, run_dir)
        with _probe_lock(device["serialNumber"], "reset"):
            result = run_logged(
                reset_argv(
                    args.nrfutil, device["serialNumber"],
                    manifest["device_family"], manifest["core"],
                ),
                run_dir / "reset.log", args.timeout,
            )
            if result.returncode:
                raise ToolError("device reset failed")
        report["status"] = "ok"
    except BaseException as error:
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        atomic_json(run_dir / "run.json", report)
        raise
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


def command_run(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    run_dir, report = _new_run("run")
    descriptor: int | None = None
    try:
        device = _select(manifest, args, run_dir)
        with _probe_lock(device["serialNumber"], "run"):
            snapshots = _snapshot_hexes(manifest, run_dir)
            for snapshot in snapshots:
                _program(manifest, device, snapshot, args, run_dir)
            descriptor = _serial_open(_serial_port(device, manifest["vcom"]))
            time.sleep(args.serial_ready_delay)
            reset = run_logged(
                reset_argv(
                    args.nrfutil, device["serialNumber"],
                    manifest["device_family"], manifest["core"],
                ),
                run_dir / "reset.log", args.timeout,
            )
            if reset.returncode:
                raise ToolError("device reset failed")
            deadline = time.monotonic() + args.token_timeout
            transcript = bytearray()
            token = manifest["expected_token"].encode()
            while time.monotonic() < deadline and token not in transcript:
                readable, _, _ = select.select([descriptor], [], [], min(0.25, deadline - time.monotonic()))
                if readable:
                    transcript.extend(os.read(descriptor, 65536))
            (run_dir / "serial.log").write_bytes(transcript)
            if token not in transcript:
                raise ToolError("expected serial token was not observed before timeout")
        report.update({
            "status": "ok", "token_observed": True,
            "image_sha256": [sha256(snapshot) for snapshot in snapshots],
        })
    except BaseException as error:
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        atomic_json(run_dir / "run.json", report)
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)
    atomic_json(run_dir / "run.json", report)
    print(run_dir / "run.json")
    return 0


def command_gdb_smoke(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    run_dir, report = _new_run("gdb-smoke")
    server: subprocess.Popen[bytes] | None = None
    serial_descriptor: int | None = None
    try:
        device = _select(manifest, args, run_dir)
        gdb = executable(args.gdb, "arm-none-eabi-gdb")
        jlink = executable(args.jlink, "JLinkGDBServerCLExe")
        with _probe_lock(device["serialNumber"], "gdb-smoke"):
            if args.verify_token:
                serial_descriptor = _serial_open(_serial_port(device, manifest["vcom"]))
                time.sleep(args.serial_ready_delay)
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
                        break
                else:
                    raise ToolError("J-Link GDB server did not open its port before timeout")
                commands = [
                    "set pagination off", "set confirm off",
                    f"file {manifest['debug_elf']['path']}", f"target remote 127.0.0.1:{port}",
                    "monitor halt", "printf \"P0_CPUID=0x%x\\n\", *(unsigned int*)0xE000ED00",
                    "info registers pc sp", "break main", "monitor reset 0", "continue",
                    "printf \"P0_MAIN_REACHED\\n\"",
                    "stepi",
                ]
                if args.post_main_break:
                    commands.extend((
                        f"break {args.post_main_break}", "continue",
                        "printf \"P0_POST_MAIN_BREAK_REACHED\\n\"",
                    ))
                commands.extend(("detach", "quit"))
                argv = [gdb, "--nx", "--batch"]
                for command in commands:
                    argv.extend(("-ex", command))
                result = run_logged(argv, run_dir / "gdb.log", args.timeout)
                markers = ("P0_MAIN_REACHED", "P0_CPUID=")
                if args.post_main_break:
                    markers += ("P0_POST_MAIN_BREAK_REACHED",)
                if result.returncode or any(marker not in result.stdout for marker in markers):
                    raise ToolError("GDB smoke contract failed")
                if serial_descriptor is not None:
                    deadline = time.monotonic() + args.token_timeout
                    transcript = bytearray()
                    token = manifest["expected_token"].encode()
                    while time.monotonic() < deadline and token not in transcript:
                        readable, _, _ = select.select(
                            [serial_descriptor], [], [],
                            min(0.25, deadline - time.monotonic()),
                        )
                        if readable:
                            transcript.extend(os.read(serial_descriptor, 65536))
                    (run_dir / "serial.log").write_bytes(transcript)
                    if token not in transcript:
                        raise ToolError("GDB smoke reached main but its serial token was not observed")
            finally:
                server_log.close()
                if server is not None and server.poll() is None:
                    try:
                        os.killpg(server.pid, signal.SIGTERM)
                        server.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(server.pid, signal.SIGKILL)
                        server.wait()
        report.update({"status": "ok", "gdb": gdb, "jlink": jlink})
    except BaseException as error:
        report.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
        atomic_json(run_dir / "run.json", report)
        raise
    finally:
        if serial_descriptor is not None:
            os.close(serial_descriptor)
    atomic_json(run_dir / "run.json", report)
    print(run_dir / "run.json")
    return 0


def add_device_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--probe-serial", default=os.environ.get("NRF_PROBE_SERIAL"))
    parser.add_argument("--nrfutil", default=shutil.which("nrfutil") or "nrfutil")
    parser.add_argument("--timeout", type=float, default=90)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build, audit, and safely run nRF reference images")
    subparsers = parser.add_subparsers(dest="command", required=True)
    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--cmake", default=shutil.which("cmake") or "cmake")
    doctor.add_argument("--ninja", default=shutil.which("ninja") or "ninja")
    doctor.add_argument("--west", default=shutil.which("west") or "west")
    doctor.add_argument("--nrfutil", default=shutil.which("nrfutil") or "nrfutil")
    doctor.add_argument("--jlink", default=shutil.which("JLinkGDBServerCLExe") or "JLinkGDBServerCLExe")
    doctor.add_argument("--gdb")
    doctor.set_defaults(handler=command_doctor)

    reference = subparsers.add_parser("reference")
    reference_commands = reference.add_subparsers(dest="reference_command", required=True)
    reference_prepare = reference_commands.add_parser("prepare")
    reference_prepare.add_argument("oracle", choices=("ncs-hello-world", "nrf-bm-leds-s115"))
    reference_prepare.add_argument("--root", type=Path, required=True)
    reference_prepare.add_argument("--toolchain", type=Path, required=True)
    reference_prepare.set_defaults(handler=command_prepare)
    reference_build = reference_commands.add_parser("build")
    reference_build.add_argument("oracle", choices=("ncs-hello-world", "nrf-bm-leds-s115"))
    reference_build.add_argument("--timeout", type=float, default=900)
    reference_build.set_defaults(handler=command_build)

    inspect = subparsers.add_parser("inspect")
    inspect.add_argument("--manifest", type=Path, required=True)
    inspect.set_defaults(handler=command_inspect)
    for name, handler in (("flash", command_flash), ("reset", command_reset), ("run", command_run)):
        command = subparsers.add_parser(name)
        add_device_arguments(command)
        if name == "run":
            command.add_argument("--token-timeout", type=float, default=10)
            command.add_argument("--serial-ready-delay", type=float, default=0.5)
        command.set_defaults(handler=handler)
    gdb = subparsers.add_parser("gdb-smoke")
    add_device_arguments(gdb)
    gdb.add_argument("--gdb")
    gdb.add_argument("--jlink", default=shutil.which("JLinkGDBServerCLExe") or "JLinkGDBServerCLExe")
    gdb.add_argument("--verify-token", action="store_true")
    gdb.add_argument("--post-main-break")
    gdb.add_argument("--token-timeout", type=float, default=10)
    gdb.add_argument("--serial-ready-delay", type=float, default=0.5)
    gdb.set_defaults(handler=command_gdb_smoke)
    args = parser.parse_args(argv)
    if getattr(args, "timeout", 1) <= 0:
        parser.error("--timeout must be positive")
    if getattr(args, "serial_ready_delay", 0) < 0:
        parser.error("--serial-ready-delay must not be negative")
    try:
        return args.handler(args)
    except (DeviceContractError, ImageContractError, ReferenceContractError, ToolError, OSError) as error:
        parser.exit(1, f"error: {error}\n")
