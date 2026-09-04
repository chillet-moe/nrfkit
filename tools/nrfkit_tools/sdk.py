# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .device import safe_backend_contract
from .image import parse_elf, parse_ihex, require_allowed
from .process import atomic_json


class SdkContractError(RuntimeError):
    pass


STANDALONE_RRAM_ALLOWLIST = [[0x00000000, 0x001FCF00]]


def _merged(ranges: tuple[tuple[int, int], ...]) -> tuple[tuple[int, int], ...]:
    result: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return tuple(result)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_device_manifest(
    project: Path,
    build_dir: Path,
    target: str,
    expected_token: str,
) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", target):
        raise SdkContractError("SDK target is not a safe artifact basename")
    if (
        not expected_token
        or len(expected_token) > 256
        or any(ord(character) < 0x20 or ord(character) > 0x7E for character in expected_token)
    ):
        raise SdkContractError("expected token must be 1-256 printable ASCII characters")
    build_dir = build_dir.resolve()
    elf = build_dir / f"{target}.elf"
    ihex = build_dir / f"{target}.hex"
    layout_path = build_dir / f"{target}.image-layout.json"
    for path in (elf, ihex, layout_path):
        if not path.is_file():
            raise SdkContractError(f"SDK artifact is missing: {path}")
    try:
        layout: dict[str, Any] = json.loads(layout_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SdkContractError(f"invalid SDK layout manifest: {error}") from error
    expected_layout = {
        "schema": "nrfkit-image-layout/v1",
        "target": target,
        "soc": "nrf54lm20a",
        "core": "cpuapp",
        "rram": {"origin": 0, "length": 0x001FCF00},
        "rram_scratch": {"origin": 0x001FCF00, "length": 0x100, "write_unit": 16},
        "ram": {"origin": 0x20000000, "length": 0x00040000},
        "configuration_regions_allowed": False,
    }
    if layout != expected_layout:
        raise SdkContractError("SDK layout manifest does not match the guarded LM20 contract")

    elf_image = parse_elf(elf)
    hex_image = parse_ihex(ihex)
    allowlist = STANDALONE_RRAM_ALLOWLIST
    require_allowed(elf_image.ranges, tuple(tuple(item) for item in allowlist))
    require_allowed(hex_image.ranges, tuple(tuple(item) for item in allowlist))
    if _merged(elf_image.ranges) != _merged(hex_image.ranges):
        raise SdkContractError("SDK ELF and HEX load ranges do not match")
    if elf_image.entry is None or not any(
        start <= elf_image.entry < end for start, end in elf_image.ranges
    ):
        raise SdkContractError("SDK ELF entry is outside its load image")
    source_lock = project / "docs/provenance/sources.lock"
    manifest = {
        "schema": "nrfkit-image/v1",
        "oracle": f"sdk-{target}",
        "source_receipt_sha256": sha256(source_lock),
        "soc": "nrf54lm20a",
        "core": "Application",
        "board": "nrf54lm20dk/nrf54lm20a/cpuapp",
        "board_version": "PCA10184",
        "device_family": "NRF54L",
        "expected_token": expected_token,
        "vcom": 1,
        "backend": safe_backend_contract(),
        "debug_allowlist": allowlist,
        "debug_elf": {
            "path": str(elf),
            "sha256": sha256(elf),
            "entry": elf_image.entry,
            "ranges": elf_image.ranges,
        },
        "images": [{
            "domain": target,
            "order": 0,
            "path": str(ihex),
            "sha256": sha256(ihex),
            "ranges": hex_image.ranges,
            "allowlist": allowlist,
        }],
    }
    output = build_dir / f"{target}.device-manifest.json"
    atomic_json(output, manifest)
    return output
