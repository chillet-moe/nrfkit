# SPDX-License-Identifier: BSD-3-Clause

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nrfkit_tools.process import ProcessResult
from nrfkit_tools.reference import (
    ReferenceContractError, _verify_build_evidence, build,
    official_toolchain_compiler,
)


class ReferenceBuildTests(unittest.TestCase):
    def test_sdc_oracle_requires_locked_multirole_and_mpsl_link_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            build_dir = Path(directory)
            zephyr = build_dir / "zephyr"
            zephyr.mkdir()
            config = zephyr / ".config"
            config.write_text(
                "CONFIG_BT_LL_SOFTDEVICE=y\nCONFIG_MPSL=y\n"
                "CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT=1\n"
                "CONFIG_BT_CTLR_SDC_CENTRAL_COUNT=1\n",
                encoding="utf-8",
            )
            link = zephyr / "linker.cmd"
            link.write_text(
                "/locked/nrfxlib/softdevice_controller/lib/nrf54lm/hard-float/"
                "libsoftdevice_controller_multirole.a "
                "/locked/nrfxlib/mpsl/lib/nrf54lm/hard-float/libmpsl.a\n",
                encoding="utf-8",
            )
            contract = {
                "build_evidence": {
                    "config": "zephyr/.config",
                    "config_markers": [
                        "CONFIG_BT_LL_SOFTDEVICE=y", "CONFIG_MPSL=y",
                        "CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT=1",
                        "CONFIG_BT_CTLR_SDC_CENTRAL_COUNT=1",
                    ],
                    "link_file": "zephyr/linker.cmd",
                    "link_markers": [
                        "softdevice_controller/lib/nrf54lm/hard-float/libsoftdevice_controller_multirole.a",
                        "mpsl/lib/nrf54lm/hard-float/libmpsl.a",
                    ],
                    "forbidden_link_markers": [
                        "libsoftdevice_controller_peripheral.a",
                        "libsoftdevice_controller_central.a",
                        "libsoftdevice_controller_ll_sw_split.a",
                    ],
                    "text_files": [{
                        "path": "zephyr/isr_tables.c",
                        "markers": [
                            "z_irq_spurious}, /* 75 */",
                            "z_irq_spurious}, /* 202 */",
                        ],
                    }],
                }
            }
            isr_table = zephyr / "isr_tables.c"
            isr_table.write_text(
                "z_irq_spurious}, /* 75 */\nz_irq_spurious}, /* 202 */\n",
                encoding="utf-8",
            )
            evidence = _verify_build_evidence(build_dir, contract)
            self.assertEqual(evidence["status"], "ok")
            link.write_text(
                link.read_text(encoding="utf-8")
                + "libsoftdevice_controller_peripheral.a\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ReferenceContractError, "forbidden link marker"):
                _verify_build_evidence(build_dir, contract)
            link.write_text(
                "/locked/nrfxlib/softdevice_controller/lib/nrf54lm/hard-float/"
                "libsoftdevice_controller_multirole.a "
                "/locked/nrfxlib/mpsl/lib/nrf54lm/hard-float/libmpsl.a\n",
                encoding="utf-8",
            )
            isr_table.write_text("z_irq_spurious}, /* 75 */\n", encoding="utf-8")
            with self.assertRaisesRegex(ReferenceContractError, "required text marker"):
                _verify_build_evidence(build_dir, contract)

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
