# SPDX-License-Identifier: BSD-3-Clause

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nrfkit_tools.process import ProcessResult
from nrfkit_tools.reference import (
    ReferenceContractError, build, official_toolchain_compiler,
)


class ReferenceBuildTests(unittest.TestCase):
    def test_official_toolchain_compiler_supports_both_sdk_layouts(self) -> None:
        for variant, relative in (
            ("zephyr", "opt/zephyr-sdk/arm-zephyr-eabi/bin/arm-zephyr-eabi-gcc"),
            ("zephyr/gnu", "opt/zephyr-sdk/gnu/arm-zephyr-eabi/bin/arm-zephyr-eabi-gcc"),
        ):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                compiler = root / relative
                compiler.parent.mkdir(parents=True)
                compiler.touch()
                self.assertEqual(official_toolchain_compiler(root), (variant, compiler))

    def test_missing_receipt_still_finalizes_run_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            with self.assertRaises(ReferenceContractError):
                build(project, "missing", 10)
            reports = list((project / ".work/runs").glob("*/run.json"))
            self.assertEqual(len(reports), 1)
            report = json.loads(reports[0].read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "failed")
            self.assertIn("source receipt", report["error"])

    def test_manifest_failure_finalizes_run_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            receipt = project / ".work/reference/sources/oracle.json"
            receipt.parent.mkdir(parents=True)
            receipt.write_text("{}\n", encoding="utf-8")
            contract = {"sample": "sample", "board": "board"}
            with (
                mock.patch(
                    "nrfkit_tools.reference.load_receipt",
                    return_value=(project / "source", project / "toolchain", {
                        "toolchain_variant": "zephyr",
                    }),
                ),
                mock.patch("nrfkit_tools.reference.oracle", return_value=contract),
                mock.patch(
                    "nrfkit_tools.reference.run_logged",
                    return_value=ProcessResult(0, False, 0.1, "built"),
                ),
                mock.patch(
                    "nrfkit_tools.reference._build_manifest",
                    side_effect=ReferenceContractError("invalid runner metadata"),
                ),
            ):
                with self.assertRaisesRegex(ReferenceContractError, "runner metadata"):
                    build(project, "oracle", 10)
            reports = list((project / ".work/runs").glob("*/run.json"))
            self.assertEqual(len(reports), 1)
            report = json.loads(reports[0].read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "failed")
            self.assertIn("invalid runner metadata", report["error"])


if __name__ == "__main__":
    unittest.main()
