# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ProvenanceTests(unittest.TestCase):
    def test_audited_sources_have_reproducible_identity(self) -> None:
        lock = json.loads(
            (ROOT / "docs/provenance/sources.lock").read_text(encoding="utf-8")
        )
        self.assertEqual(lock["schema"], "nrf-cmake-sdk-sources/v1")
        self.assertEqual(
            set(lock["audited_sources"]),
            {
                "nrfx-4.5.0", "nrf-device-family-pack-8.44.1",
                "trusted-firmware-m-ncs-3.4.0", "s115-10.0.1",
            },
        )
        for source in lock["audited_sources"].values():
            self.assertEqual(source["import_date"], "2026-09-04")
            self.assertFalse(source["imported"])
            self.assertEqual(source["patches"], "none")
            if "commit" in source:
                self.assertRegex(source["commit"], r"^[0-9a-f]{40}$")
            if "sha256" in source:
                self.assertRegex(source["sha256"], SHA256)
            for file_value in source.get("files", {}).values():
                digest = file_value["sha256"] if isinstance(file_value, dict) else file_value
                self.assertRegex(digest, SHA256)
                if isinstance(file_value, dict):
                    self.assertTrue(file_value["license"])

    def test_spdx_draft_describes_current_project_and_external_candidates(self) -> None:
        sbom = json.loads(
            (ROOT / "docs/provenance/sbom.spdx.json").read_text(encoding="utf-8")
        )
        self.assertEqual(sbom["spdxVersion"], "SPDX-2.3")
        self.assertEqual(sbom["dataLicense"], "CC0-1.0")
        package_ids = {package["SPDXID"] for package in sbom["packages"]}
        self.assertIn("SPDXRef-Package-nrf-cmake-sdk", package_ids)
        self.assertIn("SPDXRef-Package-nrfx", package_ids)
        self.assertIn("SPDXRef-Package-S115", package_ids)
        self.assertEqual(
            {item["licenseId"] for item in sbom["hasExtractedLicensingInfos"]},
            {
                "LicenseRef-CodeSourcery-Linker-Script",
                "LicenseRef-Nordic-5-Clause",
            },
        )

    def test_audit_records_new_official_startup_conclusion(self) -> None:
        audit = (ROOT / "docs/provenance/source-audit.md").read_text(encoding="utf-8")
        self.assertIn("nrfx v4.5.0", audit)
        self.assertIn("Official GNU application", audit)
        self.assertIn("No device-specific Arm/ArmClang", audit)
        self.assertIn("not currently planned for import", audit)


if __name__ == "__main__":
    unittest.main()
