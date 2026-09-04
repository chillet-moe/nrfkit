# SPDX-License-Identifier: BSD-3-Clause

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from nrfkit_tools.equivalence import EquivalenceContractError, audit_equivalence


class EquivalenceTests(unittest.TestCase):
    def test_stopped_checkpoint_keeps_exact_adapter_inputs(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        checkpoint = json.loads(
            (project_root / "docs/provenance/m6-s115-equivalence-checkpoint.json")
            .read_text(encoding="utf-8")
        )
        inputs = checkpoint["pure_cmake_consumer"]["adapter_inputs"]
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
