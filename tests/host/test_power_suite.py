# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from nrfkit_tools.power_suite_cli import (
    _durations, _profiles, _validate_observations,
)


class PowerSuiteTests(unittest.TestCase):
    def test_profile_order_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parsed = _profiles([f"idle={root / 'idle.json'}", f"direct-1m={root / 'one.json'}"])
        self.assertEqual([name for name, _ in parsed], ["idle", "direct-1m"])

    def test_duplicate_or_unsafe_profile_names_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate"):
            _profiles(["idle=a.json", "idle=b.json"])
        with self.assertRaisesRegex(ValueError, "invalid"):
            _profiles(["../idle=a.json"])
        with self.assertRaisesRegex(ValueError, "NAME=MANIFEST"):
            _profiles(["idle"])

    def test_profile_duration_overrides_are_validated(self) -> None:
        self.assertEqual(
            _durations(["idle=2.5"], {"idle", "ble"}, 18.0),
            {"idle": 2.5, "ble": 18.0},
        )
        with self.assertRaisesRegex(ValueError, "uniquely"):
            _durations(["unknown=2"], {"idle"}, 18.0)
        with self.assertRaisesRegex(ValueError, "invalid duration"):
            _durations(["idle=0"], {"idle"}, 18.0)

    def test_workload_observations_enforce_completion(self) -> None:
        _validate_observations("direct-4m", {
            "nrfkit_power_stage": 2,
            "nrfkit_power_packets": 1000,
            "nrfkit_power_batches": 1000,
        })
        _validate_observations("timeslot-retry-4m", {
            "accepted": 64, "completed": 64, "retries": 9,
            "dropped": 0, "grants": 73,
        })
        with self.assertRaisesRegex(RuntimeError, "eight-grant"):
            _validate_observations("ble-timeslot-4m", {
                "nrfkit_power_stage": 2,
                "nrfkit_power_timeslot_grants": 7,
                "nrfkit_power_timeslot_packets": 7,
            })


if __name__ == "__main__":
    unittest.main()
