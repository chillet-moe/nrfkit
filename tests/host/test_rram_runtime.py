# SPDX-License-Identifier: BSD-3-Clause
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[2]

class RramRuntimeTests(unittest.TestCase):
    def test_grants_bounds_failures_and_session_cleanup(self):
        compiler = shutil.which('cc')
        if not compiler:
            self.skipTest('host C compiler required')
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'rram-test'
            command = [compiler, '-std=c11', '-Wall', '-Wextra', '-Werror',
                       '-Wno-unused-parameter',
                       f'-I{ROOT / "src/runtime"}',
                       f'-I{ROOT / "tests/host/rram_stubs"}',
                       f'-I{ROOT / "tests/host/timeslot_stubs"}',
                       f'-I{ROOT / "include"}',
                       f'-I{ROOT / "src/wireless/include"}',
                       f'-I{ROOT / "external/sdk-nrfxlib/mpsl/include"}',
                       str(ROOT / 'tests/host/rram_runtime.c'), '-o', str(executable)]
            for argv in (command, [str(executable)]):
                result = subprocess.run(argv, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
