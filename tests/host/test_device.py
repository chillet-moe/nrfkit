# SPDX-License-Identifier: BSD-3-Clause

import json
import unittest

from nrf_cmake_tools.device import DeviceContractError, parse_json_lines, select_device


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


if __name__ == "__main__":
    unittest.main()
