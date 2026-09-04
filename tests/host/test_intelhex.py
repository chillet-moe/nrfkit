# SPDX-License-Identifier: BSD-3-Clause

import tempfile
import struct
import unittest
from pathlib import Path

from nrfkit_tools.image import ImageContractError, parse_elf, parse_ihex, require_allowed


def record(address: int, kind: int, payload: bytes) -> str:
    body = bytes((len(payload), address >> 8, address & 0xFF, kind)) + payload
    checksum = (-sum(body)) & 0xFF
    return ":" + (body + bytes((checksum,))).hex().upper()


class IntelHexTests(unittest.TestCase):
    def write_hex(self, lines: list[str]) -> Path:
        temporary = tempfile.NamedTemporaryFile("w", suffix=".hex", delete=False)
        with temporary:
            temporary.write("\n".join(lines) + "\n")
        self.addCleanup(Path(temporary.name).unlink)
        return Path(temporary.name)

    def test_extended_linear_address_and_contiguous_ranges(self) -> None:
        path = self.write_hex([
            record(0, 4, bytes.fromhex("0001")),
            record(0x20, 0, b"abcd"),
            record(0x24, 0, b"ef"),
            record(0, 1, b""),
        ])
        image = parse_ihex(path)
        self.assertEqual(image.ranges, ((0x10020, 0x10026),))

    def test_bad_checksum_is_rejected(self) -> None:
        path = self.write_hex([":00000001FE"])
        with self.assertRaisesRegex(ImageContractError, "checksum"):
            parse_ihex(path)

    def hex_at(self, address: int) -> Path:
        return self.write_hex([
            record(0, 4, (address >> 16).to_bytes(2, "big")),
            record(address & 0xFFFF, 0, bytes(4)),
            record(0, 1, b""),
        ])

    def test_named_forbidden_regions_win_over_manifest_allowlist(self) -> None:
        cases = (
            (0x00FFD000, "UICR"),
            (0x00FFE000, "SICR"),
            (0x00FFD500, "OTP"),
            (0x50049000, "KMU"),
            (0x00FFD080, "BOOTCONF"),
        )
        for address, label in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ImageContractError, f"forbidden {label}"):
                    require_allowed(
                        parse_ihex(self.hex_at(address)).ranges,
                        ((0, 0x1_0000_0000),),
                    )

    def test_outside_allowlist_is_rejected(self) -> None:
        path = self.write_hex([record(0x1000, 0, b"abcd"), record(0, 1, b"")])
        with self.assertRaisesRegex(ImageContractError, "allowlist"):
            require_allowed(parse_ihex(path).ranges, ((0, 0x1000),))

    def test_out_of_range_rram_record_is_rejected(self) -> None:
        path = self.hex_at(0x00200000)
        with self.assertRaisesRegex(ImageContractError, "outside the manifest allowlist"):
            require_allowed(parse_ihex(path).ranges, ((0, 0x001F4000),))

    def test_elf_entry_and_file_backed_load_range_are_parsed(self) -> None:
        ident = b"\x7fELF" + bytes((1, 1, 1)) + bytes(9)
        header = struct.pack(
            "<16sHHIIIIIHHHHHH",
            ident, 2, 40, 1, 0x1001, 52, 0, 0, 52, 32, 1, 0, 0, 0,
        )
        program = struct.pack("<IIIIIIII", 1, 84, 0x2000, 0x1000, 4, 4, 5, 4)
        with tempfile.NamedTemporaryFile("wb", suffix=".elf", delete=False) as temporary:
            temporary.write(header + program + b"code")
        path = Path(temporary.name)
        self.addCleanup(path.unlink)
        image = parse_elf(path)
        self.assertEqual(image.entry, 0x1001)
        self.assertEqual(image.ranges, ((0x1000, 0x1004),))


if __name__ == "__main__":
    unittest.main()
