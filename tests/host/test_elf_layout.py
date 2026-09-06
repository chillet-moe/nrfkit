# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from nrfkit_tools.cli import ToolError, load_manifest
from nrfkit_tools.image import ImageContractError, parse_elf_absolute_symbols
from nrfkit_tools.sdk import (
    SdkContractError,
    _layout_from_symbols,
    create_device_manifest,
    read_elf_layout,
    sha256,
)


ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"


class ElfLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cmake = shutil.which("cmake")
        cls.ninja = shutil.which("ninja") or shutil.which("ninja-build")
        configured = os.environ.get("NRF_LLVM_ROOT")
        clang = shutil.which("clang")
        cls.llvm_root = Path(configured) if configured else (
            Path(clang).resolve().parent.parent if clang else None
        )
        if not cls.cmake or not cls.ninja or cls.llvm_root is None:
            raise unittest.SkipTest("CMake, Ninja, and LLVM are required")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.build = Path(cls.tmp.name) / "build"
        result = subprocess.run([
            cls.cmake, "-S", str(EXAMPLES), "-B", str(cls.build), "-G", "Ninja",
            f"-DNrfKit_DIR={ROOT / 'cmake'}",
            f"-DCMAKE_TOOLCHAIN_FILE={ROOT / 'cmake/toolchains/arm-clang.cmake'}",
            f"-DNRF_LLVM_ROOT={cls.llvm_root}",
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(result.stdout)
        result = subprocess.run([
            cls.cmake, "--build", str(cls.build), "--target", "empty",
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(result.stdout)
        cls.elf = cls.build / "empty.elf"
        cls.hex = cls.build / "empty.hex"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    @staticmethod
    def _symbol_entry(data: bytearray, wanted: str) -> tuple[int, int]:
        header = struct.Struct("<16sHHIIIIIHHHHHH")
        section = struct.Struct("<IIIIIIIIII")
        symbol = struct.Struct("<IIIBBH")
        fields = header.unpack_from(data)
        section_offset, section_size, section_count = fields[6], fields[11], fields[12]
        sections = [section.unpack_from(data, section_offset + i * section_size)
                    for i in range(section_count)]
        for item in sections:
            if item[1] != 2:
                continue
            string_section = sections[item[6]]
            strings = data[string_section[4]:string_section[4] + string_section[5]]
            for offset in range(item[4], item[4] + item[5], symbol.size):
                name_offset = struct.unpack_from("<I", data, offset)[0]
                end = strings.find(b"\0", name_offset)
                if strings[name_offset:end].decode() == wanted:
                    return offset, name_offset
        raise AssertionError(f"missing fixture symbol {wanted}")

    def _copy_mutated(self, name: str, mutate) -> Path:
        path = Path(self.tmp.name) / name
        data = bytearray(self.elf.read_bytes())
        mutate(data)
        path.write_bytes(data)
        return path

    def test_read_layout_requires_and_returns_linker_symbols(self) -> None:
        layout = read_elf_layout(self.elf)
        self.assertEqual(layout["rram"], {"origin": 0, "length": 0x1FCF00})
        self.assertEqual(layout["ram"], {"origin": 0x20000000, "length": 0x40000})

    def test_missing_nonabsolute_and_invalid_ranges_are_rejected(self) -> None:
        names = ("__nrfkit_rram_start", "__nrfkit_rram_end")
        missing = self._copy_mutated("missing.elf", lambda data: (
            struct.pack_into("<I", data, self._symbol_entry(data, names[0])[0], 0),
        ))
        with self.assertRaisesRegex(ImageContractError, "missing absolute symbols"):
            parse_elf_absolute_symbols(missing, names)

        nonabsolute = self._copy_mutated("nonabsolute.elf", lambda data: (
            struct.pack_into("<H", data, self._symbol_entry(data, names[0])[0] + 14, 1),
        ))
        with self.assertRaisesRegex(ImageContractError, "global and absolute"):
            parse_elf_absolute_symbols(nonabsolute, names)

        invalid = self._copy_mutated("invalid-range.elf", lambda data: (
            struct.pack_into("<I", data, self._symbol_entry(data, names[0])[0] + 4, 0x1FCF00),
        ))
        with self.assertRaisesRegex(SdkContractError, "range is unsafe"):
            read_elf_layout(invalid)

    def test_duplicate_symbol_and_corrupt_symbol_table_are_rejected(self) -> None:
        target_offset, target_name = self._symbol_entry(
            bytearray(self.elf.read_bytes()), "__nrfkit_rram_start"
        )
        def duplicate_symbol(data: bytearray) -> None:
            header = struct.Struct("<16sHHIIIIIHHHHHH")
            section = struct.Struct("<IIIIIIIIII")
            symbol = struct.Struct("<IIIBBH")
            fields = header.unpack_from(data)
            for index in range(fields[12]):
                section_offset = fields[6] + index * fields[11]
                values = section.unpack_from(data, section_offset)
                if values[1] != 2:
                    continue
                for offset in range(values[4], values[4] + values[5], symbol.size):
                    if offset == target_offset:
                        continue
                    struct.pack_into("<I", data, offset, target_name)
                    struct.pack_into("<B", data, offset + 12, 0x10)
                    struct.pack_into("<H", data, offset + 14, 0xFFF1)
                    return
            raise AssertionError("missing duplicate symbol slot")

        duplicate = self._copy_mutated("duplicate.elf", duplicate_symbol)
        with self.assertRaisesRegex(ImageContractError, "duplicated"):
            parse_elf_absolute_symbols(duplicate, ("__nrfkit_rram_start",))

        def corrupt(data: bytearray) -> None:
            header = struct.Struct("<16sHHIIIIIHHHHHH")
            section = struct.Struct("<IIIIIIIIII")
            fields = header.unpack_from(data)
            for index in range(fields[12]):
                offset = fields[6] + index * fields[11]
                if struct.unpack_from("<I", data, offset + 4)[0] == 2:
                    struct.pack_into("<I", data, offset + 36, 0)
                    return
            raise AssertionError("missing symbol table")

        corrupt_table = self._copy_mutated("bad-table.elf", corrupt)
        with self.assertRaisesRegex(ImageContractError, "symbol table is invalid"):
            parse_elf_absolute_symbols(corrupt_table, ("__nrfkit_rram_start",))

    def test_manifest_layout_evidence_and_allowlist_become_stale(self) -> None:
        output = create_device_manifest(ROOT, self.build, "empty", "layout-test")
        manifest = load_manifest(output)
        self.assertEqual(manifest["image_layout"]["source"], "elf-symbols")
        stale = Path(self.tmp.name) / "stale.json"
        for field in ("debug", "image", "symbols", "hash"):
            with self.subTest(field=field):
                changed = json.loads(json.dumps(manifest))
                if field == "debug":
                    changed["debug_allowlist"] = [[0, 0x1FD000]]
                elif field == "image":
                    changed["images"][0]["allowlist"] = [[0, 0x1FD000]]
                elif field == "symbols":
                    changed["image_layout"]["symbols"]["__nrfkit_rram_end"] += 4
                else:
                    changed["image_layout"]["sha256"] = "0" * 64
                stale.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaises(ToolError):
                    load_manifest(stale, artifacts=False)

        changed_elf = self._copy_mutated(
            "changed.elf",
            lambda data: struct.pack_into(
                "<I", data, self._symbol_entry(data, "__nrfkit_rram_end")[0] + 4,
                0x1FCEFC,
            ),
        )
        changed = json.loads(json.dumps(manifest))
        for artifact in ("image_layout", "debug_elf"):
            changed[artifact]["path"] = str(changed_elf)
            changed[artifact]["sha256"] = sha256(changed_elf)
        stale.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaisesRegex(ToolError, "ELF layout evidence is invalid or stale"):
            load_manifest(stale, artifacts=False)

    def test_existing_restore_manifest_keeps_its_layout_receipt(self) -> None:
        output = create_device_manifest(ROOT, self.build, "empty", "restore-test")
        manifest = load_manifest(output)
        receipt = Path(self.tmp.name) / "old-layout.json"
        receipt.write_text('{"schema": "nrfkit-image-layout/v1"}', encoding="utf-8")
        manifest["image_layout"] = {"path": str(receipt), "sha256": sha256(receipt)}
        restore = Path(self.tmp.name) / "restore.json"
        restore.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertEqual(load_manifest(restore)["debug_allowlist"], [[0, 0x1FCF00]])
        receipt.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ToolError, "layout receipt is missing or stale"):
            load_manifest(restore)

    def test_manifest_rejects_overlapping_regions_from_actual_elf(self) -> None:
        build = Path(self.tmp.name) / "overlap"
        build.mkdir()
        elf = self._copy_mutated(
            "overlap.elf",
            lambda data: struct.pack_into(
                "<I", data,
                self._symbol_entry(data, "__nrfkit_rram_scratch_start")[0] + 4,
                0x001FC800,
            ),
        )
        shutil.copy2(elf, build / "overlap.elf")
        shutil.copy2(self.hex, build / "overlap.hex")
        with self.assertRaisesRegex(SdkContractError, "regions overlap"):
            create_device_manifest(ROOT, build, "overlap", "OVERLAP")

    def test_manifest_rejects_forbidden_hex_ranges(self) -> None:
        build = Path(self.tmp.name) / "forbidden"
        build.mkdir()
        shutil.copy2(self.elf, build / "bad.elf")
        def record(address: int, data: bytes, kind: int = 0) -> str:
            body = bytes((len(data), address >> 8, address & 0xff, kind)) + data
            checksum = (-sum(body)) & 0xff
            return ":" + (body + bytes((checksum,))).hex().upper()
        (build / "bad.hex").write_text(
            record(0, bytes((0x00, 0xFF)), 4) + "\n" +
            record(0xD000, bytes(4)) +
            "\n:00000001FF\n", encoding="ascii"
        )
        with self.assertRaisesRegex(ImageContractError, "forbidden UICR"):
            create_device_manifest(ROOT, build, "bad", "forbidden")

    def test_optional_layout_regions_must_be_complete_and_disjoint(self) -> None:
        symbols = {
            "__nrfkit_rram_start": 0,
            "__nrfkit_rram_end": 0x1000,
            "__nrfkit_ram_start": 0x20000000,
            "__nrfkit_ram_end": 0x20040000,
            "__nrfkit_settings_start": 0x800,
        }
        with self.assertRaisesRegex(SdkContractError, "requires both boundary symbols"):
            _layout_from_symbols(symbols)
        symbols["__nrfkit_settings_end"] = 0x1800
        with self.assertRaisesRegex(SdkContractError, "regions overlap"):
            _layout_from_symbols(symbols)
