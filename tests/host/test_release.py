# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
VERSION_HEADER = ROOT / "include/nrfkit/version.h"


def _version() -> tuple[str, str]:
    header = VERSION_HEADER.read_text(encoding="utf-8")
    components = [
        re.search(rf"NRFKIT_VERSION_{name}\s+(\d+)", header).group(1)
        for name in ("MAJOR", "MINOR", "PATCH")
    ]
    full = re.search(
        r'NRFKIT_VERSION_STRING\s+"([^"]+)"', header,
    ).group(1)
    return ".".join(components), full


class ReleaseTests(unittest.TestCase):
    def run_command(
        self, argv: list[str], environment: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=environment, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        return result

    def test_release_metadata_matches_version_header(self) -> None:
        numeric, full = _version()
        self.assertEqual(numeric, "0.1.0")
        self.assertEqual(full, "0.1.0-rc.2")
        sbom = json.loads(
            (ROOT / "docs/provenance/sbom.spdx.json").read_text(encoding="utf-8")
        )
        package = next(
            item for item in sbom["packages"] if item["name"] == "nrfkit"
        )
        self.assertEqual(package["versionInfo"], full)
        self.assertIn(f"nrfkit-{full}-", sbom["documentNamespace"])

    def test_release_archive_is_reproducible_and_consumable_offline(self) -> None:
        cmake = shutil.which("cmake")
        ninja = shutil.which("ninja")
        if cmake is None or ninja is None:
            self.skipTest("CMake and Ninja are required")
        numeric, full = _version()
        environment = os.environ.copy()
        environment["SOURCE_DATE_EPOCH"] = "946684800"
        for name in (
            "NRF_CONNECT_SDK_ROOT", "WEST_TOPDIR", "ZEPHYR_BASE",
            "ZEPHYR_SDK_INSTALL_DIR",
        ):
            environment[name] = "/path/that/must/not/be/consulted"

        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            archives: list[Path] = []
            for index in range(2):
                build = temporary / f"package-build-{index}"
                self.run_command([
                    cmake, "-S", str(ROOT), "-B", str(build), "-G", "Ninja",
                ], environment)
                self.run_command([
                    cmake, "--build", str(build), "--target", "package",
                ], environment)
                archive = build / f"nrfkit-{full}.tar.gz"
                self.assertTrue(archive.is_file(), archive)
                self.assertTrue(Path(f"{archive}.sha256").is_file())
                archives.append(archive)

            digests = [
                hashlib.sha256(path.read_bytes()).hexdigest() for path in archives
            ]
            self.assertEqual(digests[0], digests[1])

            with tarfile.open(archives[0], "r:gz") as release:
                names = set(release.getnames())
                prefix = f"nrfkit-{full}"
                for required in (
                    "include/nrfkit/version.h",
                    "lib/cmake/NrfKit/NrfKitConfig.cmake",
                    "share/doc/nrfkit/LICENSE",
                    "share/doc/nrfkit/README.md",
                    "share/doc/nrfkit/CHANGELOG.md",
                    "share/nrfkit/external/nrfx/nrfx.h",
                    "share/nrfkit/external/cherryusb/core/usbd_core.c",
                    "share/nrfkit/external/sdk-nrfxlib/mpsl/lib/nrf54lm/hard-float/libmpsl.a",
                ):
                    self.assertIn(f"{prefix}/{required}", names, required)
                release.extractall(temporary / "unpacked", filter="data")

            consumer_build = temporary / "consumer-build"
            self.run_command([
                cmake,
                "-S", str(ROOT / "tests/consumer/minimal"),
                "-B", str(consumer_build),
                "-G", "Ninja",
                f"-DCMAKE_PREFIX_PATH={temporary / 'unpacked' / f'nrfkit-{full}'}",
                f"-DNRFKIT_EXPECTED_VERSION={numeric}",
                f"-DNRFKIT_EXPECTED_VERSION_STRING={full}",
            ], environment)
            self.run_command([
                cmake, "--build", str(consumer_build),
            ], environment)


if __name__ == "__main__":
    unittest.main()
