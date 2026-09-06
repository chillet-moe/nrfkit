# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct
from typing import Any

from .device import safe_backend_contract
from .image import parse_elf, parse_elf_absolute_symbols, parse_ihex, require_allowed
from .process import atomic_json


class SdkContractError(RuntimeError):
    pass


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


def elf_layout_symbols(elf: Path) -> dict[str, int]:
    return parse_elf_absolute_symbols(
        elf,
        ("__nrfkit_rram_start", "__nrfkit_rram_end",
         "__nrfkit_ram_start", "__nrfkit_ram_end"),
        optional=("__nrfkit_settings_start", "__nrfkit_settings_end",
                  "__nrfkit_rram_scratch_start", "__nrfkit_rram_scratch_end"),
    )


def _layout_from_symbols(symbols: dict[str, int]) -> dict[str, dict[str, int]]:
    layout: dict[str, dict[str, int]] = {}
    for name, low, high in (
        ("rram", 0, LM20_SAFE_RRAM_END),
        ("ram", LM20_RAM0_ORIGIN, LM20_RAM0_END),
        ("settings", 0, LM20_SAFE_RRAM_END),
        ("rram_scratch", 0, LM20_SAFE_RRAM_END),
    ):
        start = symbols.get(f"__nrfkit_{name}_start")
        end = symbols.get(f"__nrfkit_{name}_end")
        if name in ("settings", "rram_scratch") and start is None and end is None:
            continue
        if start is None or end is None:
            raise SdkContractError(f"ELF layout {name} requires both boundary symbols")
        if not low <= start < end <= high:
            raise SdkContractError(f"ELF layout {name} range is unsafe")
        layout[name] = {"origin": start, "length": end - start}
    regions = [(name, region["origin"], region["origin"] + region["length"])
               for name, region in layout.items() if name != "ram"]
    for index, (first_name, start, end) in enumerate(regions):
        for second_name, second_start, second_end in regions[index + 1:]:
            if start < second_end and second_start < end:
                raise SdkContractError(f"ELF layout regions overlap: {first_name} and {second_name}")
    return layout


def read_elf_layout(elf: Path) -> dict[str, dict[str, int]]:
    return _layout_from_symbols(elf_layout_symbols(elf))


def create_device_manifest(
    project: Path,
    build_dir: Path,
    target: str,
    expected_token: str,
    hci_h4_hwfc_1m: bool = False,
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
    for path in (elf, ihex):
        if not path.is_file():
            raise SdkContractError(f"SDK artifact is missing: {path}")
    elf_image = parse_elf(elf)
    symbols = elf_layout_symbols(elf)
    layout = _layout_from_symbols(symbols)
    # RAM bounds describe execution, never a programming or debug-write allowance.
    allowlist = [[layout["rram"]["origin"],
                  layout["rram"]["origin"] + layout["rram"]["length"]]]
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
            "source": "elf-symbols",
            "path": str(elf),
            "sha256": sha256(elf),
            "symbols": symbols,
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
