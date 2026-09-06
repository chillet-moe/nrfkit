# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct
from typing import Any

from .device import safe_backend_contract
from .image import parse_elf, parse_ihex, require_allowed
from .process import atomic_json


class SdkContractError(RuntimeError):
    pass


STANDALONE_RRAM_ALLOWLIST = [[0x00000000, 0x001FCF00]]
FREESTANDING_STACK_BYTES = 0x4000
LM20_SAFE_RRAM_END = 0x001FD000
LM20_RAM0_ORIGIN = 0x20000000
LM20_RAM0_END = 0x20040000


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


def _elf_load_budget(
    elf: Path, *, ram_origin: int, ram_length: int, rram_origin: int, rram_length: int,
) -> dict[str, int]:
    data = elf.read_bytes()
    if len(data) < 52 or data[:5] != b"\x7fELF\x01" or data[5] != 1:
        raise SdkContractError("SDC budget requires a little-endian ELF32 image")
    header = struct.Struct("<16sHHIIIIIHHHHHH")
    program = struct.Struct("<IIIIIIII")
    fields = header.unpack_from(data)
    offset, entry_size, count = fields[5], fields[9], fields[10]
    if entry_size != program.size or offset + count * entry_size > len(data):
        raise SdkContractError("SDC ELF program header table is invalid")
    ram_allocated = 0
    ram_initialized = 0
    rram_file = 0
    for index in range(count):
        kind, unused_offset, virtual, physical, file_size, memory_size, unused_flags, unused_align = (
            program.unpack_from(data, offset + index * entry_size)
        )
        if kind != 1:
            continue
        if ram_origin <= virtual < ram_origin + ram_length:
            if virtual + memory_size > ram_origin + ram_length:
                raise SdkContractError("SDC ELF LOAD segment exceeds RAM")
            ram_allocated += memory_size
            ram_initialized += file_size
        if rram_origin <= physical < rram_origin + rram_length:
            if physical + file_size > rram_origin + rram_length:
                raise SdkContractError("SDC ELF LOAD segment exceeds RRAM")
            rram_file += file_size
    total_reserved = ram_allocated + FREESTANDING_STACK_BYTES
    return {
        "ram_allocated_bytes": ram_allocated,
        "ram_initialized_bytes": ram_initialized,
        "stack_reserved_bytes": FREESTANDING_STACK_BYTES,
        "ram_total_reserved_bytes": total_reserved,
        "ram_headroom_bytes": ram_length - total_reserved,
        "ram_capacity_bytes": ram_length,
        "rram_file_bytes": rram_file,
    }


def _validated_custom_allowlist(layout: dict[str, Any], target: str) -> list[list[int]]:
    required = {
        "schema": "nrfkit-image-layout/v1",
        "target": target,
        "soc": "nrf54lm20a",
        "core": "cpuapp",
        "configuration_regions_allowed": False,
    }
    if any(layout.get(key) != value for key, value in required.items()):
        raise SdkContractError("SDK layout manifest identity or safety fields are invalid")
    allowed_fields = set(required) | {"rram", "ram", "settings", "rram_scratch"}
    if set(layout) - allowed_fields:
        raise SdkContractError("custom SDK layout contains unsupported fields")

    def region(name: str, low: int, high: int) -> tuple[int, int]:
        value = layout.get(name)
        if not isinstance(value, dict) or set(value) - {"origin", "length", "write_unit"}:
            raise SdkContractError(f"custom SDK layout {name} region is invalid")
        origin = value.get("origin")
        length = value.get("length")
        if (isinstance(origin, bool) or not isinstance(origin, int) or
                isinstance(length, bool) or not isinstance(length, int) or length <= 0 or
                origin < low or origin + length > high):
            raise SdkContractError(f"custom SDK layout {name} range is unsafe")
        write_unit = value.get("write_unit")
        if write_unit is not None and (
            isinstance(write_unit, bool) or not isinstance(write_unit, int) or write_unit <= 0
        ):
            raise SdkContractError(f"custom SDK layout {name} write unit is invalid")
        return origin, origin + length

    rram = region("rram", 0, LM20_SAFE_RRAM_END)
    region("ram", LM20_RAM0_ORIGIN, LM20_RAM0_END)
    declared_rram_regions = [("rram", rram)]
    for name in ("settings", "rram_scratch"):
        if name in layout:
            declared_rram_regions.append((name, region(name, 0, LM20_SAFE_RRAM_END)))
    for index, (first_name, first) in enumerate(declared_rram_regions):
        for second_name, second in declared_rram_regions[index + 1:]:
            if first[0] < second[1] and second[0] < first[1]:
                raise SdkContractError(
                    f"custom SDK layout regions overlap: {first_name} and {second_name}"
                )
    return [[rram[0], rram[1]]]


def create_device_manifest(
    project: Path,
    build_dir: Path,
    target: str,
    expected_token: str,
    hci_h4_hwfc_1m: bool = False,
    *, image_layout: Path | None = None,
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
    layout_path = (
        image_layout.resolve() if image_layout is not None
        else build_dir / f"{target}.image-layout.json"
    )
    for path in (elf, ihex, layout_path):
        if not path.is_file():
            raise SdkContractError(f"SDK artifact is missing: {path}")
    try:
        layout: dict[str, Any] = json.loads(layout_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SdkContractError(f"invalid SDK layout manifest: {error}") from error
    standalone_layout = {
        "schema": "nrfkit-image-layout/v1",
        "target": target,
        "soc": "nrf54lm20a",
        "core": "cpuapp",
        "rram": {"origin": 0, "length": 0x001FCF00},
        "rram_scratch": {"origin": 0x001FCF00, "length": 0x100, "write_unit": 16},
        "ram": {"origin": 0x20000000, "length": 0x00040000},
        "configuration_regions_allowed": False,
    }
    if layout == standalone_layout:
        allowlist = STANDALONE_RRAM_ALLOWLIST
    else:
        allowlist = _validated_custom_allowlist(layout, target)

    elf_image = parse_elf(elf)
    hex_image = parse_ihex(ihex)
    require_allowed(elf_image.ranges, tuple(tuple(item) for item in allowlist))
    require_allowed(hex_image.ranges, tuple(tuple(item) for item in allowlist))
    if _merged(elf_image.ranges) != _merged(hex_image.ranges):
        raise SdkContractError("SDK ELF and HEX load ranges do not match")
    if elf_image.entry is None or not any(
        start <= elf_image.entry < end for start, end in elf_image.ranges
    ):
        raise SdkContractError("SDK ELF entry is outside its load image")
    source_lock = project / "docs/provenance/sources.lock"
    images = [{
        "domain": target,
        "order": 0,
        "path": str(ihex),
        "sha256": sha256(ihex),
        "ranges": hex_image.ranges,
        "allowlist": allowlist,
    }]
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
        "image_layout": {
            "path": str(layout_path),
            "sha256": sha256(layout_path),
        },
        "debug_allowlist": allowlist,
        "debug_elf": {
            "path": str(elf),
            "sha256": sha256(elf),
            "entry": elf_image.entry,
            "ranges": elf_image.ranges,
        },
        "images": images,
    }
    if hci_h4_hwfc_1m:
        map_path = build_dir / f"{target}.map"
        contract_path = project / "docs/provenance/m6-sdc-mpsl-contract.json"
        try:
            link_map = map_path.read_text(encoding="utf-8")
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SdkContractError(f"invalid SDC build evidence: {error}") from error
        # Audit the actual link result, not a configure-time capability report.
        variants = set(re.findall(
            r"libsoftdevice_controller_(multirole|peripheral|central)\.a\(", link_map,
        ))
        if len(variants) != 1:
            raise SdkContractError("SDC link map must contain exactly one Controller variant")
        variant = variants.pop()
        required_archives = {
            "libmpsl.a", "libmpsl_fem_common.a",
            f"libsoftdevice_controller_{variant}.a",
        }
        if not all(f"{name}(" in link_map for name in required_archives):
            raise SdkContractError("SDC build evidence does not match the locked link contract")
        if (
            contract.get("schema") != "nrfkit-m6-sdc-mpsl-contract/v1"
            or contract.get("source", {}).get("security_domain") != "secure"
            or contract.get("source", {}).get("float_abi") != "hard-float"
        ):
            raise SdkContractError("SDC provenance has an invalid binary contract")
        resources = contract.get("lm20_resources", {})
        owned_resources = []
        for group in (
            "mpsl_interrupt_peripherals", "mpsl_non_interrupt_peripherals",
            "sdc_owned_peripherals",
        ):
            entries = resources.get(group)
            if not isinstance(entries, list) or not entries or any(
                not isinstance(entry, str) or not entry for entry in entries
            ):
                raise SdkContractError("SDC provenance has an invalid resource contract")
            owned_resources.extend(entries)
        timeslot = re.search(r"\bnrfkit_timeslot_open\s*$", link_map, re.MULTILINE) is not None
        manifest["hci_transport"] = {
            "type": "H4", "baud": 1000000, "hardware_flow_control": True,
        }
        manifest["build_evidence"] = {
            "status": "ok", "variant": variant,
            "timeslot": timeslot,
            "security_domain": "secure", "float_abi": "hard-float",
            "archives": sorted(required_archives),
            "resources": sorted(owned_resources),
            "resource_contract_sha256": sha256(contract_path),
            "map_sha256": sha256(map_path),
            "elf_budget": _elf_load_budget(
                elf,
                ram_origin=layout["ram"]["origin"],
                ram_length=layout["ram"]["length"],
                rram_origin=layout["rram"]["origin"],
                rram_length=layout["rram"]["length"],
            ),
        }
    output = build_dir / f"{target}.device-manifest.json"
    atomic_json(output, manifest)
    return output
