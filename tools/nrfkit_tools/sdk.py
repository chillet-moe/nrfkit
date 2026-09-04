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
S115_APP_RRAM_ALLOWLIST = [[0x00000000, 0x001E1800]]
S115_RRAM_ALLOWLIST = [[0x001E3800, 0x001FCC00]]
S115_HEX_SHA256 = "c2b5bcf2b436e11daa9a85e9dca12060052244c2eec50032bf54d87a4a77c3a2"


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
    elf: Path, *, ram_origin: int, ram_length: int, rram_length: int,
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
        if physical < rram_length:
            if physical + file_size > rram_length:
                raise SdkContractError("SDC ELF LOAD segment exceeds RRAM")
            rram_file += file_size
    return {
        "ram_allocated_bytes": ram_allocated,
        "ram_initialized_bytes": ram_initialized,
        "ram_capacity_bytes": ram_length,
        "rram_file_bytes": rram_file,
    }


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
    layout_path = build_dir / f"{target}.image-layout.json"
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
    s115_layout = {
        "schema": "nrfkit-image-layout/v1",
        "target": target,
        "soc": "nrf54lm20a",
        "core": "cpuapp",
        "rram": {"origin": 0, "length": 0x001E1800},
        "settings": {"origin": 0x001E1800, "length": 0x2000},
        "softdevice": {
            "name": "s115", "version": "10.0.1",
            "origin": 0x001E3800, "length": 0x19400,
        },
        "ram": {"origin": 0x20002128, "length": 0x0003DED8},
        "configuration_regions_allowed": False,
    }
    if layout not in (standalone_layout, s115_layout):
        raise SdkContractError("SDK layout manifest does not match the guarded LM20 contract")

    elf_image = parse_elf(elf)
    hex_image = parse_ihex(ihex)
    allowlist = S115_APP_RRAM_ALLOWLIST if layout == s115_layout else STANDALONE_RRAM_ALLOWLIST
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
    if layout == s115_layout:
        # The absolute official input is recorded only in the generated, ignored build tree.
        input_path = build_dir / f"{target}.softdevice-input.json"
        try:
            softdevice_input = json.loads(input_path.read_text(encoding="utf-8"))
            softdevice_hex = Path(softdevice_input["hex"])
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise SdkContractError("S115 build does not record its target input") from error
        if softdevice_input != {
            "schema": "nrfkit-softdevice-input/v1",
            "name": "s115",
            "version": "10.0.1",
            "hex": str(softdevice_hex),
        }:
            raise SdkContractError("S115 target input metadata is invalid")
        if not softdevice_hex.is_file() or sha256(softdevice_hex) != S115_HEX_SHA256:
            raise SdkContractError("S115 10.0.1 HEX is missing or stale")
        softdevice_image = parse_ihex(softdevice_hex)
        require_allowed(
            softdevice_image.ranges,
            tuple(tuple(item) for item in S115_RRAM_ALLOWLIST),
        )
        images.append({
            "domain": "s115-10.0.1",
            "order": 1,
            "path": str(softdevice_hex.resolve()),
            "sha256": S115_HEX_SHA256,
            "ranges": softdevice_image.ranges,
            "allowlist": S115_RRAM_ALLOWLIST,
        })

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
        "images": images,
    }
    if hci_h4_hwfc_1m:
        sdc_target_path = build_dir / "nrfkit" / target / "sdc-target.json"
        map_path = build_dir / f"{target}.map"
        try:
            sdc_target = json.loads(sdc_target_path.read_text(encoding="utf-8"))
            link_map = map_path.read_text(encoding="utf-8")
        except (OSError, json.JSONDecodeError) as error:
            raise SdkContractError(f"invalid SDC build evidence: {error}") from error
        variant = sdc_target.get("variant")
        required_archives = {
            "libmpsl.a", "libmpsl_fem_common.a",
            f"libsoftdevice_controller_{variant}.a",
        }
        archive_names = {Path(value).name for value in sdc_target.get("archives", [])}
        resources = sdc_target.get("resources")
        if (
            sdc_target.get("schema") != "nrfkit-sdc-target/v1"
            or sdc_target.get("target") != target
            or variant not in {"multirole", "peripheral", "central"}
            or sdc_target.get("security_domain") != "secure"
            or sdc_target.get("float_abi") != "hard-float"
            or archive_names != required_archives
            or not isinstance(resources, list)
            or not resources
            or any(not isinstance(resource, str) for resource in resources)
            or not all(name in link_map for name in required_archives)
        ):
            raise SdkContractError("SDC build evidence does not match the locked link contract")
        manifest["hci_transport"] = {
            "type": "H4", "baud": 1000000, "hardware_flow_control": True,
        }
        manifest["build_evidence"] = {
            "status": "ok", "variant": variant,
            "security_domain": "secure", "float_abi": "hard-float",
            "archives": sorted(required_archives),
            "resources": sorted(resources),
            "map_sha256": sha256(map_path),
            "elf_budget": _elf_load_budget(
                elf,
                ram_origin=layout["ram"]["origin"],
                ram_length=layout["ram"]["length"],
                rram_length=layout["rram"]["length"],
            ),
        }
    output = build_dir / f"{target}.device-manifest.json"
    atomic_json(output, manifest)
    return output
