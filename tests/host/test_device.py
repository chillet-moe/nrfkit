# SPDX-License-Identifier: BSD-3-Clause

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from nrfkit_tools.device import (
    DeviceContractError, parse_json_lines, resolve_probe_alias, select_device,
)


class DeviceTests(unittest.TestCase):
    def test_json_lines_uses_info_payload(self) -> None:
        output = "\n".join((
            json.dumps({"type": "log", "data": {"message": "noise"}}),
            json.dumps({"type": "info", "data": {"devices": [{"id": 4}]}}),
        ))
        self.assertEqual(parse_json_lines(output, "devices"), [{"id": 4}])

    def test_multiple_matching_devices_are_ambiguous(self) -> None:
        devices = [
            {"serialNumber": "A", "devkit": {"boardVersion": "PCA10184"}},
            {"serialNumber": "B", "devkit": {"boardVersion": "PCA10184"}},
        ]
        with self.assertRaisesRegex(DeviceContractError, "multiple"):
            select_device(devices, "PCA10184", None)

    def test_explicit_serial_selects_one_device(self) -> None:
        devices = [
            {"serialNumber": "A", "devkit": {"boardVersion": "PCA10184"}},
            {"serialNumber": "B", "devkit": {"boardVersion": "PCA10184"}},
        ]
        self.assertEqual(select_device(devices, "PCA10184", "B")["serialNumber"], "B")

    def test_local_alias_resolves_only_for_matching_board(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "hardware-aliases.json"
            path.write_text(json.dumps({
                "schema": "nrfkit-local-hardware-aliases/v1",
                "aliases": {
                    "lm20": {
                        "board_version": "PCA10184",
                        "probe_serial": "private-probe",
                    }
                },
            }))
            self.assertEqual(
                resolve_probe_alias("LM20", "PCA10184", path), "private-probe"
            )
            with self.assertRaisesRegex(DeviceContractError, "does not match"):
                resolve_probe_alias("LM20", "PCA10156", path)


if __name__ == "__main__":
    unittest.main()
