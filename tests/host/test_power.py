# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nrfkit_tools.cli import ToolError
from nrfkit_tools.power import PowerCaptureError, summarize_capture
from nrfkit_tools.power_cli import command


class PowerCaptureTests(unittest.TestCase):
    def capture(self, contents: str) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "capture.csv"
        path.write_text(contents, encoding="utf-8")
        return path

    def test_integrates_normalized_current_capture(self) -> None:
        summary = summarize_capture(
            self.capture(
                "time_s,current_a\n"
                "0.000000,0.001\n"
                "0.000001,0.003\n"
                "0.000002,0.003\n"
                "0.000003,0.001\n"
            ),
            supply_voltage_v=1.8,
            minimum_duration_s=0.000003,
            maximum_sample_gap_s=0.0000011,
        )
        self.assertEqual(summary["sample_count"], 4)
        self.assertAlmostEqual(summary["average_current_a"], 7.0 / 3000.0)
        self.assertAlmostEqual(summary["minimum_current_a"], 0.001)
        self.assertEqual(summary["negative_samples"], 0)
        self.assertAlmostEqual(summary["charge_c"], 7e-9)
        self.assertAlmostEqual(summary["energy_j"], 12.6e-9)

    def test_rejects_sparse_or_non_monotonic_capture(self) -> None:
        with self.assertRaisesRegex(PowerCaptureError, "sample gap"):
            summarize_capture(
                self.capture("time_s,current_a\n0,0.001\n0.01,0.001\n"),
                supply_voltage_v=1.8,
                minimum_duration_s=0.001,
                maximum_sample_gap_s=0.000005,
            )
        with self.assertRaisesRegex(PowerCaptureError, "strictly increase"):
            summarize_capture(
                self.capture("time_s,current_a\n1,0.001\n1,0.001\n"),
                supply_voltage_v=1.8,
                minimum_duration_s=0.001,
                maximum_sample_gap_s=0.01,
            )

    def test_rejects_unexpected_schema(self) -> None:
        with self.assertRaisesRegex(PowerCaptureError, "exactly"):
            summarize_capture(
                self.capture("seconds,amps\n0,0\n1,0\n"),
                supply_voltage_v=1.8,
                minimum_duration_s=1.0,
                maximum_sample_gap_s=1.0,
            )

    def test_m7_reducer_remains_available_from_split_cli_module(self) -> None:
        capture = self.capture(
            "time_s,current_a\n0,0.001\n0.00001,0.002\n0.00002,0.001\n"
        )
        profiles = (
            "idle", "direct-1m", "direct-2m", "direct-4m",
            "timeslot-retry-4m", "ble", "ble-timeslot-4m",
        )
        args = Namespace(
            capture=[f"{profile}={capture}" for profile in profiles],
            instrument="test",
            supply_voltage_v=3.0,
            minimum_duration=0.00002,
            maximum_sample_gap_us=10.1,
        )
        with tempfile.TemporaryDirectory() as temporary:
            report = {}
            with patch(
                "nrfkit_tools.cli._new_run",
                return_value=(Path(temporary), report),
            ):
                self.assertEqual(command(args), 0)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(set(report["captures"]), set(profiles))

        args.capture.pop()
        with self.assertRaisesRegex(ToolError, "missing"):
            command(args)

    def test_preserves_signed_near_zero_samples(self) -> None:
        summary = summarize_capture(
            self.capture(
                "time_s,current_a\n"
                "0,-0.000001\n"
                "1,0.000003\n"
                "2,-0.000001\n"
            ),
            supply_voltage_v=3.0,
            minimum_duration_s=2.0,
            maximum_sample_gap_s=1.0,
        )
        self.assertEqual(summary["negative_samples"], 2)
        self.assertAlmostEqual(summary["minimum_current_a"], -0.000001)
        self.assertAlmostEqual(summary["average_current_a"], 0.000001)
        self.assertAlmostEqual(summary["charge_c"], 0.000002)


if __name__ == "__main__":
    unittest.main()
