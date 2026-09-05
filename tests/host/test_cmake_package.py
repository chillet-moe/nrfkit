# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CONSUMER = ROOT / "tests/consumer/minimal"


class CMakePackageTests(unittest.TestCase):
    def run_command(self, argv: list[str], environment: dict[str, str]) -> None:
        result = subprocess.run(
            argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=environment, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_source_and_installed_packages_configure_offline(self) -> None:
        cmake = shutil.which("cmake")
        ninja = shutil.which("ninja")
        if cmake is None or ninja is None:
            self.skipTest("CMake and Ninja are required")
        environment = os.environ.copy()
        version_header = (ROOT / "include/nrfkit/version.h").read_text(encoding="utf-8")
        components = [
            re.search(rf"NRFKIT_VERSION_{name}\s+(\d+)", version_header).group(1)
            for name in ("MAJOR", "MINOR", "PATCH")
        ]
        numeric_version = ".".join(components)
        full_version = re.search(
            r'NRFKIT_VERSION_STRING\s+"([^"]+)"', version_header,
        ).group(1)
        version_options = [
            f"-DNRFKIT_EXPECTED_VERSION={numeric_version}",
            f"-DNRFKIT_EXPECTED_VERSION_STRING={full_version}",
        ]
        for name in (
            "NRF_CONNECT_SDK_ROOT", "WEST_TOPDIR", "ZEPHYR_BASE",
            "ZEPHYR_SDK_INSTALL_DIR",
        ):
            environment[name] = "/path/that/must/not/be/consulted"
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            source_build = temporary / "source-consumer"
            self.run_command([
                cmake, "-S", str(CONSUMER), "-B", str(source_build), "-G", "Ninja",
                f"-DNrfKit_DIR={ROOT / 'cmake'}",
                *version_options,
            ], environment)
            self.run_command([cmake, "--build", str(source_build)], environment)

            sdk_build = temporary / "sdk-build"
            prefix = temporary / "prefix"
            self.run_command([
                cmake, "-S", str(ROOT), "-B", str(sdk_build), "-G", "Ninja",
                f"-DCMAKE_INSTALL_PREFIX={prefix}",
            ], environment)
            self.run_command([
                cmake, "--build", str(sdk_build), "--target", "install",
            ], environment)

            installed_vendor = prefix / "share/nrfkit/external"
            for required in (
                "nrfx/nrfx.h", "nrfx/drivers/src/nrfx_rramc.c",
                "nrfx/bsp/stable/mdk/nrf54l/system_nrf54l.c",
                "cherryusb/core/usbd_core.c",
                "cherryusb/port/dwc2/usb_dc_dwc2.c",
                "cherryusb/class/hid/usbd_hid.c",
            ):
                self.assertTrue((installed_vendor / required).is_file(), required)
            for excluded in (
                "nrfx/doc", "cherryusb/.github", "cherryusb/demo",
                "cherryusb/third_party", "cherryusb/tools", "cherryusb/zephyr",
                "cherryusb/Kconfig",
            ):
                self.assertFalse((installed_vendor / excluded).exists(), excluded)

            installed_build = temporary / "installed-consumer"
            self.run_command([
                cmake, "-S", str(CONSUMER), "-B", str(installed_build), "-G", "Ninja",
                f"-DCMAKE_PREFIX_PATH={prefix}",
                *version_options,
            ], environment)
            self.run_command([cmake, "--build", str(installed_build)], environment)


if __name__ == "__main__":
    unittest.main()
