# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from pathlib import Path
import re

from .image import ImageContractError, parse_ihex, require_allowed


M6_SETTINGS_START = 0x001E1800
M6_SETTINGS_SIZE = 0x2000
M6_SETTINGS_RANGE = (M6_SETTINGS_START, M6_SETTINGS_START + M6_SETTINGS_SIZE)


def is_m6_bond_manifest(oracle: str) -> bool:
    return oracle in {
        "sdk-m6_ble_validation",
        "nrf-bm-ble-hids-mouse-s115",
    } or re.fullmatch(r"sdk-m6_ble_phase[4-6]", oracle) is not None


def _record(kind: int, offset: int, data: bytes) -> str:
    raw = bytes((len(data), offset >> 8, offset & 0xFF, kind)) + data
    checksum = (-sum(raw)) & 0xFF
    return ":" + (raw + bytes((checksum,))).hex().upper()


def write_erased_m6_settings(path: Path) -> None:
    lines = [_record(4, 0, (M6_SETTINGS_START >> 16).to_bytes(2, "big"))]
    for address in range(M6_SETTINGS_START, M6_SETTINGS_RANGE[1], 16):
        lines.append(_record(0, address & 0xFFFF, b"\xFF" * 16))
    lines.append(_record(1, 0, b""))
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    require_exact_m6_settings_image(path)


def require_exact_m6_settings_image(path: Path) -> None:
    image = parse_ihex(path)
    require_allowed(image.ranges, (M6_SETTINGS_RANGE,))
    if image.ranges != (M6_SETTINGS_RANGE,):
        raise ImageContractError("bond image must cover exactly the M6 settings region")


def read_exact_m6_settings(path: Path) -> bytes:
    require_exact_m6_settings_image(path)
    memory: dict[int, int] = {}
    base = 0
    for text in path.read_text(encoding="ascii").splitlines():
        raw = bytes.fromhex(text[1:])
        length, high, low, kind = raw[:4]
        payload = raw[4 : 4 + length]
        if kind == 0:
            address = base + (high << 8 | low)
            for index, value in enumerate(payload):
                memory[address + index] = value
        elif kind == 2:
            base = int.from_bytes(payload, "big") << 4
        elif kind == 4:
            base = int.from_bytes(payload, "big") << 16
    return bytes(memory[address] for address in range(*M6_SETTINGS_RANGE))
