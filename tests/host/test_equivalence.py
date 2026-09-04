# SPDX-License-Identifier: BSD-3-Clause

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from nrfkit_tools.equivalence import EquivalenceContractError, audit_equivalence


class EquivalenceTests(unittest.TestCase):
    def test_bm_port_preserves_official_application_init_order(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        header = (project_root / "include/nrfkit/bm_port.h").read_text(
            encoding="utf-8"
        )
        port = (project_root / "softdevice/nrf54l/bm_port.c").read_text(
            encoding="utf-8"
        )
        cmake = (project_root / "cmake/modules/NrfKitFirmware.cmake").read_text(
            encoding="utf-8"
        )
        verifier = (
            project_root / "cmake/VerifyNrfBmInitOrder.cmake"
        ).read_text(encoding="utf-8")

        expected_order = (
            "NRFKIT_BM_BOARD_INIT_PRIORITY 101",
            "NRFKIT_BM_SYS_INIT_PRIORITY_bm_gpiote_init 201",
            "NRFKIT_BM_SYS_INIT_PRIORITY_bm_timer_sys_init 202",
            "NRFKIT_BM_SYS_INIT_PRIORITY_sd_irq_init 203",
            "NRFKIT_BM_SYS_INIT_PRIORITY_irq_init 204",
        )
        positions = [header.index(value) for value in expected_order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("constructor(NRFKIT_BM_BOARD_INIT_PRIORITY)", port)
        self.assertNotIn("nrfkit_nrf_bm_irq_init", cmake)
        self.assertNotIn(
            'string(REPLACE "SYS_INIT(irq_init, APPLICATION, 0);"', cmake
        )
        self.assertIn("adapter=9", cmake)
        for value in (".init_array.101", ".init_array.201", ".init_array.202",
                      ".init_array.203", ".init_array.204",
                      "CallSoftDeviceResetHandler"):
            self.assertIn(value, verifier)
        self.assertIn("VerifyNrfBmInitOrder.cmake", cmake)

    def test_bm_log_uses_one_ram_backed_uarte_transaction_per_line(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        source = (project_root / "softdevice/nrf54l/bm_port.c").read_text(
            encoding="utf-8"
        )

        self.assertIn("static uint8_t log_buffer", source)
        self.assertEqual(source.count("TASKS_DMA.TX.START"), 1)
        self.assertNotIn("for (const char *cursor", source)
        self.assertNotIn("__WFE();", source)
        self.assertIn("UARTE_SHORTS_DMA_TX_END_DMA_TX_STOP_Msk", source)
        self.assertIn("EVENTS_TXSTOPPED", source)
        self.assertIn("EVENTS_DMA.TX.BUSERROR", source)

    def test_stopped_checkpoint_keeps_exact_adapter_inputs(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        checkpoint = json.loads(
            (project_root / "docs/provenance/m6-s115-equivalence-checkpoint.json")
            .read_text(encoding="utf-8")
        )
        inputs = checkpoint["lifecycle_candidate"]["adapter_inputs"]
        for relative, expected in inputs.items():
            actual = hashlib.sha256((project_root / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, relative)

    def test_update_and_check_use_portable_paths_and_detect_drift(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source_root = root / "sdk"
            build_root = root / "build"
            source = source_root / "nrf-bm/src/main.c"
            generated = build_root / "zephyr/generated.c"
            autoconf = build_root / "zephyr/include/generated/zephyr/autoconf.h"
            for path, text in (
                (source, "int main(void) { return 0; }\n"),
                (generated, "int generated;\n"),
                (autoconf, "#define CONFIG_TEST 1\n"),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            compile_commands = build_root / "compile_commands.json"
            compile_commands.write_text(json.dumps([
                {"file": str(source), "command": f"cc -I{source_root}/include -c {source}"},
                {"file": str(generated), "arguments": ["cc", "-c", str(generated)]},
            ]), encoding="utf-8")
            receipt = root / "receipt.json"
            config = root / "config.h"
            value = audit_equivalence(
                source_root, build_root, compile_commands, autoconf, receipt, config,
                update=True,
            )
            self.assertEqual(value["nrf_bm_sources"], ["nrf-bm/src/main.c"])
            self.assertNotIn(str(root), receipt.read_text(encoding="utf-8"))
            audit_equivalence(
                source_root, build_root, compile_commands, autoconf, receipt, config,
            )
            config.write_text("#define CONFIG_TEST 2\n", encoding="utf-8")
            with self.assertRaisesRegex(EquivalenceContractError, "static compatibility"):
                audit_equivalence(
                    source_root, build_root, compile_commands, autoconf, receipt, config,
                )


if __name__ == "__main__":
    unittest.main()
