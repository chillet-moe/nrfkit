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

            sdk_root = prefix / "share/nrfkit"
            for source in (ROOT / "src").rglob("*"):
                if source.is_file():
                    relative = source.relative_to(ROOT)
                    self.assertTrue((sdk_root / relative).is_file(), str(relative))
            for obsolete in ("boards", "runtime", "softdevice", "radio", "usb"):
                self.assertFalse((sdk_root / obsolete).exists(), obsolete)
            self.assertTrue((sdk_root / "include/nrfkit/usbhs.h").is_file())
            installed_vendor = sdk_root / "external"
            for required in (
                "nrfx/nrfx.h", "nrfx/drivers/src/nrfx_rramc.c",
                "nrfx/bsp/stable/mdk/nrf54l/system_nrf54l.c",
                "cherryusb/core/usbd_core.c",
                "cherryusb/port/dwc2/usb_dc_dwc2.c",
                "cherryusb/class/hid/usbd_hid.c",
            ):
                self.assertTrue((installed_vendor / required).is_file(), required)
            for required in (
                "reference.cmake", "usb_config.h.in",
            ):
                self.assertTrue(
                    (sdk_root / "examples/common/usb" / required).is_file(), required
                )
            self.assertTrue((prefix / "include/nrfkit/mpsl.h").is_file())
            saw_usb_port = False
            for cmake_file in prefix.rglob("*.cmake"):
                cmake_text = cmake_file.read_text(encoding="utf-8")
                saw_usb_port = saw_usb_port or "NrfKit::usb_port" in cmake_text
                self.assertNotIn("NrfKit::usb_device", cmake_text, str(cmake_file))
                self.assertNotIn("nrfkit_configure_usb", cmake_text, str(cmake_file))
            self.assertTrue(saw_usb_port)
            selected_nrfx = (ROOT / "cmake/nrfx-selection.txt").read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertEqual(set(selected_nrfx), {
                path.relative_to(installed_vendor / "nrfx").as_posix()
                for path in (installed_vendor / "nrfx").rglob("*") if path.is_file()
            })
            selected_cmsis = (ROOT / "cmake/cmsis-selection.txt").read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertEqual(set(selected_cmsis), {
                path.relative_to(installed_vendor / "cmsis").as_posix()
                for path in (installed_vendor / "cmsis").rglob("*") if path.is_file()
            })
            for excluded in (
                "../third_party", "nrfx/bsp/stable/mdk/nrf51", "nrfx/doc",
                "cherryusb/.github", "cherryusb/demo",
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

            # Changing the selection must regenerate the prepared view even when
            # the upstream revision and patches are unchanged.
            cache_source = temporary / "cache-consumer"
            cache_source.mkdir()
            (cache_source / "CMakeLists.txt").write_text(
                'cmake_minimum_required(VERSION 3.25)\n'
                'project(cache_contract LANGUAGES NONE)\n'
                'include("${NrfKit_MODULE_DIR}/NrfKitNrfx.cmake")\n'
                '_nrfkit_prepare_nrfx(prepared)\n'
                'file(WRITE "${CMAKE_BINARY_DIR}/prepared.txt" "${prepared}")\n'
            )
            cache_build = temporary / "cache-build"
            self.run_command([
                cmake, "-S", str(cache_source), "-B", str(cache_build), "-G", "Ninja",
                f"-DNrfKit_ROOT={sdk_root}",
                f"-DNrfKit_MODULE_DIR={prefix / 'lib/cmake/NrfKit/modules'}",
            ], environment)
            prepared = Path((cache_build / "prepared.txt").read_text())
            self.assertEqual(set(selected_nrfx), {
                path.relative_to(prepared).as_posix() for path in prepared.rglob("*")
                if path.is_file() and path.name != ".nrfkit-prepared"
            })
            marker = (prepared / ".nrfkit-prepared").read_text()
            probe = "selection-probe.h"
            (installed_vendor / "nrfx" / probe).write_text("/* cache probe */\n")
            selection = sdk_root / "cmake/nrfx-selection.txt"
            selection.write_text(selection.read_text() + probe + "\n")
            self.run_command([cmake, "--build", str(cache_build)], environment)
            self.assertTrue((prepared / probe).is_file())
            self.assertNotEqual(marker, (prepared / ".nrfkit-prepared").read_text())


if __name__ == "__main__":
    unittest.main()
