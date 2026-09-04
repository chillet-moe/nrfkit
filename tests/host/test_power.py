# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from nrfkit_tools.power import PowerCaptureError, summarize_capture


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

    def test_rejects_unexpected_schema_and_negative_current(self) -> None:
        with self.assertRaisesRegex(PowerCaptureError, "exactly"):
            summarize_capture(
                self.capture("seconds,amps\n0,0\n1,0\n"),
                supply_voltage_v=1.8,
                minimum_duration_s=1.0,
                maximum_sample_gap_s=1.0,
            )
        with self.assertRaisesRegex(PowerCaptureError, "invalid value"):
            summarize_capture(
                self.capture("time_s,current_a\n0,-0.1\n1,0\n"),
                supply_voltage_v=1.8,
                minimum_duration_s=1.0,
                maximum_sample_gap_s=1.0,
            )


if __name__ == "__main__":
    unittest.main()
