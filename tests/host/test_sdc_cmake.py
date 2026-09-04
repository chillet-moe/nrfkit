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

    def configure(self, directory: Path, case: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([
            self.cmake, "-S", str(FIXTURE), "-B", str(directory), "-G", "Ninja",
            f"-DNrfKit_DIR={ROOT / 'cmake'}",
            f"-DCMAKE_TOOLCHAIN_FILE={ROOT / 'cmake/toolchains/arm-clang.cmake'}",
            f"-DNRF_LLVM_ROOT={self.llvm_root}",
            f"-DCONTRACT_CASE={case}",
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)

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
            ):
                self.assertIn(symbol, link_map)


if __name__ == "__main__":
    unittest.main()
