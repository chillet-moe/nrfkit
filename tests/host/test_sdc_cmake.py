# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/consumer/sdc-contract"
COMBINED_FIXTURE = ROOT / "tests/consumer/combined-contract"


class SdcCmakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cmake = shutil.which("cmake")
        cls.ninja = shutil.which("ninja") or shutil.which("ninja-build")
        configured_llvm = os.environ.get("NRF_LLVM_ROOT")
        clang = shutil.which("clang")
        cls.llvm_root = (
            Path(configured_llvm) if configured_llvm else Path(clang).resolve().parent.parent
        ) if configured_llvm or clang else None
        if not cls.cmake or not cls.ninja or cls.llvm_root is None:
            raise unittest.SkipTest("CMake, Ninja, and locked LLVM are required")

    def configure(self, directory: Path, case: str,
                  *options: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([
            self.cmake, "-S", str(FIXTURE), "-B", str(directory), "-G", "Ninja",
            f"-DNrfKit_DIR={ROOT / 'cmake'}",
            f"-DCMAKE_TOOLCHAIN_FILE={ROOT / 'cmake/toolchains/arm-clang.cmake'}",
            f"-DNRF_LLVM_ROOT={self.llvm_root}",
            f"-DCONTRACT_CASE={case}",
            *options,
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)

    def copy_wireless_input(self, destination: Path) -> None:
        upstream = ROOT / "external/sdk-nrfxlib"
        source = json.loads((ROOT / "docs/provenance/sources.lock").read_text())[
            "audited_sources"]["sdk-nrfxlib-3.4.0"]
        paths = set(source["files"])
        for include in ("mpsl/include", "mpsl/fem/include",
                        "softdevice_controller/include"):
            paths.update(path.relative_to(upstream).as_posix()
                         for path in (upstream / include).rglob("*.h"))
        for relative in paths:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(upstream / relative, target)

    def test_explicit_wireless_input_is_used_in_link_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            upstream = base / "wireless"
            self.copy_wireless_input(upstream)
            result = self.configure(base / "build", "valid",
                                    f"-DNRFKIT_NRFXLIB_ROOT={upstream}")
            self.assertEqual(result.returncode, 0, result.stdout)
            contract = json.loads((base / "build/nrfkit/contract/sdc-target.json").read_text())
            self.assertTrue(all(Path(path).is_relative_to(upstream)
                                for path in contract["archives"]))
            result = subprocess.run([self.cmake, "--build", str(base / "build")],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(str(upstream), (base / "build/contract.map").read_text())

    def test_wireless_input_drift_and_missing_override_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            upstream = base / "wireless"
            result = self.configure(base / "missing", "valid",
                                    f"-DNRFKIT_NRFXLIB_ROOT={upstream}")
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.copy_wireless_input(upstream)
            for index, relative in enumerate((
                "mpsl/include/mpsl_timeslot.h",
                "softdevice_controller/include/sdc_hci_cmd_le.h",
                "mpsl/fem/include/protocol/mpsl_fem_protocol_api.h",
                "mpsl/lib/nrf54lm/manifest.yaml",
                "mpsl/license.txt",
                "mpsl/lib/nrf54lm/hard-float/libmpsl.a",
            )):
                with self.subTest(relative=relative):
                    path = upstream / relative
                    original = path.read_bytes()
                    path.write_bytes(original + b"\n/* drift */\n")
                    result = self.configure(base / f"drift-{index}", "valid",
                                            f"-DNRFKIT_NRFXLIB_ROOT={upstream}")
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn("hash mismatch", result.stdout)
                    path.write_bytes(original)
            extra = upstream / "mpsl/include/unlocked.h"
            extra.write_text("/* Unexpected public input. */\n")
            result = self.configure(base / "extra", "valid",
                                    f"-DNRFKIT_NRFXLIB_ROOT={upstream}")
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("header set mismatch", result.stdout)
            extra.unlink()
            (upstream / "mpsl/license.txt").unlink()
            result = self.configure(base / "missing-license", "valid",
                                    f"-DNRFKIT_NRFXLIB_ROOT={upstream}")
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("input is missing: mpsl/license.txt", result.stdout)

    def test_multirole_target_locks_archives_and_all_resources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            configured = self.configure(build, "valid")
            self.assertEqual(configured.returncode, 0, configured.stdout)
            built = subprocess.run(
                [self.cmake, "--build", str(build)], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            self.assertEqual(built.returncode, 0, built.stdout)
            contract = json.loads(
                (build / "nrfkit/contract/sdc-target.json").read_text(encoding="utf-8")
            )
            self.assertEqual(contract["variant"], "multirole")
            self.assertEqual(contract["float_abi"], "hard-float")
            self.assertEqual(contract["security_domain"], "secure")
            self.assertIn("timer20", contract["resources"])
            self.assertIn("ecb00", contract["resources"])
            self.assertIn("grtc.channel.11", contract["resources"])
            self.assertIn("dppi10.channel.11", contract["resources"])
            self.assertTrue(contract["archives"][0].endswith("libmpsl.a"))
            self.assertTrue(
                contract["archives"][1].endswith("libmpsl_fem_common.a")
            )
            self.assertTrue(
                contract["archives"][2].endswith("libsoftdevice_controller_multirole.a")
            )
            ninja = (build / "build.ninja").read_text(encoding="utf-8")
            self.assertIn("libsoftdevice_controller_multirole.a", ninja)
            self.assertIn("libmpsl.a", ninja)
            self.assertIn("libmpsl_fem_common.a", ninja)
            self.assertNotIn("zephyr", " ".join(contract["archives"]).lower())

    def test_sdc_resource_conflict_and_unknown_variant_fail_at_configure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for case, expected in (
                ("conflict", "timer20' is already owned by 'application'"),
                ("invalid-variant", "unsupported VARIANT 'observer'"),
            ):
                configured = self.configure(base / case, case)
                self.assertNotEqual(configured.returncode, 0, configured.stdout)
                self.assertIn(expected, configured.stdout)

    def test_installed_package_keeps_selected_nrfxlib_offline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            sdk_build = base / "sdk-build"
            prefix = base / "prefix"
            consumer = base / "consumer"
            for argv in (
                [
                    self.cmake, "-S", str(ROOT), "-B", str(sdk_build), "-G", "Ninja",
                    f"-DCMAKE_INSTALL_PREFIX={prefix}",
                ],
                [self.cmake, "--build", str(sdk_build), "--target", "install"],
                [
                    self.cmake, "-S", str(FIXTURE), "-B", str(consumer), "-G", "Ninja",
                    f"-DCMAKE_PREFIX_PATH={prefix}",
                    f"-DCMAKE_TOOLCHAIN_FILE={prefix / 'share/nrfkit/cmake/toolchains/arm-clang.cmake'}",
                    f"-DNRF_LLVM_ROOT={self.llvm_root}",
                    "-DCONTRACT_CASE=valid",
                ],
                [self.cmake, "--build", str(consumer)],
            ):
                result = subprocess.run(
                    argv, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout)

            # Reconfiguration of an installed consumer must also reject drift.
            header = prefix / "share/nrfkit/external/sdk-nrfxlib/mpsl/include/mpsl_timeslot.h"
            header.write_text(header.read_text() + "\n/* drift */\n")
            result = subprocess.run(
                [self.cmake, "--build", str(consumer)], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("hash mismatch: mpsl/include/mpsl_timeslot.h", result.stdout)

    def test_combined_cpp23_usb_sdc_timeslot_rram_consumer_links_offline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            environment = os.environ.copy()
            for name in (
                "NRF_CONNECT_SDK_ROOT", "WEST_TOPDIR", "ZEPHYR_BASE",
                "ZEPHYR_SDK_INSTALL_DIR",
            ):
                environment[name] = "/path/that/must/not/be/consulted"

            sdk_build = base / "sdk-build"
            prefix = base / "prefix"
            commands = [
                [
                    self.cmake, "-S", str(ROOT), "-B", str(sdk_build),
                    "-G", "Ninja", f"-DCMAKE_INSTALL_PREFIX={prefix}",
                ],
                [self.cmake, "--build", str(sdk_build), "--target", "install"],
            ]
            for usb_first, package_options in (
                (False, [f"-DNrfKit_DIR={ROOT / 'cmake'}",
                         f"-DCMAKE_TOOLCHAIN_FILE={ROOT / 'cmake/toolchains/arm-clang.cmake'}"]),
                (True, [f"-DCMAKE_PREFIX_PATH={prefix}",
                        f"-DCMAKE_TOOLCHAIN_FILE={prefix / 'share/nrfkit/cmake/toolchains/arm-clang.cmake'}"]),
            ):
                build = base / ("installed-usb-first" if usb_first else "source-sdc-first")
                commands.extend(([
                    self.cmake, "-S", str(COMBINED_FIXTURE), "-B", str(build),
                    "-G", "Ninja", f"-DNRF_LLVM_ROOT={self.llvm_root}",
                    f"-DCOMBINED_USB_FIRST={'ON' if usb_first else 'OFF'}",
                    *package_options,
                ], [self.cmake, "--build", str(build)]))

            for argv in commands:
                result = subprocess.run(
                    argv, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, env=environment, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout)

            for build in (base / "source-sdc-first", base / "installed-usb-first"):
                ninja_file = (build / "build.ninja").read_text(encoding="utf-8")
                self.assertIn("NRFKIT_USBHS_MPSL_CLOCK=1", ninja_file)
                link_map = (build / "contract.map").read_text(encoding="utf-8")
                self.assertIn("mpsl_clock_hfclk_src_request", link_map)
                self.assertIn("libsoftdevice_controller_multirole.a", link_map)

    def test_combined_target_rejects_nrfx_clock_irq_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([
                self.cmake, "-S", str(COMBINED_FIXTURE), "-B", directory,
                "-G", "Ninja", f"-DNrfKit_DIR={ROOT / 'cmake'}",
                f"-DCMAKE_TOOLCHAIN_FILE={ROOT / 'cmake/toolchains/arm-clang.cmake'}",
                f"-DNRF_LLVM_ROOT={self.llvm_root}", "-DCOMBINED_NRFX_CLOCK=ON",
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                check=False)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("cannot link the nrfx CLOCK driver", result.stdout)

    def test_all_controller_variants_reach_real_link_closure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for variant in ("multirole", "peripheral", "central"):
                build = base / variant
                configured = subprocess.run([
                    self.cmake, "-S", str(FIXTURE), "-B", str(build), "-G", "Ninja",
                    f"-DNrfKit_DIR={ROOT / 'cmake'}",
                    f"-DCMAKE_TOOLCHAIN_FILE={ROOT / 'cmake/toolchains/arm-clang.cmake'}",
                    f"-DNRF_LLVM_ROOT={self.llvm_root}",
                    "-DCONTRACT_CASE=valid",
                    f"-DCONTRACT_VARIANT={variant}",
                ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    check=False)
                self.assertEqual(configured.returncode, 0, configured.stdout)
                built = subprocess.run(
                    [self.cmake, "--build", str(build)], text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
                )
                self.assertEqual(built.returncode, 0, built.stdout)
                link_map = (build / "contract.map").read_text(encoding="utf-8")
                self.assertIn(f"libsoftdevice_controller_{variant}.a", link_map)
                self.assertIn("libmpsl_fem_common.a", link_map)
                self.assertIn("libmpsl.a", link_map)

    def test_validation_firmware_emits_guarded_hci_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            configured = subprocess.run([
                self.cmake, "-S", str(ROOT / "examples"), "-B", str(build),
                "-G", "Ninja", f"-DNrfKit_DIR={ROOT / 'cmake'}",
                f"-DCMAKE_TOOLCHAIN_FILE={ROOT / 'cmake/toolchains/arm-clang.cmake'}",
                f"-DNRF_LLVM_ROOT={self.llvm_root}",
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(configured.returncode, 0, configured.stdout)
            built = subprocess.run([
                self.cmake, "--build", str(build), "--target", "m6_sdc_validation",
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(built.returncode, 0, built.stdout)
            generated = subprocess.run([
                str(ROOT / "tools/nrfkit"), "sdk", "manifest",
                "--build-dir", str(build), "--target", "m6_sdc_validation",
                "--expected-token", "NRFKIT_M6_SDC", "--hci-h4-hwfc-1m",
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(generated.returncode, 0, generated.stdout)
            manifest = json.loads((
                build / "m6_sdc_validation.device-manifest.json"
            ).read_text(encoding="utf-8"))
            self.assertEqual(manifest["hci_transport"], {
                "type": "H4", "baud": 1000000, "hardware_flow_control": True,
            })
            self.assertEqual(manifest["build_evidence"]["status"], "ok")
            evidence = manifest["build_evidence"]
            self.assertEqual(len(evidence["map_sha256"]), 64)
            self.assertIn("radio0", evidence["resources"])
            self.assertGreater(evidence["elf_budget"]["rram_file_bytes"], 0)
            self.assertLessEqual(
                evidence["elf_budget"]["ram_total_reserved_bytes"],
                evidence["elf_budget"]["ram_capacity_bytes"],
            )
            self.assertEqual(evidence["elf_budget"]["stack_reserved_bytes"], 0x4000)
            link_map = (build / "m6_sdc_validation.map").read_text(encoding="utf-8")
            for symbol in (
                "nrfkit_sdc_hci_command", "RADIO_0_IRQHandler",
                "TIMER10_IRQHandler", "GRTC_3_IRQHandler", "SWI00_IRQHandler",
                "mpsl_low_latency_acquire_callback",
                "mpsl_low_latency_release_callback",
                "mpsl_assert", "controller_fault", "nrfkit_sdc_last_fault",
                "controller_region",
            ):
                self.assertIn(symbol, link_map)


if __name__ == "__main__":
    unittest.main()
