# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import os
from pathlib import Path
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
                f"-DNrfCMakeSdk_DIR={ROOT / 'cmake'}",
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

            installed_build = temporary / "installed-consumer"
            self.run_command([
                cmake, "-S", str(CONSUMER), "-B", str(installed_build), "-G", "Ninja",
                f"-DCMAKE_PREFIX_PATH={prefix}",
            ], environment)
            self.run_command([cmake, "--build", str(installed_build)], environment)


if __name__ == "__main__":
    unittest.main()
