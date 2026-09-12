# SPDX-License-Identifier: BSD-3-Clause
"""Read-only protocol support for the pinned ppk2-eeprom audit firmware."""

from __future__ import annotations

import math
from pathlib import Path
import re
import struct
import time
from typing import Any

from .ppk2 import Ppk2Error


PPK2_EEPROM_RELEASE = "r0"
PPK2_EEPROM_PACKAGE_SHA256 = (
    "1eafcc943caa9859529ac5cb7c6588cf70e1caf79131116bf8cccf3820181eef"
)
PPK2_EEPROM_SOURCE_COMMIT = "380720e43cc978c176b5899e2f376a569849231d"
PPK2_EEPROM_SIZE = 0x100
PPK2_EEPROM_PROMPT = b"uart:~$ "
PPK2_EEPROM_USB_ID = (0x2FE3, 0x0001)
CALIBRATION_OFFSETS = {
    **{f"r{index}": index * 4 for index in range(5)},
    **{f"gs{index}": 20 + index * 4 for index in range(5)},
    **{f"o{index}": 40 + index * 4 for index in range(5)},
    **{f"s{index}": 60 + index * 4 for index in range(5)},
    **{f"i{index}": 80 + index * 4 for index in range(5)},
    **{f"gi{index}": 100 + index * 4 for index in range(5)},
    **{f"ug{index}": 128 + index * 4 for index in range(5)},
}


def eeprom_shell_ports() -> set[str]:
    """Return serial ports matching the immutable temporary-firmware USB ID."""
    from serial.tools import list_ports

    return {
        port.device for port in list_ports.comports()
        if (port.vid, port.pid) == PPK2_EEPROM_USB_ID
    }


def find_new_eeprom_shell_port(existing_ports: set[str]) -> str | None:
    matches = eeprom_shell_ports() - existing_ports
    if len(matches) > 1:
        raise Ppk2Error("multiple new ppk2-eeprom serial ports appeared")
    return next(iter(matches), None)


def wait_new_eeprom_shell_port(existing_ports: set[str], timeout: float) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        port = find_new_eeprom_shell_port(existing_ports)
        if port is not None:
            return port
        time.sleep(0.25)
    raise Ppk2Error("temporary ppk2-eeprom serial shell did not enumerate")


def parse_eeprom_dump(
    output: str, expected_offset: int = 0, expected_size: int = PPK2_EEPROM_SIZE,
) -> bytes:
    chunks: dict[int, bytes] = {}
    line_pattern = re.compile(r"^([0-9a-fA-F]{8}):\s+(.*?)\s+\|", re.MULTILINE)
    for match in line_pattern.finditer(output):
        address = int(match.group(1), 16)
        octets = re.findall(
            r"(?<![0-9a-fA-F])[0-9a-fA-F]{2}(?![0-9a-fA-F])", match.group(2),
        )
        if not octets or address in chunks:
            raise Ppk2Error("malformed or duplicate ppk2-eeprom dump line")
        chunks[address] = bytes.fromhex(" ".join(octets))
    data = bytearray()
    for address in sorted(chunks):
        if address != expected_offset + len(data):
            raise Ppk2Error("ppk2-eeprom dump has a gap or unexpected address")
        data.extend(chunks[address])
    if len(data) != expected_size:
        raise Ppk2Error(
            f"ppk2-eeprom dump has {len(data)} bytes, expected {expected_size}"
        )
    return bytes(data)


def parse_calibration_read(output: str) -> dict[str, dict[str, Any]]:
    pattern = re.compile(
        r"^\s*([a-z]+[0-4])\s+\(\s*(\d+)\):.*?,\s*"
        r"([0-9a-fA-F]{2})\s+([0-9a-fA-F]{2})\s+"
        r"([0-9a-fA-F]{2})\s+([0-9a-fA-F]{2})\s*$",
        re.MULTILINE,
    )
    parsed: dict[str, dict[str, Any]] = {}
    for match in pattern.finditer(output):
        name = match.group(1)
        offset = int(match.group(2))
        if name not in CALIBRATION_OFFSETS or CALIBRATION_OFFSETS[name] != offset:
            raise Ppk2Error("ppk2-eeprom calibration output has an unexpected field")
        if name in parsed:
            raise Ppk2Error("ppk2-eeprom calibration output has a duplicate field")
        raw = bytes(int(match.group(index), 16) for index in range(3, 7))
        value = struct.unpack("<f", raw)[0]
        if math.isnan(value):
            classification = "nan"
            json_value: float | None = None
        elif math.isinf(value):
            classification = "+inf" if value > 0 else "-inf"
            json_value = None
        else:
            classification = "finite"
            json_value = value
        parsed[name] = {
            "offset": offset,
            "bytes": raw.hex(),
            "value": json_value,
            "classification": classification,
        }
    if set(parsed) != set(CALIBRATION_OFFSETS):
        missing = sorted(set(CALIBRATION_OFFSETS) - set(parsed))
        raise Ppk2Error(f"ppk2-eeprom calibration output is incomplete: {', '.join(missing)}")
    return parsed


def verify_calibration_bytes(calibration: dict[str, dict[str, Any]], eeprom: bytes) -> None:
    if len(eeprom) != PPK2_EEPROM_SIZE:
        raise Ppk2Error("invalid PPK2 EEPROM image size")
    for name, offset in CALIBRATION_OFFSETS.items():
        if calibration[name]["bytes"] != eeprom[offset:offset + 4].hex():
            raise Ppk2Error(f"calibration field {name} differs from the raw EEPROM read")


class Ppk2EepromShell:
    """Read-only interface to the pinned ppk2-eeprom Zephyr shell."""

    def __init__(self, port: str):
        import serial

        self.serial = serial.Serial(
            port, baudrate=115200, timeout=0.1, write_timeout=1, exclusive=True,
        )
        self._query(b"\r\n", 5.0)

    def close(self) -> None:
        self.serial.close()

    def _query(self, command: bytes, timeout: float) -> str:
        raw_read = re.fullmatch(
            rb"eeprom read eeprom@50 (0|16|32|48|64|80|96|112|128|144|160|176|"
            rb"192|208|224|240) 16\r\n",
            command,
        )
        if command not in (b"\r\n", b"cal_read\r\n") and raw_read is None:
            raise Ppk2Error("attempted an unsupported ppk2-eeprom shell command")
        self.serial.reset_input_buffer()
        if self.serial.write(command) != len(command):
            raise Ppk2Error("short ppk2-eeprom shell command write")
        self.serial.flush()
        deadline = time.monotonic() + timeout
        data = bytearray()
        while time.monotonic() < deadline and len(data) < 65536:
            data.extend(self.serial.read(max(1, self.serial.in_waiting)))
            if PPK2_EEPROM_PROMPT in data:
                try:
                    return data.decode("utf-8")
                except UnicodeDecodeError as error:
                    raise Ppk2Error("ppk2-eeprom shell returned invalid text") from error
        raise Ppk2Error("ppk2-eeprom shell timed out or exceeded its output limit")

    def calibration_read(self) -> tuple[str, dict[str, dict[str, Any]]]:
        output = self._query(b"cal_read\r\n", 5.0)
        return output, parse_calibration_read(output)

    def eeprom_read(self) -> tuple[str, bytes]:
        outputs = []
        image = bytearray()
        for offset in range(0, PPK2_EEPROM_SIZE, 16):
            output = self._query(
                f"eeprom read eeprom@50 {offset} 16\r\n".encode("ascii"), 5.0,
            )
            outputs.append(output)
            image.extend(parse_eeprom_dump(output, offset, 16))
        return "\n".join(outputs), bytes(image)

    def reset_to_bootloader(self) -> None:
        command = b"reset_bl\r\n"
        if self.serial.write(command) != len(command):
            raise Ppk2Error("short ppk2-eeprom reset command write")
        self.serial.flush()
        # pyserial.flush() only drains the host-side buffer. Keep the handle open
        # until the firmware has consumed reset_bl and USB actually disconnects.
        deadline = time.monotonic() + 3.0
        port = Path(self.serial.port)
        while time.monotonic() < deadline:
            try:
                self.serial.read(max(1, self.serial.in_waiting))
            except OSError:
                return
            if not port.exists():
                return
        raise Ppk2Error("ppk2-eeprom reset_bl did not disconnect the temporary shell")
