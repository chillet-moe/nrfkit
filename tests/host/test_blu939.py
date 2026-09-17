# SPDX-License-Identifier: BSD-3-Clause

from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory
import struct
import unittest
from unittest.mock import MagicMock, patch

from nrfkit_tools.blu939 import (
    Blu939,
    Blu939Error,
    Decoder,
    decode_capture,
    parse_metadata,
)
from nrfkit_tools.blu939_cli import command


def metadata_bytes() -> bytes:
    lines = ["Calibrated: 0", "VDD: 3000"]
    lines.extend(f"R{index}: {1000 / (10 ** index)}" for index in range(6))
    lines.extend(f"O{index}: {index}" for index in range(6))
    return ("\n".join(lines) + "\nEND\n").encode("ascii")


class Blu939Tests(unittest.TestCase):
    def test_metadata_requires_complete_finite_calibration(self) -> None:
        metadata = parse_metadata(metadata_bytes())
        self.assertEqual(metadata["vdd"], 3000)
        self.assertEqual(metadata["r0"], 1000)
        for malformed in (
            b"VDD: 3000\n",
            metadata_bytes().replace(b"R0: 1000.0", b"R0: nan"),
            metadata_bytes().replace(b"END\n", b"R0: 2\nEND\n"),
        ):
            with self.assertRaises(Blu939Error):
                parse_metadata(malformed)

    def test_voltage_command_is_big_endian_and_read_back(self) -> None:
        instrument = object.__new__(Blu939)
        instrument.command = MagicMock()
        metadata = parse_metadata(metadata_bytes())
        instrument.metadata = MagicMock(return_value=metadata)
        with patch("nrfkit_tools.blu939.time.sleep"):
            self.assertEqual(instrument.configure_voltage(3000)["vdd"], 3000)
        instrument.command.assert_called_once_with(b"\x0d\x0b\xb8")

    def test_decoder_uses_six_ranges_and_preserves_unfiltered_samples(self) -> None:
        metadata = parse_metadata(metadata_bytes())
        decoder = Decoder(metadata, 3000)
        expected = (400 - metadata["o0"]) * (1.8 / 163840) / metadata["r0"]
        self.assertAlmostEqual(decoder.sample(100), expected)
        decoder.sample((7 << 14) | 100)
        self.assertEqual(decoder.range_counts[5], 1)
        self.assertEqual(decoder.saturated_range_samples, 1)

    def test_capture_decoder_emits_m7_normalized_csv(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / "samples.bin"
            raw.write_bytes(b"".join(struct.pack("<I", value) for value in (100, 101, 102)))
            summary = decode_capture(
                raw, root / "current.csv", parse_metadata(metadata_bytes()), 3000
            )
            self.assertEqual(summary["sample_count"], 3)
            self.assertAlmostEqual(summary["duration_s"], 20e-6)
            self.assertIn("time_s,current_a", (root / "current.csv").read_text())
            self.assertEqual(summary["filter"], "none; range-switch transients retained")
            self.assertEqual(summary["calibration_metadata_flag"], 0)
            self.assertIn("not interpreted", summary["calibration_status"])

    def test_power_failure_requests_output_off_before_close(self) -> None:
        with TemporaryDirectory() as temporary:
            report = {}
            instrument = MagicMock()
            instrument.metadata.return_value = parse_metadata(metadata_bytes())
            instrument.configure_voltage.return_value = parse_metadata(metadata_bytes())
            args = Namespace(
                blu939_action="power",
                instrument_serial=None,
                voltage_mv=3000,
                duration=60,
                state="on",
            )
            with patch(
                "nrfkit_tools.cli._new_run",
                return_value=(Path(temporary), report),
            ), patch("nrfkit_tools.blu939_cli.discover", return_value=[]), patch(
                "nrfkit_tools.blu939_cli.select",
                return_value={"serial": "test", "port": "unused"},
            ), patch(
                "nrfkit_tools.blu939_cli.Blu939", return_value=instrument
            ), patch(
                "nrfkit_tools.blu939_cli.time.sleep",
                side_effect=Blu939Error("interrupted"),
            ):
                with self.assertRaisesRegex(Blu939Error, "interrupted"):
                    command(args)
            self.assertEqual(instrument.power.call_args.args, (False,))
            instrument.close.assert_called_once()
            self.assertEqual(report["cleanup_output_requested"], "off")


if __name__ == "__main__":
    unittest.main()
