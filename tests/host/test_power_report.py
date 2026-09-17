# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from nrfkit_tools.power_report import _envelope, generate_report
from nrfkit_tools.power_report_cli import _latest_successful


class PowerReportTests(unittest.TestCase):
    def fixture(self, root: Path, *, status: str = "ok") -> Path:
        profile = root / "01-idle"
        profile.mkdir(parents=True)
        csv = profile / "current.csv"
        csv.write_text(
            "time_s,current_a\n"
            "0.0,0.000001\n0.1,0.000004\n0.2,-0.000002\n"
            "0.3,0.000003\n0.4,0.000001\n",
            encoding="utf-8",
        )
        raw = profile / "samples.bin"
        raw.write_bytes(b"raw capture")
        report = root / "run.json"
        report.write_text(json.dumps({
            "operation": "blu939-suite",
            "status": status,
            "started_at": "2026-09-18T00:00:00Z",
            "instrument": "BLU939",
            "supply_voltage_v": 3.0,
            "instrument_metadata": {"calibrated": 0},
            "cleanup": {
                "output_requested": "off", "restore_verified": True,
                "peer_restore_verified": True,
            },
            "profiles": [{
                "name": "idle", "csv": str(csv), "raw": str(raw),
                "csv_sha256": "c", "raw_sha256": "r", "observations": {},
                "measurement": {
                    "sample_count": 5, "duration_s": 0.4,
                    "average_current_a": 0.000001,
                    "peak_current_a": 0.000004,
                    "energy_j": 0.0000012, "negative_samples": 1,
                },
            }],
        }), encoding="utf-8")
        return report

    def test_envelope_preserves_minimum_maximum_and_mean(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = self.fixture(Path(temporary))
            csv = report.parent / "01-idle/current.csv"
            values = _envelope(csv, 5, 2)
        self.assertEqual(len(values), 2)
        self.assertEqual(values[0][1:3], [-2.0, 4.0])
        self.assertAlmostEqual(values[0][3], 1.0)

    def test_generates_portable_self_contained_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = self.fixture(Path(temporary))
            output = generate_report(report)
            document = output.read_text(encoding="utf-8")
            self.assertLess(output.stat().st_size, 1_000_000)
            self.assertIn("01-idle/current.csv", document)
            self.assertIn("Raw samples", document)
            self.assertNotIn(str(report.parent.resolve()), document)
            self.assertNotIn("https://", document)

    def test_zero_argument_selection_uses_latest_successful_suite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            power_runs = Path(temporary) / "power/runs"
            failed = power_runs / "20260918-000001-blu939-suite-failed"
            success = power_runs / "20260918-000000-blu939-suite-ok"
            self.fixture(success)
            self.fixture(failed, status="failed")
            failed.touch()
            self.assertEqual(_latest_successful(power_runs), success / "run.json")


if __name__ == "__main__":
    unittest.main()
