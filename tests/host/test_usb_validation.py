# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from nrfkit_tools import usb_validation
from nrfkit_tools.cli import command_consumer_usb_smoke, main


class ConsumerUsbAttachTests(unittest.TestCase):
    def test_cli_accepts_descriptor_only_inspection(self):
        with mock.patch('nrfkit_tools.cli.command_consumer_usb_smoke', return_value=0) as command:
            self.assertEqual(main(['consumer-usb-smoke', '--attach', '--reconnect-cycles', '0',
                                   '--manifest', 'image.json', '--vid', '0xcafe', '--pid', '0x4012']), 0)
            self.assertTrue(command.call_args.args[0].attach)

    def test_attach_does_not_select_program_or_reset_a_probe(self):
        with TemporaryDirectory() as temporary:
            report = {'stages': []}
            args = SimpleNamespace(manifest=Path('image.json'), attach=True,
                                   vid=0xcafe, pid=0x4012, expected_speed=480,
                                   expected_interfaces=4, timeout=5, reconnect_cycles=0)
            with mock.patch('nrfkit_tools.cli._new_run', return_value=(Path(temporary), report)), \
                 mock.patch('nrfkit_tools.cli.load_manifest', return_value={}), \
                 mock.patch('nrfkit_tools.cli._initialize_device_report'), \
                 mock.patch('nrfkit_tools.cli._select') as select, \
                 mock.patch('nrfkit_tools.cli._program') as program, \
                 mock.patch('nrfkit_tools.cli.run_logged') as run, \
                 mock.patch('nrfkit_tools.cli.inspect_standard_descriptors', return_value={}), \
                 mock.patch('nrfkit_tools.cli.run_standard_reconnect_validation', return_value={}):
                command_consumer_usb_smoke(args)
            select.assert_not_called()
            program.assert_not_called()
            run.assert_not_called()
            self.assertEqual(report['status'], 'ok')


class FakeUsbUtil:
    def __init__(self) -> None:
        self.claimed: list[int] = []

    def claim_interface(self, device: object, interface: int) -> None:
        self.claimed.append(interface)

    def dispose_resources(self, device: object) -> None:
        pass


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


class FakeEndpoint:
    bEndpointAddress = 0x81
    bmAttributes = 3
    wMaxPacketSize = 64
    bInterval = 1


class FakeInterface:
    bInterfaceNumber = 0
    bAlternateSetting = 0
    bInterfaceClass = 3
    bInterfaceSubClass = 1
    bInterfaceProtocol = 1

    def __iter__(self):
        return iter((FakeEndpoint(),))


class FakeConfiguration:
    bConfigurationValue = 1

    def __iter__(self):
        return iter((FakeInterface(),))


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

    def test_standard_descriptor_inspection_uses_only_standard_objects(self) -> None:
        device = SimpleNamespace(
            speed=3, idVendor=0xCAFE, idProduct=0x4012,
            get_active_configuration=lambda: FakeConfiguration(),
        )
        with mock.patch.object(
            usb_validation, "_configured_device",
            return_value=(device, FakeConfiguration()),
        ):
            result = usb_validation.inspect_standard_descriptors(
                vid=0xCAFE, pid=0x4012, expected_speed=3,
                expected_interfaces=1, timeout=1,
            )
        self.assertEqual(result["configuration"], 1)
        self.assertEqual(result["interfaces"][0]["class"], 3)
        self.assertEqual(result["interfaces"][0]["endpoints"][0]["address"], 0x81)

    def test_standard_descriptor_inspection_rejects_interface_mismatch(self) -> None:
        device = SimpleNamespace(
            speed=3, idVendor=0xCAFE, idProduct=0x4012,
            get_active_configuration=lambda: FakeConfiguration(),
        )
        with mock.patch.object(
            usb_validation, "_configured_device",
            return_value=(device, FakeConfiguration()),
        ):
            with self.assertRaisesRegex(usb_validation.UsbValidationError, "interfaces"):
                usb_validation.inspect_standard_descriptors(
                    vid=0xCAFE, pid=0x4012, expected_speed=3,
                    expected_interfaces=2, timeout=1,
                )

    def test_standard_descriptor_inspection_selects_configuration_when_needed(self) -> None:
        configurations: list[int] = []

        def active_configuration() -> FakeConfiguration:
            if not configurations:
                raise ValueError("not configured")
            return FakeConfiguration()

        device = SimpleNamespace(
            speed=3, idVendor=0xCAFE, idProduct=0x4012,
            get_active_configuration=active_configuration,
            set_configuration=lambda value: configurations.append(value),
        )
        util = FakeUsbUtil()
        with (
            mock.patch.object(usb_validation, "_find_ids", return_value=device),
            mock.patch.object(usb_validation, "_modules", return_value=(object(), util)),
        ):
            returned_device, result = usb_validation._configured_device(
                vid=0xCAFE, pid=0x4012, timeout=1,
            )
        self.assertEqual(configurations, [1])
        self.assertIs(returned_device, device)
        self.assertEqual(result.bConfigurationValue, 1)


if __name__ == "__main__":
    unittest.main()
