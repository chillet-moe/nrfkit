# SPDX-License-Identifier: BSD-3-Clause

import json
import sys
import tempfile
import unittest
from pathlib import Path

from nrf_cmake_tools.process import atomic_json, run_logged


class ProcessTests(unittest.TestCase):
    def test_atomic_json_replaces_complete_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.json"
            atomic_json(path, {"status": "ok"})
            self.assertEqual(json.loads(path.read_text()), {"status": "ok"})
            self.assertEqual(list(path.parent.glob(f".{path.name}.*")), [])

    def test_timeout_terminates_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_logged(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                Path(directory) / "process.log",
                timeout=0.1,
            )
            self.assertTrue(result.timed_out)
            self.assertEqual(result.returncode, 124)


if __name__ == "__main__":
    unittest.main()
