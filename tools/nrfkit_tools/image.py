# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
from typing import Iterable


FORBIDDEN_RANGES = (
    # nRF54LM20A MDK/SVD: BOOTCONF and OTP are write-once UICR subregions.
    # Keep them before the enclosing UICR range so diagnostics stay specific.
    (0x00FFD080, 0x00FFD084, "BOOTCONF"),
    (0x00FFD500, 0x00FFDA00, "OTP"),
    (0x00FFD000, 0x00FFE000, "UICR"),
    (0x00FFE000, 0x00FFF000, "SICR"),
    (0x50049000, 0x5004A000, "KMU"),
    (0x00FF8000, 0x00FFD000, "factory information"),
    (0x00FFF000, 0x01000000, "reserved configuration"),
    (0x0FF00000, 0x10000000, "configuration alias"),
)


class ImageContractError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedImage:
    path: Path
    ranges: tuple[tuple[int, int], ...]
    entry: int | None = None


def parse_elf_absolute_symbols(
    path: Path, names: Iterable[str], *, optional: Iterable[str] = (),
) -> dict[str, int]:
    """Read linker-owned absolute symbols from a little-endian ARM ELF32."""
    required = set(names)
    wanted = required | set(optional)
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ImageContractError(f"cannot read ELF {path}: {error}") from error
    header = struct.Struct("<16sHHIIIIIHHHHHH")
    section = struct.Struct("<IIIIIIIIII")
    symbol = struct.Struct("<IIIBBH")
    if len(data) < header.size or data[:7] != b"\x7fELF\x01\x01\x01":
        raise ImageContractError("layout requires a little-endian ELF32 image")
    fields = header.unpack_from(data)
    if fields[1] != 2 or fields[2] != 40 or fields[3] != 1:
        raise ImageContractError("layout requires an ARM executable ELF")
    offset, entry_size, count = fields[6], fields[11], fields[12]
    if (fields[8] != header.size or entry_size != section.size or not count
            or offset < header.size or offset + count * entry_size > len(data)):
        raise ImageContractError("ELF section header table is invalid")
    sections = [section.unpack_from(data, offset + i * entry_size) for i in range(count)]
    found: dict[str, int] = {}
    for section_header in sections:
        if section_header[1] != 2:  # SHT_SYMTAB: the static linker's symbol table.
            continue
        symbol_offset, symbol_size, string_table = section_header[4:7]
        if (string_table >= count or section_header[9] != symbol.size
                or symbol_size % symbol.size or symbol_offset < header.size
                or symbol_offset + symbol_size > len(data)):
            raise ImageContractError("ELF symbol table is invalid")
        string_header = sections[string_table]
        string_offset, string_size = string_header[4:6]
        if (string_header[1] != 3 or not string_size or string_offset < header.size
                or string_offset + string_size > len(data)):
            raise ImageContractError("ELF symbol string table is invalid")
        strings = data[string_offset:string_offset + string_size]
        for position in range(symbol_offset, symbol_offset + symbol_size, symbol.size):
            name_offset, value, unused_size, info, unused_other, section_index = (
                symbol.unpack_from(data, position)
            )
            if name_offset >= len(strings):
                raise ImageContractError("ELF symbol name offset is invalid")
            end = strings.find(b"\0", name_offset)
            if end < 0:
                raise ImageContractError("ELF symbol name is unterminated")
            try:
                name = strings[name_offset:end].decode("utf-8")
            except UnicodeDecodeError as error:
                raise ImageContractError("ELF symbol name is not UTF-8") from error
            if name not in wanted:
                continue
            if section_index != 0xFFF1 or info >> 4 != 1:
                raise ImageContractError(f"ELF symbol {name} must be global and absolute")
            if name in found:
                raise ImageContractError(f"ELF symbol {name} is duplicated")
            found[name] = value
    missing = sorted(required - found.keys())
    if missing:
        raise ImageContractError(f"ELF is missing absolute symbols: {', '.join(missing)}")
    return found


def _ranges(addresses: Iterable[int]) -> tuple[tuple[int, int], ...]:
    ordered = sorted(set(addresses))
    if not ordered:
        raise ImageContractError("image contains no data")
    result: list[tuple[int, int]] = []
    start = previous = ordered[0]
    for address in ordered[1:]:
        if address != previous + 1:
            result.append((start, previous + 1))
            start = address
        previous = address
    result.append((start, previous + 1))
    return tuple(result)


def parse_ihex(path: Path) -> ParsedImage:
    memory: dict[int, int] = {}
    base = 0
    eof = False
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as error:
        raise ImageContractError(f"cannot read Intel HEX {path}: {error}") from error
    for number, text in enumerate(lines, start=1):
        if not text.startswith(":"):
            raise ImageContractError(f"Intel HEX line {number} has no record marker")
        try:
            raw = bytes.fromhex(text[1:])
        except ValueError as error:
            raise ImageContractError(f"Intel HEX line {number} is not hexadecimal") from error
        if len(raw) < 5 or len(raw) != raw[0] + 5:
            raise ImageContractError(f"Intel HEX line {number} has an invalid length")
        if sum(raw) & 0xFF:
            raise ImageContractError(f"Intel HEX line {number} checksum is invalid")
        length, high, low, kind = raw[:4]
        offset = high << 8 | low
        payload = raw[4 : 4 + length]
        if eof:
            raise ImageContractError("Intel HEX contains records after EOF")
        if kind == 0:
            start = base + offset
            if start + length > 0x1_0000_0000:
                raise ImageContractError("Intel HEX data exceeds the 32-bit address space")
            for index, value in enumerate(payload):
                address = start + index
                previous = memory.setdefault(address, value)
                if previous != value:
                    raise ImageContractError(f"conflicting Intel HEX data at 0x{address:08x}")
        elif kind == 1:
            if length or offset:
                raise ImageContractError("Intel HEX EOF record is malformed")
            eof = True
        elif kind == 2:
            if length != 2 or offset:
                raise ImageContractError("Intel HEX segment address record is malformed")
            base = int.from_bytes(payload, "big") << 4
        elif kind == 4:
            if length != 2 or offset:
                raise ImageContractError("Intel HEX linear address record is malformed")
            base = int.from_bytes(payload, "big") << 16
        elif kind in (3, 5):
            if length != 4:
                raise ImageContractError("Intel HEX start address record is malformed")
        else:
            raise ImageContractError(f"unsupported Intel HEX record type {kind}")
    if not eof:
        raise ImageContractError("Intel HEX has no EOF record")
    return ParsedImage(path.resolve(), _ranges(memory))


def parse_elf(path: Path) -> ParsedImage:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ImageContractError(f"cannot read ELF {path}: {error}") from error
    if len(data) < 52 or data[:4] != b"\x7fELF":
        raise ImageContractError("input is not an ELF image")
    elf_class, encoding = data[4], data[5]
    if encoding != 1 or elf_class not in (1, 2):
        raise ImageContractError("ELF must be little-endian ELF32 or ELF64")
    if elf_class == 1:
        header = struct.Struct("<16sHHIIIIIHHHHHH")
        program = struct.Struct("<IIIIIIII")
        fields = header.unpack_from(data)
        if fields[2] != 40:
            raise ImageContractError("ELF machine is not ARM")
        entry, offset, entry_size, count = fields[4], fields[5], fields[9], fields[10]
    else:
        header = struct.Struct("<16sHHIQQQIHHHHHH")
        program = struct.Struct("<IIQQQQQQ")
        fields = header.unpack_from(data)
        if fields[2] != 40:
            raise ImageContractError("ELF machine is not ARM")
        entry, offset, entry_size, count = fields[4], fields[5], fields[9], fields[10]
    if entry_size != program.size or offset + count * entry_size > len(data):
        raise ImageContractError("ELF program header table is invalid")
    ranges: list[tuple[int, int]] = []
    for index in range(count):
        values = program.unpack_from(data, offset + index * entry_size)
        if values[0] != 1:
            continue
        if elf_class == 1:
            file_offset, physical, file_size = values[1], values[3], values[4]
        else:
            file_offset, physical, file_size = values[2], values[4], values[5]
        if not file_size:
            continue
        if file_offset + file_size > len(data) or physical + file_size > 0x1_0000_0000:
            raise ImageContractError("ELF LOAD range is invalid")
        ranges.append((physical, physical + file_size))
    if not ranges:
        raise ImageContractError("ELF has no file-backed LOAD segments")
    return ParsedImage(path.resolve(), tuple(sorted(ranges)), entry)


def require_allowed(
    ranges: Iterable[tuple[int, int]], allowlist: Iterable[tuple[int, int]]
) -> None:
    allowed = tuple(allowlist)
    for start, end in ranges:
        if start < 0 or end <= start or end > 0x1_0000_0000:
            raise ImageContractError("image contains an invalid load range")
        for forbidden_start, forbidden_end, label in FORBIDDEN_RANGES:
            if start < forbidden_end and end > forbidden_start:
                raise ImageContractError(
                    f"image range 0x{start:08x}..0x{end:08x} enters forbidden {label} region"
                )
        if not any(start >= allowed_start and end <= allowed_end for allowed_start, allowed_end in allowed):
            raise ImageContractError(
                f"image range 0x{start:08x}..0x{end:08x} is outside the manifest allowlist"
            )
