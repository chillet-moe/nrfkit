# SPDX-License-Identifier: BSD-3-Clause
"""CMSIS-DAP/OpenOCD transport for the guarded LM20 application workflow."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Any

from .image import require_allowed
from .process import run_logged


class OpenOcdError(RuntimeError):
    pass


RRAM_END = 0x001FD000


def tcl_word(value: str | Path) -> str:
    value = str(value)
    if any(c in value for c in "{}\\\n\r\x00"):
        raise OpenOcdError("unsupported character in Tcl argument")
    return "{" + value + "}"


def discover(vid: int, pid: int, serial: str | None) -> list[dict[str, Any]]:
    import usb.core
    import usb.util

    result = []
    for device in usb.core.find(find_all=True, idVendor=vid, idProduct=pid):
        try:
            identity = device.serial_number
            if not identity or (serial is not None and serial != identity):
                continue
            interfaces = []
            for configuration in device:
                for interface in configuration:
                    name = usb.util.get_string(device, interface.iInterface) or ""
                    bulk = [ep for ep in interface if ep.bmAttributes & 3 == 2]
                    if "CMSIS-DAP" in name and any(ep.bEndpointAddress & 0x80 for ep in bulk) and any(
                        not ep.bEndpointAddress & 0x80 for ep in bulk
                    ):
                        interfaces.append(interface.bInterfaceNumber)
            if len(interfaces) == 1:
                result.append({"serial": identity, "vid": vid, "pid": pid,
                               "interface": interfaces[0], "product": device.product})
        finally:
            usb.util.dispose_resources(device)
    return result


def configuration(device: dict[str, Any], speed_khz: int, gdb_port: int | None = None) -> str:
    if speed_khz not in (1000, 2000, 4000):
        raise OpenOcdError("validated SWD requests are 1000, 2000, or 4000 kHz")
    if gdb_port is not None and not 1024 <= gdb_port <= 65535:
        raise OpenOcdError("invalid GDB port")
    return f"""adapter driver cmsis-dap
cmsis-dap backend usb_bulk
cmsis-dap usb interface {device['interface']}
adapter usb vid_pid 0x{device['vid']:04x} 0x{device['pid']:04x}
adapter serial {tcl_word(device['serial'])}
bindto 127.0.0.1
gdb port {gdb_port if gdb_port is not None else 'disabled'}
tcl port disabled
telnet port disabled
source [find target/nordic/nrf54lm20.cfg]
adapter speed {speed_khz}
# Use wired nRESET. Do not fall back to CTRL-AP soft reset (anomaly 63).
reset_config srst_only srst_nogate
adapter srst pulse_width 100
adapter srst delay 100
"""


IDENTIFY = """set part [lindex [read_memory 0x00ffc31c 32 1] 0]
set variant [lindex [read_memory 0x00ffc320 32 1] 0]
set rram_kib [lindex [read_memory 0x00ffc32c 32 1] 0]
if {($part != 0x054bc20a && $part != 0x054bc20b) || $rram_kib != 2036} {
    error "Target is not an accepted LM20 application device"
}
echo [format "NRFKIT_ID %08x %08x %u" $part $variant $rram_kib]
echo [format "NRFKIT_DEVICEID %08x %08x" [lindex [read_memory 0x00ffc304 32 1] 0] [lindex [read_memory 0x00ffc308 32 1] 0]]
"""


def parse_identity(output: str) -> dict[str, Any]:
    match = re.search(r"^NRFKIT_ID ([0-9a-f]{8}) ([0-9a-f]{8}) (\d+)$", output, re.M)
    device = re.search(r"^NRFKIT_DEVICEID ([0-9a-f]{8}) ([0-9a-f]{8})$", output, re.M)
    if not match or not device:
        raise OpenOcdError("OpenOCD did not report the target identity")
    part, variant = (int(match[i], 16) for i in (1, 2))
    size = int(match[3])
    if part not in (0x054BC20A, 0x054BC20B) or size != 2036:
        raise OpenOcdError("OpenOCD target identity mismatch")
    return {"part": part, "variant": variant, "rram_kib": size,
            "device_id": device[1] + device[2]}


def addressed_hex(start: int, data: bytes) -> str:
    require_allowed(((start, start + len(data)),), ((0, RRAM_END),))
    if start % 16 or len(data) % 16:
        raise OpenOcdError("backup HEX ranges must be 16-byte aligned")
    lines = []
    upper = None
    def record(offset: int, kind: int, payload: bytes) -> str:
        body = bytes([len(payload)]) + offset.to_bytes(2, "big") + bytes([kind]) + payload
        return ":" + (body + bytes([-sum(body) & 0xff])).hex().upper()
    for offset in range(0, len(data), 16):
        address = start + offset
        # Backups use 16-byte aligned ranges, so records never cross a 64 KiB boundary.
        if upper != address >> 16:
            upper = address >> 16
            lines.append(record(0, 4, upper.to_bytes(2, "big")))
        lines.append(record(address & 0xffff, 0, data[offset:offset + 16]))
    lines.append(record(0, 1, b""))
    return "\n".join(lines) + "\n"


class OpenOcd:
    def __init__(self, executable: Path, scripts: Path, device: dict[str, Any],
                 run_dir: Path, speed_khz: int, timeout: float):
        self.executable = executable.resolve()
        self.scripts = scripts.resolve()
        if not self.executable.is_file() or not (self.scripts / "target/nordic/nrf54lm20.cfg").is_file():
            raise OpenOcdError("OpenOCD executable and matching LM20 scripts are required")
        self.device, self.run_dir = device, run_dir
        self.speed_khz, self.timeout = speed_khz, timeout

    def receipt(self) -> dict[str, Any]:
        def digest(path: Path) -> str:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        return {"executable": str(self.executable), "sha256": digest(self.executable),
                "scripts": str(self.scripts),
                "target_sha256": digest(self.scripts / "target/nordic/nrf54lm20.cfg"),
                "family_sha256": digest(self.scripts / "target/nordic/nrf54l.cfg"),
                "swd_khz_requested": self.speed_khz}

    def argv(self, name: str, commands: str, *, gdb_port: int | None = None) -> list[str]:
        script = self.run_dir / f"{name}.tcl"
        script.write_text(configuration(self.device, self.speed_khz, gdb_port) + commands)
        script.chmod(0o400)
        return [str(self.executable), "-s", str(self.scripts), "-f", str(script)]

    def run(self, name: str, commands: str) -> str:
        result = run_logged(self.argv(name, "init\n" + IDENTIFY + commands + "\nshutdown\n"),
                            self.run_dir / f"{name}.log", self.timeout)
        if result.returncode or result.timed_out:
            raise OpenOcdError(f"OpenOCD {name} failed; see its run log")
        parse_identity(result.stdout)
        return result.stdout
