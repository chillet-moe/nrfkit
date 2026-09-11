# SPDX-License-Identifier: BSD-3-Clause
"""Bounded PPK2 serial access; protocol provenance is documented separately."""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any


class Ppk2Error(RuntimeError):
    pass


def discover(serial_number: str | None = None) -> list[dict[str, Any]]:
    from serial.tools import list_ports

    devices = []
    for p in list_ports.comports():
        if (p.vid, p.pid, p.product) != (0x1915, 0xC00A, "PPK2"):
            continue
        if serial_number is not None and p.serial_number != serial_number:
            continue
        # PPK2 exposes two CDC ports. Only USB interface 1 is the command/data port.
        interface = Path("/sys/class/tty") / Path(p.device).name / "device/bInterfaceNumber"
        if interface.read_text().strip() != "01":
            continue
        devices.append({"port": p.device, "serial": p.serial_number,
                        "vid": p.vid, "pid": p.pid, "description": p.description})
    return devices


def select(serial_number: str | None = None) -> dict[str, Any]:
    devices = discover(serial_number)
    if len(devices) != 1 or not devices[0]["serial"]:
        raise Ppk2Error("select exactly one identified PPK2 using --ppk-serial")
    return devices[0]


def parse_metadata(data: bytes) -> dict[str, float | str | None]:
    try:
        lines = data.decode("ascii").strip().splitlines()
    except UnicodeDecodeError as error:
        raise Ppk2Error("PPK2 is streaming or returned non-ASCII metadata") from error
    if not lines or lines[-1].strip() != "END":
        raise Ppk2Error("incomplete PPK2 metadata")
    result: dict[str, float | str | None] = {}
    for line in lines[:-1]:
        key, separator, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if not separator or not key or key in result:
            raise Ppk2Error("malformed PPK2 metadata")
        try:
            numeric = float(value)
            result[key] = numeric if math.isfinite(numeric) else None
        except ValueError:
            result[key] = value
    return result


class Ppk2:
    def __init__(self, port: str):
        import serial

        self.serial = serial.Serial(
            port, baudrate=115200, timeout=0.1, write_timeout=1, exclusive=True,
        )

    def close(self) -> None:
        self.serial.close()

    def command(self, data: bytes) -> None:
        if self.serial.write(data) != len(data):
            raise Ppk2Error("short PPK2 command write")
        self.serial.flush()

    def metadata(self) -> dict[str, float | str | None]:
        # Do not stop another client's capture or alter the supply merely to inspect it.
        self.command(b"\x19")
        deadline = time.monotonic() + 3.0
        data = bytearray()
        while time.monotonic() < deadline and len(data) < 16384:
            data.extend(self.serial.read(max(1, self.serial.in_waiting)))
            if b"END" in data:
                return parse_metadata(bytes(data))
        raise Ppk2Error("PPK2 metadata timed out or exceeded its size limit")

    def configure(self, voltage_mv: int, mode: str) -> dict[str, float | str | None]:
        if not 800 <= voltage_mv <= 5000 or mode not in ("source", "ampere"):
            raise Ppk2Error("invalid PPK2 voltage or mode")
        self.command(bytes([0x11, 2 if mode == "source" else 1]))
        self.command(bytes([0x0d, voltage_mv >> 8, voltage_mv & 0xff]))
        time.sleep(0.1)
        metadata = self.metadata()
        if metadata.get("vdd") != voltage_mv or metadata.get("mode") != (2 if mode == "source" else 1):
            raise Ppk2Error("PPK2 mode/voltage readback differs from the request")
        return metadata

    def power(self, enabled: bool) -> None:
        # Firmware has no output-state readback in metadata. Record this as a
        # command, never as an independently measured voltage or verified state.
        self.command(bytes([0x0c, int(enabled)]))

    def capture(self, path: Path, duration_s: float) -> dict[str, float | int]:
        if not math.isfinite(duration_s) or not 0.01 <= duration_s <= 600:
            raise Ppk2Error("capture duration must be between 0.01 and 600 seconds")
        count = math.ceil(duration_s * 100000) + 1
        wanted = count * 4
        received = 0
        self.serial.reset_input_buffer()
        started = time.monotonic()
        try:
            with path.open("xb") as stream:
                self.command(b"\x06")
                while received < wanted:
                    if time.monotonic() - started > duration_s + 5:
                        raise Ppk2Error("PPK2 acquisition timed out")
                    chunk = self.serial.read(min(wanted - received, max(1, self.serial.in_waiting)))
                    stream.write(chunk)
                    received += len(chunk)
        finally:
            self.command(b"\x07")
            # Drain remaining samples before the next metadata request.
            deadline = time.monotonic() + 0.3
            while time.monotonic() < deadline:
                self.serial.read(max(1, self.serial.in_waiting))
        return {"bytes": received, "sample_count": count,
                "wall_duration_s": time.monotonic() - started}


class Decoder:
    """Decode 32-bit PPK2 samples with counter continuity and explicit calibration.

    Unavailable coefficients use Nordic's published defaults. Range-switch samples
    are left unfiltered; preserve raw ADC data and flag transitions in the report.
    """
    def __init__(self, metadata: dict[str, Any], voltage_mv: int):
        defaults = {"r": [1031.64, 101.65, 10.15, 0.94, 0.043],
                    "gs": [1.] * 5, "gi": [1.] * 5, "o": [0.] * 5,
                    "s": [0.] * 5, "i": [0.] * 5, "ug": [1.] * 5}
        self.coefficients = {}
        self.defaulted = []
        for key, values in defaults.items():
            for index, default in enumerate(values):
                name = f"{key}{index}"
                value = metadata.get(name)
                if not isinstance(value, (float, int)) or not math.isfinite(value):
                    value = default
                    self.defaulted.append(name)
                if key == "r" and value <= 0:
                    raise Ppk2Error("PPK2 calibration contains a nonpositive resistor")
                self.coefficients[name] = value
        self.voltage_v = voltage_mv / 1000
        self.previous_counter: int | None = None
        self.previous_range: int | None = None
        self.range_transitions = 0
        self.range_counts = [0] * 5
        self.negative_samples = 0

    def sample(self, word: int) -> float:
        counter = (word >> 18) & 63
        if self.previous_counter is not None and counter != (self.previous_counter + 1) % 64:
            raise Ppk2Error("PPK2 sample-counter discontinuity; capture is not gap-free")
        self.previous_counter = counter
        current_range = (word >> 14) & 7
        if current_range >= 5:
            raise Ppk2Error("invalid PPK2 current range")
        self.range_counts[current_range] += 1
        if self.previous_range is not None and self.previous_range != current_range:
            self.range_transitions += 1
        self.previous_range = current_range
        c = self.coefficients
        r = str(current_range)
        raw = ((word & 0x3fff) * 4 - c["o"+r]) * (1.8 / 163840) / c["r"+r]
        current = c["ug"+r] * (raw * (c["gs"+r] * raw + c["gi"+r]) +
                                c["s"+r] * self.voltage_v + c["i"+r])
        if not math.isfinite(current):
            raise Ppk2Error("PPK2 calibration produced a nonfinite current")
        self.negative_samples += int(current < 0)
        return current


def decode_capture(raw: Path, csv_path: Path, metadata: dict[str, Any], voltage_mv: int) -> dict[str, Any]:
    import struct
    decoder = Decoder(metadata, voltage_mv)
    size = raw.stat().st_size
    if size < 8 or size % 4:
        raise Ppk2Error("PPK2 capture must contain complete 32-bit samples")
    total = 0.
    peak = -math.inf
    low = math.inf
    first = last = 0.
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
                output.write(f"{index / 100000:.5f},{current:.12g}\n")
                index += 1
    duration = (index - 1) / 100000
    charge = (total - (first + last) / 2) / 100000
    return {"sample_count": index, "duration_s": duration, "sample_period_s": 1e-5,
            "counter_continuity": True, "range_transitions": decoder.range_transitions,
            "range_sample_counts": decoder.range_counts, "negative_samples": decoder.negative_samples,
            "average_current_a": charge / duration, "minimum_current_a": low,
            "peak_current_a": peak, "charge_c": charge,
            "estimated_energy_j": charge * voltage_mv / 1000,
            "voltage_basis": "configured, not independently measured",
            "defaulted_coefficients": decoder.defaulted,
            "calibrated": metadata.get("calibrated") == 1,
            "filter": "none; range-switch spikes retained",
            "counter_limit": "6-bit counter cannot detect loss of exact multiples of 64 samples"}
