# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest import mock

from nrfkit_tools import usb_validation


class FakeUsbUtil:
    def __init__(self) -> None:
        self.claimed: list[int] = []

    def claim_interface(self, device: object, interface: int) -> None:
        self.claimed.append(interface)


class FakeDevice:
    def __init__(self, configuration: int | None) -> None:
        self.configuration = configuration
        self.detached: list[int] = []
        self.set_configurations: list[int] = []

    def is_kernel_driver_active(self, interface: int) -> bool:
        return interface == 1

    def detach_kernel_driver(self, interface: int) -> None:
        self.detached.append(interface)

    def get_active_configuration(self) -> object:
        if self.configuration is None:
            raise ValueError("not configured")
        return SimpleNamespace(bConfigurationValue=self.configuration)

    def set_configuration(self, configuration: int) -> None:
        self.set_configurations.append(configuration)


class UsbValidationTests(unittest.TestCase):
    def test_claim_preserves_an_already_active_configuration(self) -> None:
        device = FakeDevice(1)
        util = FakeUsbUtil()
        with mock.patch.object(usb_validation, "_modules", return_value=(object(), util)):
            returned_util, detached = usb_validation._claim(device)
        self.assertIs(returned_util, util)
        self.assertEqual(device.detached, [1])
        self.assertEqual(detached, [1])
        self.assertEqual(device.set_configurations, [])
        self.assertEqual(util.claimed, [0, 1])

    def test_claim_configures_an_unconfigured_device(self) -> None:
        device = FakeDevice(None)
        util = FakeUsbUtil()
        with mock.patch.object(usb_validation, "_modules", return_value=(object(), util)):
            usb_validation._claim(device)
        self.assertEqual(device.set_configurations, [1])

    def test_status_layout_matches_the_firmware_contract(self) -> None:
        values = tuple(range(22))
        values = (usb_validation.STATUS_MAGIC,) + values[1:]
        payload = usb_validation.struct.pack(usb_validation.STATUS_FORMAT, *values)
        device = SimpleNamespace(ctrl_transfer=lambda *args, **kwargs: payload)
        status = usb_validation.read_status(device)
        self.assertEqual(status["magic"], usb_validation.STATUS_MAGIC)
        self.assertEqual(status["wake_pcgcctl_after"], 18)
        self.assertEqual(status["bulk_arm_result"], 20)
        self.assertEqual(status["hid_arm_result"], 21)

    def test_host_resume_contract_rejects_reconfiguration(self) -> None:
        before = {"configured_count": 2, "suspend_count": 4, "resume_count": 3}
        after = {"configured_count": 3, "suspend_count": 5, "resume_count": 4}
        with self.assertRaisesRegex(
            usb_validation.UsbValidationError, "reset or reconfigured"
        ):
            usb_validation._validate_host_resume(before, after)

    def test_host_resume_contract_accepts_suspend_and_resume(self) -> None:
        before = {"configured_count": 2, "suspend_count": 4, "resume_count": 3}
        after = {"configured_count": 2, "suspend_count": 5, "resume_count": 4}
        usb_validation._validate_host_resume(before, after)


if __name__ == "__main__":
    unittest.main()
