# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import unittest
from argparse import Namespace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from nrfkit_tools.ble_validation import (
    BATTERY_LEVEL,
    BATTERY_SERVICE,
    BleValidationError,
    GATT_CHARACTERISTIC,
    GATT_SERVICE,
    HID_SERVICE,
    HID_REPORT_MAP,
    REQUIRED_HID_CHARACTERISTICS,
    audit_gatt_objects,
    bluetooth_info_argv,
    capture_hci,
    hci_monitor_argv,
    optional_hci_capture,
)
from nrfkit_tools.cli import command_m6_ble_gate, command_m6_ble_scan


class BleValidationTests(unittest.TestCase):
    def test_scan_command_writes_cleanup_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            run_dir = Path(directory)
            report = {"schema": "nrfkit-run/v1", "status": "running"}
            args = Namespace(device_name="nrfkit-m6-adv", timeout=5.0)
            result = {
                "device_name": args.device_name,
                "rssi_observed": True,
                "cleanup": {"verified": True},
            }
            with patch("nrfkit_tools.cli._new_run", return_value=(run_dir, report)), \
                 patch("nrfkit_tools.cli.scan_ble_advertisement", return_value=result):
                self.assertEqual(command_m6_ble_scan(args), 0)
            written = json.loads((run_dir / "run.json").read_text())
            self.assertEqual(written["status"], "ok")
            self.assertTrue(written["stages"][0]["cleanup"]["verified"])

    def test_scan_cleanup_accepts_bluez_already_absent_race(self) -> None:
        source = (
            Path(__file__).resolve().parents[2]
            / "tools/nrfkit_tools/ble_validation.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"org.bluez.Error.DoesNotExist"', source)
        self.assertIn('"already-absent"', source)

    def test_pairing_discovery_cleanup_reads_back_adapter_state(self) -> None:
        source = (
            Path(__file__).resolve().parents[2]
            / "tools/nrfkit_tools/ble_validation.py"
        ).read_text(encoding="utf-8")
        validation = source[source.index("def run_ble_validation("):]
        self.assertIn(
            "adapter_property_interface = dbus.Interface(adapter_object, PROPERTIES)",
            validation,
        )
        self.assertIn(
            'adapter_property_interface.Get(ADAPTER, "Discovering")', validation
        )

    def test_scan_command_preserves_failure_cleanup_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            run_dir = Path(directory)
            report = {"schema": "nrfkit-run/v1", "status": "running"}
            args = Namespace(device_name="nrfkit-m6-adv", timeout=5.0)
            error = BleValidationError(
                "scan timed out",
                details={
                    "failure_stage": "ble-advertisement",
                    "cleanup": {"verified": True},
                },
            )
            with patch("nrfkit_tools.cli._new_run", return_value=(run_dir, report)), \
                 patch("nrfkit_tools.cli.scan_ble_advertisement", side_effect=error), \
                 self.assertRaises(BleValidationError):
                command_m6_ble_scan(args)
            written = json.loads((run_dir / "run.json").read_text())
            self.assertEqual(written["status"], "failed")
            self.assertEqual(written["stages"][0]["name"], "ble-advertisement")
            self.assertTrue(written["stages"][0]["cleanup"]["verified"])

    def test_validation_error_keeps_structured_failure_details(self) -> None:
        error = BleValidationError(
            "pairing failed", details={"dbus_error": "org.bluez.Error.Failed"}
        )

        self.assertEqual(str(error), "pairing failed")
        self.assertEqual(error.details["dbus_error"], "org.bluez.Error.Failed")

    def test_cli_writes_structured_pairing_failure_stage(self) -> None:
        with TemporaryDirectory() as directory:
            run_dir = Path(directory)
            report = {"schema": "nrfkit-run/v1", "status": "running"}
            args = Namespace(
                device_name="nrfkit-m6-p5",
                timeout=45.0,
                fresh_pairing=True,
                hci_trace=False,
                btmon="/usr/sbin/btmon",
                phase="hid",
            )
            error = BleValidationError(
                "pairing failed",
                details={
                    "dbus_error": "org.bluez.Error.AuthenticationFailed",
                    "cleanup": {"verified": True},
                },
            )
            with patch("nrfkit_tools.cli._new_run", return_value=(run_dir, report)), \
                 patch("nrfkit_tools.cli.run_ble_validation", side_effect=error), \
                 self.assertRaises(BleValidationError):
                command_m6_ble_gate(args)

            written = json.loads((run_dir / "run.json").read_text())
            self.assertEqual(written["status"], "failed")
            self.assertEqual(written["stages"][0]["name"], "ble-pairing")
            self.assertEqual(written["stages"][0]["status"], "failed")
            self.assertTrue(written["stages"][0]["cleanup"]["verified"])

    def test_cli_preserves_discovery_timeout_cleanup_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            run_dir = Path(directory)
            report = {"schema": "nrfkit-run/v1", "status": "running"}
            args = Namespace(
                device_name="nrfkit-m6-p5",
                timeout=45.0,
                fresh_pairing=True,
                hci_trace=False,
                btmon="/usr/sbin/btmon",
                phase="oracle",
            )
            error = BleValidationError(
                "target not found",
                details={
                    "failure_stage": "ble-advertisement",
                    "phase": "oracle",
                    "cleanup": {
                        "stop_discovery_attempted": True,
                        "verified": True,
                        "errors": [],
                    },
                },
            )
            with patch("nrfkit_tools.cli._new_run", return_value=(run_dir, report)), \
                 patch("nrfkit_tools.cli.run_ble_validation", side_effect=error), \
                 self.assertRaises(BleValidationError):
                command_m6_ble_gate(args)

            written = json.loads((run_dir / "run.json").read_text())
            stage = written["stages"][0]
            self.assertEqual(stage["name"], "ble-advertisement")
            self.assertTrue(stage["cleanup"]["stop_discovery_attempted"])
            self.assertTrue(stage["cleanup"]["verified"])

    def test_report_map_is_the_encryption_proof_attribute(self) -> None:
        self.assertEqual(HID_REPORT_MAP, "00002a4b-0000-1000-8000-00805f9b34fb")
        self.assertIn(HID_REPORT_MAP, REQUIRED_HID_CHARACTERISTICS)

    def test_hci_monitor_always_has_an_outer_hard_timeout(self) -> None:
        self.assertEqual(
            hci_monitor_argv(btmon="/usr/sbin/btmon", timeout=17),
            [
                "timeout", "--foreground", "--signal=INT", "--kill-after=2",
                "17", "/usr/sbin/btmon",
            ],
        )

    def test_bluetooth_info_is_read_only_and_bounded(self) -> None:
        self.assertEqual(
            bluetooth_info_argv(btmgmt="/usr/bin/btmgmt", index=2, timeout=5),
            [
                "timeout", "--foreground", "--signal=TERM", "--kill-after=2",
                "5", "/usr/bin/btmgmt", "--index", "2", "info",
            ],
        )

    def test_hci_monitor_cleanup_stops_the_process_group(self) -> None:
        class Process:
            pid = 31415
            returncode = None

            def poll(self) -> int | None:
                return self.returncode

            def wait(self, timeout: float) -> int:
                self.returncode = 130
                return self.returncode

        process = Process()
        with TemporaryDirectory() as directory, \
             patch("nrfkit_tools.ble_validation.subprocess.Popen", return_value=process), \
             patch("nrfkit_tools.ble_validation.time.sleep"), \
             patch("nrfkit_tools.ble_validation.os.killpg") as killpg:
            with capture_hci(
                log=Path(directory) / "hci.log",
                btmon="/usr/sbin/btmon",
                timeout=17,
            ) as trace:
                self.assertFalse(trace["cleaned"])

        killpg.assert_called_once_with(process.pid, 2)
        self.assertTrue(trace["cleaned"])

    def test_unavailable_hci_diagnostic_does_not_block_validation(self) -> None:
        with TemporaryDirectory() as directory, \
             patch(
                 "nrfkit_tools.ble_validation.capture_hci"
             ) as capture:
            capture.return_value.__enter__.side_effect = BleValidationError(
                "permission denied"
            )
            with optional_hci_capture(
                log=Path(directory) / "hci.log",
                btmon="/usr/sbin/btmon",
                timeout=17,
            ) as state:
                self.assertFalse(state["available"])
                self.assertIn("permission denied", state["error"])

    def test_gatt_contract_is_scoped_to_selected_device(self) -> None:
        device = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF"
        objects = {
            f"{device}/service0001": {GATT_SERVICE: {"UUID": HID_SERVICE.upper()}},
            f"{device}/service0002": {GATT_SERVICE: {"UUID": BATTERY_SERVICE}},
            "/org/bluez/hci0/dev_00_00_00_00_00_00/service9999": {
                GATT_SERVICE: {"UUID": "unrelated"}
            },
        }
        for index, uuid in enumerate(sorted(REQUIRED_HID_CHARACTERISTICS | {BATTERY_LEVEL})):
            objects[f"{device}/service0001/char{index:04x}"] = {
                GATT_CHARACTERISTIC: {"UUID": uuid}
            }

        result = audit_gatt_objects(objects, device)

        self.assertEqual(result["services"], sorted({BATTERY_SERVICE, HID_SERVICE}))
        self.assertNotIn("unrelated", result["services"])

    def test_missing_hid_characteristic_is_rejected(self) -> None:
        device = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF"
        objects = {
            f"{device}/service0001": {GATT_SERVICE: {"UUID": HID_SERVICE}},
            f"{device}/service0002": {GATT_SERVICE: {"UUID": BATTERY_SERVICE}},
            f"{device}/service0002/char0001": {
                GATT_CHARACTERISTIC: {"UUID": BATTERY_LEVEL}
            },
        }

        with self.assertRaisesRegex(BleValidationError, "GATT contract is incomplete"):
            audit_gatt_objects(objects, device)

    def test_plaintext_contract_only_requires_battery(self) -> None:
        device = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF"
        objects = {
            f"{device}/service0001": {GATT_SERVICE: {"UUID": BATTERY_SERVICE}},
            f"{device}/service0001/char0001": {
                GATT_CHARACTERISTIC: {"UUID": BATTERY_LEVEL}
            },
        }

        result = audit_gatt_objects(objects, device, require_hid=False)

        self.assertEqual(result["services"], [BATTERY_SERVICE])
        self.assertEqual(result["characteristics"], [BATTERY_LEVEL])


if __name__ == "__main__":
    unittest.main()
