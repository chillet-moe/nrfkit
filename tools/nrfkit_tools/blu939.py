# SPDX-License-Identifier: BSD-3-Clause
"""Bounded BLU939 serial access without a vendor SDK runtime dependency."""

from __future__ import annotations

import math
from pathlib import Path
import struct
import time
from typing import Any


USB_VID = 0x15A2
USB_PID = 0x300A
SAMPLE_RATE_HZ = 100_000


class Blu939Error(RuntimeError):
    pass


def discover(serial_number: str | None = None) -> list[dict[str, Any]]:
    from serial.tools import list_ports

    devices = []
    for port in list_ports.comports():
        if (port.vid, port.pid) != (USB_VID, USB_PID):
            continue
        if serial_number is not None and port.serial_number != serial_number:
            continue
        devices.append({
            "port": port.device,
            "serial": port.serial_number,
            "vid": port.vid,
            "pid": port.pid,
            "description": port.description,
        })
    return devices


def select(serial_number: str | None = None) -> dict[str, Any]:
    devices = discover(serial_number)
    if len(devices) != 1 or not devices[0]["serial"]:
        raise Blu939Error(
            "select exactly one identified BLU939 using --instrument-serial"
        )
    return devices[0]


def parse_metadata(data: bytes) -> dict[str, float | str]:
    try:
        text = data.rstrip(b"\x00").decode("ascii")
    except UnicodeDecodeError as error:
        raise Blu939Error("BLU939 is streaming or returned non-ASCII metadata") from error
    lines = text.splitlines()
    if not lines or lines[-1].strip() != "END":
        raise Blu939Error("incomplete BLU939 metadata")
    result: dict[str, float | str] = {}
    for line in lines[:-1]:
        key, separator, value = line.partition(":")
        if not separator:
            key, separator, value = line.partition("=")
        key, value = key.strip().lower(), value.strip()
        if not separator or not key or not value or key in result:
            raise Blu939Error("malformed BLU939 metadata")
        try:
            numeric = float(value)
        except ValueError:
            result[key] = value
        else:
            if not math.isfinite(numeric):
                raise Blu939Error("BLU939 metadata contains a nonfinite value")
            result[key] = numeric
    required = {f"r{index}" for index in range(6)} | {
        f"o{index}" for index in range(6)
    }
    if not required.issubset(result):
        raise Blu939Error("incomplete BLU939 calibration metadata")
    if any(float(result[f"r{index}"]) <= 0 for index in range(6)):
        raise Blu939Error("BLU939 calibration contains a nonpositive resistor")
    return result


class Blu939:
    def __init__(self, port: str):
        import serial

        self.serial = serial.Serial(
            port, baudrate=115200, timeout=0.1, write_timeout=1, exclusive=True,
        )
        self.last_metadata_response = b""

    def close(self) -> None:
        self.serial.close()

    def command(self, data: bytes) -> None:
        if self.serial.write(data) != len(data):
            raise Blu939Error("short BLU939 command write")
        self.serial.flush()

    def metadata(self) -> dict[str, float | str]:
        self.serial.reset_input_buffer()
        self.command(b"\x19")
        deadline = time.monotonic() + 3.0
        quiet_deadline: float | None = None
        data = bytearray()
        while time.monotonic() < deadline and len(data) < 16384:
            chunk = self.serial.read(max(1, self.serial.in_waiting))
            if chunk:
                data.extend(chunk)
                quiet_deadline = time.monotonic() + 0.1
                if b"\nEND\n" in data:
                    self.last_metadata_response = bytes(data)
                    return parse_metadata(self.last_metadata_response)
            elif quiet_deadline is not None and time.monotonic() >= quiet_deadline:
                self.last_metadata_response = bytes(data)
                return parse_metadata(self.last_metadata_response)
        self.last_metadata_response = bytes(data)
        raise Blu939Error("BLU939 metadata timed out or exceeded its size limit")

    def configure_voltage(self, voltage_mv: int) -> dict[str, float | str]:
        if not 500 <= voltage_mv <= 5000:
            raise Blu939Error("BLU939 voltage must be 500..5000 mV")
        self.command(bytes([0x0D, voltage_mv >> 8, voltage_mv & 0xFF]))
        deadline = time.monotonic() + 2.0
        while True:
            time.sleep(0.1)
            metadata = self.metadata()
            if metadata.get("vdd") == voltage_mv:
                return metadata
            if time.monotonic() >= deadline:
                raise Blu939Error(
                    "BLU939 voltage readback differs from the request: "
                    f"vdd={metadata.get('vdd')}"
                )

    def power(self, enabled: bool) -> None:
        self.command(bytes([0x0C, int(enabled)]))

    def capture(self, path: Path, duration_s: float) -> dict[str, float | int]:
        if not math.isfinite(duration_s) or not 0.01 <= duration_s <= 600:
            raise Blu939Error("capture duration must be between 0.01 and 600 seconds")
        sample_count = math.ceil(duration_s * SAMPLE_RATE_HZ) + 1
        wanted = sample_count * 4
        received = 0
        self.serial.reset_input_buffer()
        started = time.monotonic()
        try:
            with path.open("xb") as stream:
                self.command(b"\x06")
                while received < wanted:
                    if time.monotonic() - started > duration_s + 5:
                        raise Blu939Error("BLU939 acquisition timed out")
                    chunk = self.serial.read(
                        min(wanted - received, max(1, self.serial.in_waiting))
                    )
                    stream.write(chunk)
                    received += len(chunk)
        finally:
            self.command(b"\x07")
            deadline = time.monotonic() + 0.3
            while time.monotonic() < deadline:
                self.serial.read(max(1, self.serial.in_waiting))
        return {
            "bytes": received,
            "sample_count": sample_count,
            "wall_duration_s": time.monotonic() - started,
        }


class Decoder:
    """Decode unfiltered samples using calibration returned by the instrument."""

    def __init__(self, metadata: dict[str, Any], voltage_mv: int):
        self.resistors = []
        self.offsets = []
        for index in range(6):
            resistor = metadata.get(f"r{index}")
            offset = metadata.get(f"o{index}")
            if (
                not isinstance(resistor, (float, int))
                or not math.isfinite(resistor)
                or resistor <= 0
                or not isinstance(offset, (float, int))
                or not math.isfinite(offset)
            ):
                raise Blu939Error("invalid BLU939 calibration metadata")
            self.resistors.append(float(resistor))
            self.offsets.append(float(offset))
        self.voltage_v = voltage_mv / 1000
        self.previous_range: int | None = None
        self.range_transitions = 0
        self.range_counts = [0] * 6
        self.saturated_range_samples = 0
        self.negative_samples = 0

    def sample(self, word: int) -> float:
        encoded_range = (word >> 14) & 7
        current_range = min(encoded_range, 5)
        self.saturated_range_samples += int(encoded_range > 5)
        self.range_counts[current_range] += 1
        if self.previous_range is not None and self.previous_range != current_range:
            self.range_transitions += 1
        self.previous_range = current_range
        adc_code = (word & 0x3FFF) * 4
        current = (
            (adc_code - self.offsets[current_range])
            * (1.8 / 163840)
            / self.resistors[current_range]
        )
        if not math.isfinite(current):
            raise Blu939Error("BLU939 calibration produced a nonfinite current")
        self.negative_samples += int(current < 0)
        return current


def decode_capture(
    raw: Path,
    csv_path: Path,
    metadata: dict[str, Any],
    voltage_mv: int,
) -> dict[str, Any]:
    decoder = Decoder(metadata, voltage_mv)
    size = raw.stat().st_size
    if size < 8 or size % 4:
        raise Blu939Error("BLU939 capture must contain complete 32-bit samples")
    total = 0.0
    peak = -math.inf
    low = math.inf
    first = last = 0.0
    index = 0
    with raw.open("rb") as source, csv_path.open("x", encoding="ascii") as output:
        output.write("time_s,current_a\n")
        while chunk := source.read(65536):
            for (word,) in struct.iter_unpack("<I", chunk):
                current = decoder.sample(word)
                if index == 0:
                    first = current
                last = current
                total += current
                low, peak = min(low, current), max(peak, current)
                output.write(f"{index / SAMPLE_RATE_HZ:.5f},{current:.12g}\n")
                index += 1
    duration = (index - 1) / SAMPLE_RATE_HZ
    charge = (total - (first + last) / 2) / SAMPLE_RATE_HZ
    return {
        "sample_count": index,
        "duration_s": duration,
        "sample_period_s": 1 / SAMPLE_RATE_HZ,
        "range_transitions": decoder.range_transitions,
        "range_sample_counts": decoder.range_counts,
        "saturated_range_samples": decoder.saturated_range_samples,
        "negative_samples": decoder.negative_samples,
        "average_current_a": charge / duration,
        "minimum_current_a": low,
        "peak_current_a": peak,
        "charge_c": charge,
        "estimated_energy_j": charge * decoder.voltage_v,
        "voltage_basis": "configured, not independently measured",
        "filter": "none; range-switch transients retained",
        "continuity": "unverified; complete records only, no sequence counter",
        "calibration_metadata_flag": metadata.get("calibrated"),
        "calibration_coefficients": "six instrument R/O pairs applied",
        "calibration_status": (
            "metadata flag retained but not interpreted; the vendor conversion path "
            "uses R/O coefficients and does not consult this flag"
        ),
    }
