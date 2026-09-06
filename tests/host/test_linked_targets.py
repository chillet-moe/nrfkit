# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/consumer/linked-targets"


class LinkedTargetTests(unittest.TestCase):
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
        cls.tmp_root = ROOT / ".work/link-targets/tmp"
        cls.tmp_root.mkdir(parents=True, exist_ok=True)

    def run_cmake(self, build: Path, case: str, build_target: bool = True, config: str = "Release"):
        result = subprocess.run([
            self.cmake, "-S", str(FIXTURE), "-B", str(build), "-G", "Ninja",
            f"-DNrfKit_DIR={ROOT / 'cmake'}",
            f"-DCMAKE_TOOLCHAIN_FILE={ROOT / 'cmake/toolchains/arm-clang.cmake'}",
            f"-DNRF_LLVM_ROOT={self.llvm_root}", f"-DLINKED_CASE={case}",
            f"-DCMAKE_BUILD_TYPE={config}",
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        if result.returncode == 0 and build_target:
            result = subprocess.run(
                [self.cmake, "--build", str(build)], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
        result.stdout = "\n".join(result.stdout.splitlines()[-30:])
        return result

    def test_direct_and_transitive_targets_reach_real_link_closure(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.tmp_root) as directory:
            base = Path(directory)
            for case in ("direct", "transitive-serial"):
                result = self.run_cmake(base / case, case)
                self.assertEqual(result.returncode, 0, result.stdout)
                link_map = (base / case / "linked_firmware.map").read_text()
                ninja = (base / case / "build.ninja").read_text()
                self.assertIn("nrfx_timer.c", link_map)
                self.assertIn("nrfx_uarte.c", link_map)
                self.assertIn("nrfx_prs.c", link_map)
                self.assertIn("/_shared/nrfkit/nrfx-", ninja)
                self.assertNotIn("external/nrfx/drivers/src", ninja)

    def test_supported_wireless_and_usb_targets_link_in_isolated_builds(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.tmp_root) as directory:
            base = Path(directory)
            for case in ("sdc-multirole", "sdc-peripheral", "sdc-central",
                         "radio-direct", "radio-timeslot", "rram",
                         "usb-port", "usb-default", "custom-port"):
                with self.subTest(case=case):
                    result = self.run_cmake(base / case, case)
                    self.assertEqual(result.returncode, 0, result.stdout)
                    link_map = (base / case / "linked_firmware.map").read_text()
                    self.assertIn("nrfkit", link_map.lower())
                    if case.startswith("sdc-"):
                        archive = "libsoftdevice_controller_" + case[4:] + ".a"
                        self.assertIn(archive, (base / case / "build.ninja").read_text())
                    if case == "custom-port":
                        custom_ninja = (base / case / "build.ninja").read_text()
                        self.assertIn("custom_usb.c", custom_ninja)
                        self.assertNotIn("/src/usb/", custom_ninja)

    def test_usb_images_keep_target_local_fifo_configuration(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.tmp_root) as directory:
            build = Path(directory) / "usb-dual"
            result = self.run_cmake(build, "usb-dual")
            self.assertEqual(result.returncode, 0, result.stdout)
            configs = sorted(build.rglob("usb_config.h"))
            self.assertEqual(len(configs), 2)
            contents = [path.read_text() for path in configs]
            self.assertTrue(any("{ 16, 16, 32," in content for content in contents))
            self.assertTrue(any("{ 16, 64, 128," in content for content in contents))
            ninja = (build / "build.ninja").read_text()
            self.assertGreaterEqual(ninja.count("external/cherryusb/core/usbd_core.c"), 2)

    def test_multiple_firmware_targets_keep_configuration_isolated(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.tmp_root) as directory:
            base = Path(directory)
            result = self.run_cmake(base / "multiple", "multiple")
            self.assertEqual(result.returncode, 0, result.stdout)
            gpio_map = (base / "multiple/linked_firmware.map").read_text()
            radio_map = (base / "multiple/linked_radio.map").read_text()
            self.assertIn("nrfx_timer.c", gpio_map)
            self.assertIn("nrfx_uarte.c", gpio_map)
            self.assertNotIn("radio.c", gpio_map)
            self.assertIn("radio.c", radio_map)
            self.assertNotIn("nrfx_timer.c", radio_map)

    def test_native_conditional_links_select_only_the_active_capability(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.tmp_root) as directory:
            for config in ("Debug", "Release"):
                build = Path(directory) / config
                result = self.run_cmake(build, "native-conditional", config=config)
                self.assertEqual(result.returncode, 0, result.stdout)
                ninja = (build / "build.ninja").read_text()
                self.assertEqual("NRFKIT_SDC_ENABLED=1" in ninja, config == "Debug")
                self.assertEqual("NRFX_CLOCK_ENABLED=1" in ninja, config == "Release")

    def test_resource_masks_accumulate_and_remain_per_firmware(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.tmp_root) as directory:
            result = self.run_cmake(Path(directory), "resource-masks")
            self.assertEqual(result.returncode, 0, result.stdout)

    def test_native_composition_rejects_incompatible_or_missing_dependencies(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.tmp_root) as directory:
            for case, expected in (
                ("conflict-sdc-variants", "NRFKIT_SDC_VARIANT"),
                ("conflict-direct-radio", "NRFKIT_RADIO_MODE"),
                ("conflict-clock", "NRFKIT_CLOCK_OWNER"),
                ("missing-sdc-rram", "requires an explicit SDC"),
            ):
                with self.subTest(case=case):
                    result = self.run_cmake(Path(directory) / case, case)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn(expected, result.stdout)

if __name__ == "__main__":
    unittest.main()
