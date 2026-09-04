# SPDX-License-Identifier: BSD-3-Clause

import argparse
from contextlib import nullcontext
import json
import os
from pathlib import Path
import tempfile
import termios
import time
import unittest
from unittest import mock

from nrfkit_tools.cli import (
    ToolError, _probe_has_msd, _probe_lock, _serial_cleanup, _serial_open,
    _serial_reader, _serial_reader_stop, _set_probe_msd, command_flash,
    command_m2_gate, command_p0_gate, command_probe_msd, command_run, load_manifest,
)
from nrfkit_tools.device import program_argv, reset_argv, safe_backend_contract
from nrfkit_tools.image import ImageContractError
from nrfkit_tools.process import ProcessResult


class FlashCommandTests(unittest.TestCase):
    @staticmethod
    def probe_device(msd: bool) -> dict:
        interfaces = [{"class": 2, "interfaceString": "CDC"}]
        if msd:
            interfaces.append({"class": 8, "interfaceString": "MSD interface"})
        return {
            "serialNumber": "probe-123",
            "devkit": {"boardVersion": "PCA10184"},
            "usb": {"interfaces": interfaces},
            "serialPorts": [{"vcom": 0}, {"vcom": 1}],
            "traits": {"jlink": True},
        }

    def test_programming_command_is_non_erasing_verified_and_non_resetting(self) -> None:
        argv = program_argv("nrfutil", "firmware.hex", "123", "NRF54L", "Application")
        joined = " ".join(argv)
        self.assertIn("chip_erase_mode=ERASE_NONE", joined)
        self.assertIn("verify=VERIFY_READ", joined)
        self.assertIn("reset=RESET_NONE", joined)
        self.assertNotIn("ERASE_ALL", joined)
        self.assertNotIn("recover", argv)

    def test_reset_command_can_request_a_pin_reset(self) -> None:
        argv = reset_argv(
            "nrfutil", "123", "NRF54L", "Application", "RESET_PIN"
        )
        self.assertEqual(argv[-2:], ["--reset-kind", "RESET_PIN"])

    def test_invalid_image_is_rejected_before_device_or_vendor_tool(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            report = {"schema": "nrfkit-run/v1", "status": "running"}
            args = argparse.Namespace(manifest="invalid")
            with (
                mock.patch(
                    "nrfkit_tools.cli.load_manifest",
                    side_effect=ImageContractError("forbidden UICR region"),
                ),
                mock.patch(
                    "nrfkit_tools.cli._new_run", return_value=(run_dir, report)
                ),
                mock.patch("nrfkit_tools.cli._enumerate") as enumerate_devices,
                mock.patch("nrfkit_tools.cli._program") as program,
            ):
                with self.assertRaisesRegex(ImageContractError, "UICR"):
                    command_flash(args)
            self.assertEqual(report["status"], "failed")
            self.assertIn("forbidden UICR region", report["error"])
            enumerate_devices.assert_not_called()
            program.assert_not_called()

    def test_manifest_cannot_relax_backend_contract(self) -> None:
        manifest = {
            "schema": "nrfkit-image/v1", "oracle": "test",
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
            mock.patch("nrfkit_tools.cli.os.open", return_value=17),
            mock.patch("nrfkit_tools.cli.fcntl.ioctl") as ioctl,
            mock.patch(
                "nrfkit_tools.cli.tty.setraw", side_effect=OSError("raw failed")
            ),
            mock.patch("nrfkit_tools.cli.os.close") as close,
        ):
            with self.assertRaisesRegex(OSError, "raw failed"):
                _serial_open(Path("/dev/test-vcom"))
        if hasattr(termios, "TIOCEXCL"):
            ioctl.assert_called_once_with(17, termios.TIOCEXCL, 0)
        close.assert_called_once_with(17)

    def test_serial_cleanup_closes_descriptor_after_reader_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            thread = mock.Mock()
            thread.is_alive.return_value = False
            reader = (mock.Mock(), thread, bytearray(b"partial output"), [])
            with (
                mock.patch(
                    "nrfkit_tools.cli._serial_reader_stop",
                    side_effect=ToolError("reader stuck"),
                ),
                mock.patch("nrfkit_tools.cli.os.close") as close,
            ):
                cleanup, error = _serial_cleanup(run_dir, reader, 17)
            close.assert_called_once_with(17)
            self.assertTrue(cleanup["serial_reader_stopped"])
            self.assertTrue(cleanup["serial_closed"])
            self.assertIn("reader stuck", str(error))
            self.assertEqual((run_dir / "serial.log").read_bytes(), b"partial output")

    def test_probe_msd_detection_uses_usb_interface_contract(self) -> None:
        self.assertTrue(_probe_has_msd(self.probe_device(True)))
        self.assertFalse(_probe_has_msd(self.probe_device(False)))

    def test_probe_msd_command_is_exact_and_reboots_before_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "nested/run"
            device = self.probe_device(True)
            output = "Probe configured successfully.\nRebooted successfully.\n"
            with (
                mock.patch(
                    "nrfkit_tools.cli._probe_lock", return_value=nullcontext()
                ),
                mock.patch(
                    "nrfkit_tools.cli.run_logged",
                    return_value=ProcessResult(0, False, 0.1, output),
                ) as run_logged,
                mock.patch(
                    "nrfkit_tools.cli._wait_for_probe_msd_state",
                    return_value=self.probe_device(False),
                ) as wait_for_state,
            ):
                _set_probe_msd(
                    "JLinkExe", "nrfutil", device, False, run_dir, 10
                )
            command_file = run_dir / "msd-disable.jlink"
            self.assertEqual(
                command_file.read_text(encoding="ascii"),
                "MSDDisable\nReboot force\nExit\n",
            )
            self.assertEqual(command_file.stat().st_mode & 0o777, 0o400)
            self.assertEqual(run_logged.call_args.args[0], [
                "JLinkExe", "-USB", "probe-123", "-NoGui", "1",
                "-ExitOnError", "1", "-CommandFile", str(command_file),
            ])
            wait_for_state.assert_called_once_with(
                "nrfutil", "probe-123", "PCA10184", False,
                run_dir / "msd-disable-verification", 10,
            )

    def test_persistent_probe_msd_change_requires_explicit_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            report = {"schema": "nrfkit-run/v1", "status": "running"}
            args = argparse.Namespace(
                nrfutil="nrfutil", jlink_commander="JLinkExe", probe_serial=None,
                timeout=10, enabled=False, authorize_persistent_change=False,
            )
            with (
                mock.patch("nrfkit_tools.cli._new_run", return_value=(run_dir, report)),
                mock.patch(
                    "nrfkit_tools.cli.executable", side_effect=lambda value, _: value
                ),
                mock.patch(
                    "nrfkit_tools.cli.oracle",
                    return_value={"board_version": "PCA10184"},
                ),
                mock.patch(
                    "nrfkit_tools.cli._enumerate",
                    return_value=[self.probe_device(True)],
                ),
                mock.patch("nrfkit_tools.cli._set_probe_msd") as set_msd,
            ):
                with self.assertRaisesRegex(ToolError, "explicit .* is required"):
                    command_probe_msd(args)
            set_msd.assert_not_called()
            self.assertEqual(report["status"], "failed")
            self.assertTrue((run_dir / "probe-state-before.json").is_file())

    def test_persistent_probe_msd_disable_backs_up_and_verifies_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            report = {"schema": "nrfkit-run/v1", "status": "running"}
            enabled = self.probe_device(True)
            disabled = self.probe_device(False)
            args = argparse.Namespace(
                nrfutil="nrfutil", jlink_commander="JLinkExe", probe_serial=None,
                timeout=10, enabled=False, authorize_persistent_change=True,
            )
            with (
                mock.patch("nrfkit_tools.cli._new_run", return_value=(run_dir, report)),
                mock.patch(
                    "nrfkit_tools.cli.executable", side_effect=lambda value, _: value
                ),
                mock.patch(
                    "nrfkit_tools.cli.oracle",
                    return_value={"board_version": "PCA10184"},
                ),
                mock.patch("nrfkit_tools.cli._enumerate", return_value=[enabled]),
                mock.patch(
                    "nrfkit_tools.cli._set_probe_msd", return_value=disabled
                ) as set_msd,
                mock.patch("builtins.print"),
            ):
                self.assertEqual(command_probe_msd(args), 0)
            set_msd.assert_called_once_with(
                "JLinkExe", "nrfutil", enabled, False,
                run_dir / "probe-msd", 10,
            )
            self.assertEqual(
                json.loads((run_dir / "probe-state-before.json").read_text()), enabled
            )
            self.assertEqual(
                json.loads((run_dir / "probe-state-after.json").read_text()), disabled
            )
            self.assertTrue(report["persistent_change_applied"])
            self.assertFalse(report["probe_msd_finally_enabled"])

    def test_persistent_probe_msd_disable_is_idempotent_without_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            report = {"schema": "nrfkit-run/v1", "status": "running"}
            disabled = self.probe_device(False)
            args = argparse.Namespace(
                nrfutil="nrfutil", jlink_commander="JLinkExe", probe_serial=None,
                timeout=10, enabled=False, authorize_persistent_change=False,
            )
            with (
                mock.patch("nrfkit_tools.cli._new_run", return_value=(run_dir, report)),
                mock.patch(
                    "nrfkit_tools.cli.executable", side_effect=lambda value, _: value
                ),
                mock.patch(
                    "nrfkit_tools.cli.oracle",
                    return_value={"board_version": "PCA10184"},
                ),
                mock.patch("nrfkit_tools.cli._enumerate", return_value=[disabled]),
                mock.patch("nrfkit_tools.cli._set_probe_msd") as set_msd,
                mock.patch("builtins.print"),
            ):
                self.assertEqual(command_probe_msd(args), 0)
            set_msd.assert_not_called()
            self.assertFalse(report["persistent_change_applied"])
            self.assertFalse(report["probe_msd_finally_enabled"])

    def test_p0_gate_refuses_msd_change_without_explicit_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            report = {"schema": "nrfkit-run/v1", "status": "running"}
            args = argparse.Namespace(
                nrfutil="nrfutil", jlink_commander="JLinkExe", gdb="gdb",
                jlink="server", probe_serial=None, timeout=10,
                authorize_temporary_msd_disable=False,
            )
            with (
                mock.patch("nrfkit_tools.cli._new_run", return_value=(run_dir, report)),
                mock.patch(
                    "nrfkit_tools.cli.executable", side_effect=lambda value, _: value
                ),
                mock.patch(
                    "nrfkit_tools.cli.oracle",
                    return_value={"board_version": "PCA10184"},
                ),
                mock.patch(
                    "nrfkit_tools.cli._enumerate",
                    return_value=[self.probe_device(True)],
                ),
                mock.patch("nrfkit_tools.cli._set_probe_msd") as set_msd,
            ):
                with self.assertRaisesRegex(ToolError, "explicit .* is required"):
                    command_p0_gate(args)
            set_msd.assert_not_called()
            self.assertTrue(report["cleanup"]["probe_msd_restored"])

    def test_p0_gate_restores_msd_after_child_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            report = {"schema": "nrfkit-run/v1", "status": "running"}
            enabled = self.probe_device(True)
            disabled = self.probe_device(False)
            args = argparse.Namespace(
                nrfutil="nrfutil", jlink_commander="JLinkExe", gdb="gdb",
                jlink="server", probe_serial=None, timeout=10, build_timeout=20,
                token_timeout=3, serial_ready_delay=0.1, gate_timeout=30,
                cmake="cmake", ninja="ninja", west="west",
                authorize_temporary_msd_disable=True,
            )
            with (
                mock.patch("nrfkit_tools.cli._new_run", return_value=(run_dir, report)),
                mock.patch(
                    "nrfkit_tools.cli.executable", side_effect=lambda value, _: value
                ),
                mock.patch(
                    "nrfkit_tools.cli.oracle",
                    return_value={"board_version": "PCA10184"},
                ),
                mock.patch("nrfkit_tools.cli._enumerate", return_value=[enabled]),
                mock.patch(
                    "nrfkit_tools.cli._set_probe_msd",
                    side_effect=(disabled, enabled),
                ) as set_msd,
                mock.patch(
                    "nrfkit_tools.cli._run_p0_child",
                    side_effect=ToolError("child failed"),
                ),
            ):
                with self.assertRaisesRegex(ToolError, "child failed"):
                    command_p0_gate(args)
            self.assertEqual(
                [call.args[3] for call in set_msd.call_args_list], [False, True]
            )
            self.assertTrue(report["cleanup"]["probe_msd_restored"])

    def test_p0_gate_runs_complete_public_child_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            report = {"schema": "nrfkit-run/v1", "status": "running"}
            device = self.probe_device(False)
            args = argparse.Namespace(
                nrfutil="nrfutil", jlink_commander="JLinkExe", gdb="gdb",
                jlink="server", probe_serial=None, timeout=10, build_timeout=20,
                token_timeout=3, serial_ready_delay=0.1, gate_timeout=30,
                cmake="cmake", ninja="ninja", west="west",
                authorize_temporary_msd_disable=False,
            )
            child_reports = [f"/tmp/child-{index}.json" for index in range(5)]
            with (
                mock.patch("nrfkit_tools.cli._new_run", return_value=(run_dir, report)),
                mock.patch(
                    "nrfkit_tools.cli.executable", side_effect=lambda value, _: value
                ),
                mock.patch(
                    "nrfkit_tools.cli.oracle",
                    return_value={"board_version": "PCA10184"},
                ),
                mock.patch("nrfkit_tools.cli._enumerate", return_value=[device]),
                mock.patch("nrfkit_tools.cli._set_probe_msd") as set_msd,
                mock.patch(
                    "nrfkit_tools.cli._run_p0_child",
                    side_effect=child_reports,
                ) as run_child,
                mock.patch("builtins.print"),
            ):
                self.assertEqual(command_p0_gate(args), 0)
            set_msd.assert_not_called()
            self.assertEqual(run_child.call_count, 5)
            child_argvs = [call.args[0] for call in run_child.call_args_list]
            self.assertEqual(
                [argv[-1] for argv in child_argvs[:4]],
                ["ncs-hello-world"] * 3 + ["nrf-bm-leds-s115"],
            )
            self.assertEqual(child_argvs[4][1], "gdb-smoke")
            self.assertIn("--verify-token", child_argvs[4])

    def test_m2_gate_runs_cycles_gdb_fault_and_restoration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            report = {"schema": "nrfkit-run/v1", "status": "running"}
            args = argparse.Namespace(
                normal_manifest=Path("normal.json"), fault_manifest=Path("fault.json"),
                nrfutil="nrfutil", gdb="gdb", jlink="server", probe_serial=None,
                timeout=10, token_timeout=3, serial_ready_delay=0.1, gate_timeout=30,
            )
            manifests = (
                {
                    "oracle": "sdk-hardware_validation",
                    "source_receipt_sha256": "a",
                    "expected_token": "NRFKIT_BOOT test",
                },
                {"oracle": "sdk-fault", "source_receipt_sha256": "a"},
            )
            child_reports = [f"/tmp/m2-child-{index}.json" for index in range(24)]
            with (
                mock.patch("nrfkit_tools.cli._new_run", return_value=(run_dir, report)),
                mock.patch("nrfkit_tools.cli.load_manifest", side_effect=manifests),
                mock.patch(
                    "nrfkit_tools.cli.executable", side_effect=lambda value, _: value
                ),
                mock.patch("nrfkit_tools.cli.sha256", return_value="a"),
                mock.patch(
                    "nrfkit_tools.cli._run_p0_child", side_effect=child_reports
                ) as run_child,
                mock.patch("builtins.print"),
            ):
                self.assertEqual(command_m2_gate(args), 0)
            self.assertEqual(run_child.call_count, 24)
            argvs = [call.args[0] for call in run_child.call_args_list]
            self.assertTrue(all(argv[1] == "run" for argv in argvs[:20]))
            self.assertIn("--sdk-runtime-contract", argvs[20])
            self.assertEqual(argvs[21][1], "flash")
            self.assertIn("--fault-contract", argvs[22])
            self.assertEqual(argvs[23][1], "run")
            self.assertTrue(report["cleanup"]["normal_image_restored"])

    def test_m2_gate_restores_normal_image_after_fault_contract_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            report = {"schema": "nrfkit-run/v1", "status": "running"}
            args = argparse.Namespace(
                normal_manifest=Path("normal.json"), fault_manifest=Path("fault.json"),
                nrfutil="nrfutil", gdb="gdb", jlink="server", probe_serial=None,
                timeout=10, token_timeout=3, serial_ready_delay=0.1, gate_timeout=30,
            )
            manifests = (
                {
                    "oracle": "sdk-hardware_validation",
                    "source_receipt_sha256": "a",
                    "expected_token": "NRFKIT_BOOT test",
                },
                {"oracle": "sdk-fault", "source_receipt_sha256": "a"},
            )
            effects = [f"/tmp/m2-child-{index}.json" for index in range(22)]
            effects.extend((ToolError("fault contract failed"), "/tmp/restored.json"))
            with (
                mock.patch("nrfkit_tools.cli._new_run", return_value=(run_dir, report)),
                mock.patch("nrfkit_tools.cli.load_manifest", side_effect=manifests),
                mock.patch(
                    "nrfkit_tools.cli.executable", side_effect=lambda value, _: value
                ),
                mock.patch("nrfkit_tools.cli.sha256", return_value="a"),
                mock.patch(
                    "nrfkit_tools.cli._run_p0_child", side_effect=effects
                ) as run_child,
            ):
                with self.assertRaisesRegex(ToolError, "fault contract failed"):
                    command_m2_gate(args)
            self.assertEqual(run_child.call_args.args[0][1], "run")
            self.assertTrue(report["cleanup"]["normal_image_restored"])

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
            report = {"schema": "nrfkit-run/v1", "status": "running"}
            args = argparse.Namespace(
                manifest=None, oracle="ncs-hello-world", build_timeout=900,
                west="west", timeout=90, token_timeout=10,
                serial_ready_delay=0.5, official_toolchain=Path("toolchain"),
            )
            manifest = {
                "oracle": "ncs-hello-world", "board_version": "PCA10184",
            }
            with (
                mock.patch("nrfkit_tools.cli._new_run", return_value=(run_dir, report)),
                mock.patch(
                    "nrfkit_tools.cli._doctor",
                    return_value=({"tools": {"all": {"returncode": 0}}}, True),
                ) as doctor,
                mock.patch(
                    "nrfkit_tools.cli.build", return_value=run_dir / "image-manifest.json"
                ) as reference_build,
                mock.patch("nrfkit_tools.cli.load_manifest", return_value=manifest) as audit,
                mock.patch("nrfkit_tools.cli._initialize_device_report"),
                mock.patch(
                    "nrfkit_tools.cli._select", side_effect=ToolError("stop before hardware")
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
