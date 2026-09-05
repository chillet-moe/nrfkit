# SPDX-License-Identifier: BSD-3-Clause

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class TimeslotRuntimeTests(unittest.TestCase):
    def test_request_failure_preserves_grant_and_allows_idle_retry(self) -> None:
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("host C compiler required")
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "timeslot-test"
            result = subprocess.run([
                compiler, "-std=c11", "-Wall", "-Wextra",
                "-Wno-unused-parameter", "-Werror",
                f"-I{ROOT / 'tests/host/timeslot_stubs'}",
                f"-I{ROOT / 'include'}",
                f"-I{ROOT / 'external/sdk-nrfxlib/mpsl/include'}",
                str(ROOT / "tests/host/timeslot_runtime.c"),
                "-o", str(executable),
            ], text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run(
                [str(executable)], text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
