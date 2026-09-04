# SPDX-License-Identifier: BSD-3-Clause

import hashlib
import json
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = ROOT / "external/sdk-nrfxlib"
CONTRACT_PATH = ROOT / "docs/provenance/m6-sdc-mpsl-contract.json"


def tree_digest(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        relative = path.relative_to(UPSTREAM).as_posix()
        file_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        digest.update(f"{relative}\0{file_digest}\n".encode())
    return digest.hexdigest()


class NrfxlibContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_contract_covers_locked_documentation_headers_and_licenses(self) -> None:
        sets = {
            "sdc_headers": sorted((UPSTREAM / "softdevice_controller/include").rglob("*.h")),
            "mpsl_headers": sorted((UPSTREAM / "mpsl/include").rglob("*.h")),
            "sdc_docs": sorted([
                UPSTREAM / "softdevice_controller/README.rst",
                UPSTREAM / "softdevice_controller/CHANGELOG.rst",
                UPSTREAM / "softdevice_controller/limitations.rst",
                *(UPSTREAM / "softdevice_controller/doc").glob("*.rst"),
            ]),
            "mpsl_docs": sorted([
                UPSTREAM / "mpsl/README.rst",
                UPSTREAM / "mpsl/CHANGELOG.rst",
                *(UPSTREAM / "mpsl/doc").glob("*.rst"),
            ]),
            "licenses": sorted([
                UPSTREAM / "LICENSE",
                UPSTREAM / "softdevice_controller/license.txt",
                UPSTREAM / "mpsl/license.txt",
                UPSTREAM / "mpsl/LICENSE-ATTRIBUTION.txt",
            ]),
        }
        reviews = self.contract["reviewed_input_sets"]
        self.assertEqual(set(reviews), set(sets))
        for name, paths in sets.items():
            self.assertEqual(reviews[name]["file_count"], len(paths), name)
            self.assertEqual(reviews[name]["tree_sha256"], tree_digest(paths), name)

    def test_every_requirement_has_a_live_source_anchor(self) -> None:
        ids = set()
        for requirement in self.contract["requirements"]:
            self.assertRegex(requirement["id"], r"^(MPSL|SDC)-[A-Z]+-[0-9]{2}$")
            self.assertNotIn(requirement["id"], ids)
            ids.add(requirement["id"])
            self.assertIn(requirement["category"], {
                "resource", "interrupt", "clock", "memory", "lifecycle",
                "context", "callback", "fault", "hci", "link",
            })
            self.assertTrue(requirement["verification"])
            for source in requirement["sources"]:
                path = UPSTREAM / source["path"]
                text = path.read_text(encoding="utf-8")
                self.assertIn(source["anchor"], text, requirement["id"])

    def test_lm20_resource_masks_match_public_headers(self) -> None:
        expected = self.contract["lm20_resources"]["channel_masks"]
        headers = "\n".join([
            (UPSTREAM / "mpsl/include/mpsl_hwres.h").read_text(encoding="utf-8"),
            (UPSTREAM / "softdevice_controller/include/sdc_soc.h").read_text(encoding="utf-8"),
        ])
        for macro, value in expected.items():
            match = re.search(rf"#define\s+{re.escape(macro)}\s+\((0x[0-9a-fA-F]+)\)", headers)
            self.assertIsNotNone(match, macro)
            self.assertEqual(int(match.group(1), 16), int(value, 16), macro)

    def test_contract_identity_and_vectors_match_locked_inputs(self) -> None:
        lock = json.loads(
            (ROOT / "docs/provenance/sources.lock").read_text(encoding="utf-8")
        )["audited_sources"]["sdk-nrfxlib-3.4.0"]
        identity = self.contract["source"]
        for key in (
            "release", "commit", "binary_manifest_revision", "target",
            "security_domain", "float_abi",
        ):
            self.assertEqual(identity[key], lock[key], key)

        device_header = (
            ROOT / "third_party/nrfx/mdk/nrf54l/nrf54lm20a/"
            "nrf54lm20a_application.h"
        ).read_text(encoding="utf-8")
        vectors = self.contract["lm20_resources"]["interrupts"]["vectors"]
        for name, number in vectors.items():
            self.assertRegex(
                device_header,
                rf"\b{re.escape(name)}\s*=\s*{number}\s*,",
                name,
            )
        low = self.contract["lm20_resources"]["interrupts"][
            "official_low_priority_default"
        ]
        self.assertRegex(
            device_header,
            rf"\b{re.escape(low['name'])}\s*=\s*{low['number']}\s*,",
        )

    def test_archive_abi_and_public_link_closure(self) -> None:
        readelf = "/usr/sbin/arm-none-eabi-readelf"
        nm = "/usr/sbin/arm-none-eabi-nm"
        for archive in self.contract["archives"]:
            path = UPSTREAM / archive["path"]
            attributes = subprocess.run(
                [readelf, "-A", str(path)], text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, check=False,
            )
            self.assertEqual(attributes.returncode, 0, attributes.stdout)
            for marker in archive["required_elf_attributes"]:
                self.assertIn(marker, attributes.stdout, archive["path"])
            undefined = subprocess.run(
                [nm, "--undefined-only", str(path)], text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, check=False,
            )
            self.assertEqual(undefined.returncode, 0, undefined.stdout)
            public = {
                line.split()[-1] for line in undefined.stdout.splitlines()
                if line.strip() and not line.split()[-1].startswith("sym_")
                and not line.rstrip().endswith(":")
            }
            self.assertEqual(public, set(archive["public_undefined_symbols"]), archive["path"])


if __name__ == "__main__":
    unittest.main()
