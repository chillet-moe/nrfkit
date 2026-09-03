# SPDX-License-Identifier: BSD-3-Clause

import argparse
import os
import time
import unittest
from unittest import mock

from nrf_cmake_tools.cli import (
    ToolError, _probe_lock, _serial_reader, _serial_reader_stop, command_flash,
)
from nrf_cmake_tools.device import program_argv
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
        args = argparse.Namespace(manifest="invalid")
        with (
            mock.patch(
                "nrf_cmake_tools.cli.load_manifest",
                side_effect=ImageContractError("forbidden UICR region"),
            ),
            mock.patch("nrf_cmake_tools.cli._new_run") as new_run,
            mock.patch("nrf_cmake_tools.cli._enumerate") as enumerate_devices,
            mock.patch("nrf_cmake_tools.cli._program") as program,
        ):
            with self.assertRaisesRegex(ImageContractError, "UICR"):
                command_flash(args)
        new_run.assert_not_called()
        enumerate_devices.assert_not_called()
        program.assert_not_called()

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

    def test_probe_lock_rejects_contention_and_can_be_reacquired(self) -> None:
        identity = f"host-test-{os.getpid()}"
        with _probe_lock(identity, "first"):
            with self.assertRaisesRegex(ToolError, "locked"):
                with _probe_lock(identity, "second"):
                    self.fail("contended lock was acquired")
        with _probe_lock(identity, "third"):
            pass


if __name__ == "__main__":
    unittest.main()
