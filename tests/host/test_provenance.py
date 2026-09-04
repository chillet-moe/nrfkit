# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ProvenanceTests(unittest.TestCase):
    def test_sdc_reference_oracle_is_locked_to_hard_float_multirole(self) -> None:
        lock = json.loads(
            (ROOT / "docs/provenance/sources.lock").read_text(encoding="utf-8")
        )
        oracle = lock["oracles"]["ncs-hci-uart-sdc"]
        self.assertEqual(oracle["board"], "nrf54lm20dk/nrf54lm20a/cpuapp")
        self.assertEqual(oracle["modules"]["nrfxlib"],
                         lock["audited_sources"]["sdk-nrfxlib-3.4.0"]["commit"])
        self.assertEqual(oracle["hci_transport"], {
            "type": "H4", "baud": 1000000, "hardware_flow_control": True,
        })
        evidence = oracle["build_evidence"]
        self.assertIn("CONFIG_BT_LL_SOFTDEVICE_MULTIROLE=y", evidence["config_markers"])
        self.assertIn('CONFIG_MPSL_LIB_FLOAT_ABI_DIR="hard-float"',
                      evidence["config_markers"])
        self.assertIn("libsoftdevice_controller_multirole.a",
                      " ".join(evidence["link_markers"]))
        self.assertNotIn("soft-float", " ".join(evidence["link_markers"]))

    def test_audited_sources_have_reproducible_identity(self) -> None:
        lock = json.loads(
            (ROOT / "docs/provenance/sources.lock").read_text(encoding="utf-8")
        )
        self.assertEqual(lock["schema"], "nrfkit-sources/v1")
        self.assertEqual(
            set(lock["audited_sources"]),
            {
                "nrfx-4.5.0", "cmsis-6.3.0", "nrf-device-family-pack-8.44.1",
                "trusted-firmware-m-ncs-3.4.0", "s115-10.0.1",
                "cherryusb-1.6.1", "nrf54lm20-datasheet-1.0",
                "ncs-radio-test-3.4.0", "sdk-nrfxlib-3.4.0",
            },
        )
        for source_id, source in lock["audited_sources"].items():
            imported_on = date.fromisoformat(source["import_date"])
            self.assertEqual(imported_on.isoformat(), source["import_date"])
            self.assertIsInstance(source["imported"], bool)
            if source_id == "nrfx-4.5.0":
                self.assertEqual(
                    source["patches"],
                    [
                        "patches/nrfx/0001-grtc-enable-compare-after-programming.patch",
                        "patches/nrfx/0002-clock-xo-allow-null-source-output.patch",
                    ],
                )
            else:
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

        nrfxlib = lock["audited_sources"]["sdk-nrfxlib-3.4.0"]
        self.assertEqual(nrfxlib["target"], "nrf54lm")
        self.assertEqual(nrfxlib["security_domain"], "secure")
        self.assertEqual(nrfxlib["float_abi"], "hard-float")
        self.assertRegex(nrfxlib["binary_manifest_revision"], r"^[0-9a-f]{40}$")
        for archive in (
            "softdevice_controller/lib/nrf54lm/hard-float/libsoftdevice_controller_multirole.a",
            "softdevice_controller/lib/nrf54lm/hard-float/libsoftdevice_controller_peripheral.a",
            "softdevice_controller/lib/nrf54lm/hard-float/libsoftdevice_controller_central.a",
            "mpsl/lib/nrf54lm/hard-float/libmpsl.a",
            "mpsl/fem/common/lib/nrf54lm/hard-float/libmpsl_fem_common.a",
        ):
            self.assertIn(archive, nrfxlib["files"])

    def test_nrfx_submodule_and_patch_are_locked_and_immutable(self) -> None:
        lock = json.loads(
            (ROOT / "docs/provenance/sources.lock").read_text(encoding="utf-8")
        )
        expected = lock["audited_sources"]["nrfx-4.5.0"]["commit"]
        actual = subprocess.run(
            ["git", "-C", str(ROOT / "external/nrfx"), "rev-parse", "HEAD"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        self.assertEqual(actual.returncode, 0, actual.stdout)
        self.assertEqual(actual.stdout.strip(), expected)
        for patch in lock["audited_sources"]["nrfx-4.5.0"]["patches"]:
            check = subprocess.run(
                [
                    "git", "-C", str(ROOT / "external/nrfx"), "apply", "--check",
                    str(ROOT / patch),
                ],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            self.assertEqual(check.returncode, 0, check.stdout)

    def test_cherryusb_submodule_is_locked(self) -> None:
        lock = json.loads(
            (ROOT / "docs/provenance/sources.lock").read_text(encoding="utf-8")
        )
        expected = lock["audited_sources"]["cherryusb-1.6.1"]["commit"]
        actual = subprocess.run(
            ["git", "-C", str(ROOT / "external/cherryusb"), "rev-parse", "HEAD"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        self.assertEqual(actual.returncode, 0, actual.stdout)
        self.assertEqual(actual.stdout.strip(), expected)

    def test_sdk_nrfxlib_submodule_and_selected_files_are_locked(self) -> None:
        import hashlib

        lock = json.loads(
            (ROOT / "docs/provenance/sources.lock").read_text(encoding="utf-8")
        )
        source = lock["audited_sources"]["sdk-nrfxlib-3.4.0"]
        upstream = ROOT / "external/sdk-nrfxlib"
        actual = subprocess.run(
            ["git", "-C", str(upstream), "rev-parse", "HEAD"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        self.assertEqual(actual.returncode, 0, actual.stdout)
        self.assertEqual(actual.stdout.strip(), source["commit"])

        configured_url = subprocess.run(
            [
                "git", "config", "--file", str(ROOT / ".gitmodules"), "--get",
                "submodule.external/sdk-nrfxlib.url",
            ],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        self.assertEqual(configured_url.returncode, 0, configured_url.stdout)
        self.assertEqual(
            configured_url.stdout.strip(),
            "https://github.com/nrfconnect/sdk-nrfxlib.git",
        )

        for relative, metadata in source["files"].items():
            path = upstream / relative
            self.assertTrue(path.is_file(), relative)
            expected = metadata["sha256"] if isinstance(metadata, dict) else metadata
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)

        for component in ("softdevice_controller", "mpsl"):
            manifest = (upstream / component / "lib/nrf54lm/manifest.yaml").read_text(
                encoding="utf-8"
            )
            self.assertIn(
                f"git_revision: {source['binary_manifest_revision']}", manifest
            )

    def test_vendor_import_manifest_covers_and_hashes_third_party_tree(self) -> None:
        lock = json.loads(
            (ROOT / "docs/provenance/sources.lock").read_text(encoding="utf-8")
        )
        import_ref = lock["vendor_import_manifest"]
        import_path = ROOT / import_ref["path"]
        import hashlib
        self.assertEqual(hashlib.sha256(import_path.read_bytes()).hexdigest(), import_ref["sha256"])
        manifest = json.loads(import_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], "nrfkit-vendor-imports/v1")
        entries = {item["destination"]: item for item in manifest["files"]}
        actual = {
            path.relative_to(ROOT).as_posix(): path
            for path in (ROOT / "third_party").rglob("*") if path.is_file()
        }
        self.assertEqual(set(entries), set(actual))
        for destination, path in actual.items():
            item = entries[destination]
            self.assertRegex(item["sha256"], SHA256)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item["sha256"])
            self.assertTrue(item["source_path"])
            self.assertTrue(item["license"])
            self.assertEqual(item["patches"], "none")

    def test_spdx_draft_describes_current_project_and_external_candidates(self) -> None:
        sbom = json.loads(
            (ROOT / "docs/provenance/sbom.spdx.json").read_text(encoding="utf-8")
        )
        self.assertEqual(sbom["spdxVersion"], "SPDX-2.3")
        self.assertEqual(sbom["dataLicense"], "CC0-1.0")
        package_ids = {package["SPDXID"] for package in sbom["packages"]}
        self.assertIn("SPDXRef-Package-nrfkit", package_ids)
        self.assertIn("SPDXRef-Package-nrfx", package_ids)
        self.assertIn("SPDXRef-Package-CMSIS", package_ids)
        self.assertIn("SPDXRef-Package-S115", package_ids)
        self.assertIn("SPDXRef-Package-sdk-nrfxlib", package_ids)
        self.assertIn("SPDXRef-Package-CherryUSB", package_ids)
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

    def test_m1_toolchains_are_identified_without_local_paths(self) -> None:
        lock = json.loads(
            (ROOT / "docs/provenance/toolchains.lock").read_text(encoding="utf-8")
        )
        self.assertIn("llvm-arm-bare-metal", lock["tools"])
        self.assertIn("fedora-gnu-arm-smoke", lock["tools"])
        for tool in lock["tools"].values():
            serialized = json.dumps(tool)
            self.assertNotRegex(serialized, r"/(?:home|Users)/[^/]+/")
            for digest in tool.get("executables", {}).values():
                self.assertRegex(digest, SHA256)


if __name__ == "__main__":
    unittest.main()
