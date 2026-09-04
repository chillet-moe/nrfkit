# SPDX-License-Identifier: BSD-3-Clause

import argparse
import json
import os
from pathlib import Path
import tempfile
import termios
import time
import unittest
from unittest import mock

from nrf_cmake_tools.cli import (
    ToolError, _probe_lock, _serial_open, _serial_reader, _serial_reader_stop,
    command_flash, command_run, load_manifest,
)
from nrf_cmake_tools.device import program_argv, safe_backend_contract
from nrf_cmake_tools.image import ImageContractError


class FlashCommandTests(unittest.TestCase):
    def test_programming_command_is_non_erasing_verified_and_non_resetting(self) -> None:
        argv = program_argv("nrfutil", "firmware.hex", "123", "NRF54L", "Application")
        joined = " ".join(argv)
        self.assertIn("chip_erase_mode=ERASE_NONE", joined)
        self.assertIn("verify=VERIFY_READ", joined)
        self.assertIn("reset=RESET_NONE", joined)
        self.assertNotIn("ERASE_ALL", joined)
        self.assertNotIn("recover", argv)

    def test_invalid_image_is_rejected_before_device_or_vendor_tool(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            report = {"schema": "nrf-cmake-sdk-run/v1", "status": "running"}
            args = argparse.Namespace(manifest="invalid")
            with (
                mock.patch(
                    "nrf_cmake_tools.cli.load_manifest",
                    side_effect=ImageContractError("forbidden UICR region"),
                ),
                mock.patch(
                    "nrf_cmake_tools.cli._new_run", return_value=(run_dir, report)
                ),
                mock.patch("nrf_cmake_tools.cli._enumerate") as enumerate_devices,
                mock.patch("nrf_cmake_tools.cli._program") as program,
            ):
                with self.assertRaisesRegex(ImageContractError, "UICR"):
                    command_flash(args)
            self.assertEqual(report["status"], "failed")
            self.assertIn("forbidden UICR region", report["error"])
            enumerate_devices.assert_not_called()
            program.assert_not_called()

    def test_manifest_cannot_relax_backend_contract(self) -> None:
        manifest = {
            "schema": "nrf-cmake-sdk-image/v1", "oracle": "test",
            "source_receipt_sha256": "0" * 64, "soc": "test", "core": "Application",
            "board": "test", "board_version": "test", "device_family": "test",
            "expected_token": "test", "vcom": "VCOM1", "debug_allowlist": [[0, 1]],
            "debug_elf": {}, "images": [], "backend": safe_backend_contract(),
        }
        manifest["backend"]["program_options"]["chip_erase_mode"] = "ERASE_ALL"
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as temporary:
            json.dump(manifest, temporary)
        path = Path(temporary.name)
        self.addCleanup(path.unlink)
        with self.assertRaisesRegex(ToolError, "backend contract"):
            load_manifest(path, artifacts=False)

    def test_serial_reader_drains_while_an_operation_is_running(self) -> None:
        read_descriptor, write_descriptor = os.pipe()
        self.addCleanup(os.close, read_descriptor)
        self.addCleanup(os.close, write_descriptor)
        reader = _serial_reader(read_descriptor)
        os.write(write_descriptor, b"startup token")
        deadline = time.monotonic() + 1
        while b"startup token" not in reader[2] and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(_serial_reader_stop(reader), b"startup token")

    def test_serial_open_claims_exclusive_access_and_closes_on_failure(self) -> None:
        with (
            mock.patch("nrf_cmake_tools.cli.os.open", return_value=17),
            mock.patch("nrf_cmake_tools.cli.fcntl.ioctl") as ioctl,
            mock.patch(
                "nrf_cmake_tools.cli.tty.setraw", side_effect=OSError("raw failed")
            ),
            mock.patch("nrf_cmake_tools.cli.os.close") as close,
        ):
            with self.assertRaisesRegex(OSError, "raw failed"):
                _serial_open(Path("/dev/test-vcom"))
        if hasattr(termios, "TIOCEXCL"):
            ioctl.assert_called_once_with(17, termios.TIOCEXCL, 0)
        close.assert_called_once_with(17)

    def test_probe_lock_rejects_contention_and_can_be_reacquired(self) -> None:
        identity = f"host-test-{os.getpid()}"
        with _probe_lock(identity, "first"):
            with self.assertRaisesRegex(ToolError, "locked"):
                with _probe_lock(identity, "second"):
                    self.fail("contended lock was acquired")
        with _probe_lock(identity, "third"):
            pass

    def test_oracle_run_orchestrates_doctor_build_and_manifest_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            report = {"schema": "nrf-cmake-sdk-run/v1", "status": "running"}
            args = argparse.Namespace(
                manifest=None, oracle="ncs-hello-world", build_timeout=900,
                west="west", timeout=90, token_timeout=10,
                serial_ready_delay=0.5, official_toolchain=Path("toolchain"),
            )
            manifest = {
                "oracle": "ncs-hello-world", "board_version": "PCA10184",
            }
            with (
                mock.patch("nrf_cmake_tools.cli._new_run", return_value=(run_dir, report)),
                mock.patch(
                    "nrf_cmake_tools.cli._doctor",
                    return_value=({"tools": {"all": {"returncode": 0}}}, True),
                ) as doctor,
                mock.patch(
                    "nrf_cmake_tools.cli.build", return_value=run_dir / "image-manifest.json"
                ) as reference_build,
                mock.patch("nrf_cmake_tools.cli.load_manifest", return_value=manifest) as audit,
                mock.patch("nrf_cmake_tools.cli._initialize_device_report"),
                mock.patch(
                    "nrf_cmake_tools.cli._select", side_effect=ToolError("stop before hardware")
                ),
            ):
                with self.assertRaisesRegex(ToolError, "before hardware"):
                    command_run(args)
            doctor.assert_called_once_with(args)
            reference_build.assert_called_once_with(
                mock.ANY, "ncs-hello-world", 900, "west"
            )
            audit.assert_called_once_with(run_dir / "image-manifest.json")


if __name__ == "__main__":
    unittest.main()
