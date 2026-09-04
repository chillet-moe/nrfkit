# SPDX-License-Identifier: BSD-3-Clause

from pathlib import Path
import tempfile
import unittest

from nrfkit_tools.bond import (
    M6_SETTINGS_RANGE,
    M6_SETTINGS_SIZE,
    is_m6_bond_manifest,
    read_exact_m6_settings,
    write_erased_m6_settings,
)
from nrfkit_tools.device import read_memory_argv
from nrfkit_tools.image import parse_ihex


class BondToolTests(unittest.TestCase):
    def test_only_bond_capable_m6_manifests_are_accepted(self) -> None:
        self.assertTrue(is_m6_bond_manifest("nrf-bm-ble-hids-mouse-s115"))
        self.assertTrue(is_m6_bond_manifest("sdk-m6_ble_validation"))
        self.assertTrue(is_m6_bond_manifest("sdk-m6_ble_official_baseline"))
        for phase in range(4, 7):
            self.assertTrue(is_m6_bond_manifest(f"sdk-m6_ble_phase{phase}"))
        for phase in range(1, 4):
            self.assertFalse(is_m6_bond_manifest(f"sdk-m6_ble_phase{phase}"))
        self.assertFalse(is_m6_bond_manifest("sdk-m6_ble_phase7"))
        self.assertFalse(is_m6_bond_manifest("unrelated"))

    def test_erased_image_covers_only_the_declared_settings_region(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "settings.hex"
            write_erased_m6_settings(image)

            self.assertEqual(parse_ihex(image).ranges, (M6_SETTINGS_RANGE,))
            self.assertEqual(read_exact_m6_settings(image), b"\xFF" * M6_SETTINGS_SIZE)

    def test_settings_read_is_bounded_and_uses_controller_checks(self) -> None:
        argv = read_memory_argv(
            "nrfutil", "backup.hex", "123", "NRF54L", "Application",
            M6_SETTINGS_RANGE[0], M6_SETTINGS_SIZE,
        )

        self.assertIn("read", argv)
        self.assertEqual(argv[argv.index("--address") + 1], "0x001e1800")
        self.assertEqual(argv[argv.index("--bytes") + 1], "8192")
        self.assertNotIn("--direct", argv)


if __name__ == "__main__":
    unittest.main()
