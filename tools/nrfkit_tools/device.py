# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


class DeviceContractError(RuntimeError):
    pass


SAFE_PROGRAM_OPTIONS = (
    ("chip_erase_mode", "ERASE_NONE"),
    ("verify", "VERIFY_READ"),
    ("reset", "RESET_NONE"),
)


def safe_backend_contract() -> dict[str, Any]:
    return {
        "programmer": "nrfutil-device",
        "program_options": dict(SAFE_PROGRAM_OPTIONS),
        "resetter": "nrfutil-device-reset",
    }


def parse_json_lines(output: str, field: str) -> Any:
    matches: list[Any] = []
    for number, line in enumerate(output.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise DeviceContractError(f"invalid JSON event on line {number}") from error
        if event.get("type") == "info" and isinstance(event.get("data"), dict):
            if field in event["data"]:
                matches.append(event["data"][field])
    if len(matches) != 1:
        raise DeviceContractError(f"expected one nrfutil info event containing {field!r}")
    return matches[0]


def select_device(
    devices: Iterable[dict[str, Any]], board_version: str, serial: str | None
) -> dict[str, Any]:
    matches = [
        device
        for device in devices
        if device.get("devkit", {}).get("boardVersion") == board_version
        and (serial is None or device.get("serialNumber") == serial)
    ]
    if not matches:
        raise DeviceContractError(f"no connected {board_version} device matches the selection")
    if len(matches) > 1:
        raise DeviceContractError(
            f"multiple connected {board_version} devices match; select a probe serial explicitly"
        )
    return matches[0]


def nrfutil_prefix(executable: str) -> list[str]:
    return [executable, "--log-output", "stdout", "--json"]


def program_argv(
    executable: str, image: str, serial: str, family: str, core: str
) -> list[str]:
    options = ",".join(f"{name}={value}" for name, value in SAFE_PROGRAM_OPTIONS)
    return nrfutil_prefix(executable) + [
        "device", "program", "--firmware", image, "--serial-number", serial,
        "--traits", "jlink", "--core", core.lower(), "--family", family.lower(),
        "--options", options,
    ]


def reset_argv(
    executable: str, serial: str, family: str, core: str,
    reset_kind: str = "RESET_DEFAULT",
) -> list[str]:
    return nrfutil_prefix(executable) + [
        "device", "reset", "--serial-number", serial, "--traits", "jlink",
        "--family", family.lower(), "--core", core.lower(),
        "--reset-kind", reset_kind,
    ]


def read_memory_argv(
    executable: str, output: str, serial: str, family: str, core: str,
    address: int, size: int,
) -> list[str]:
    return nrfutil_prefix(executable) + [
        "device", "read", "--address", f"0x{address:08x}",
        "--bytes", str(size), "--width", "8", "--to-file", output,
        "--serial-number", serial, "--traits", "jlink",
        "--core", core.lower(), "--family", family.lower(),
    ]
