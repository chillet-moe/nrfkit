# SPDX-License-Identifier: BSD-3-Clause

from argparse import Namespace
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from nrfkit_tools.ppk2 import Ppk2Error
from nrfkit_tools.ppk2_eeprom import (
    CALIBRATION_OFFSETS,
    PPK2_EEPROM_USB_ID,
    find_new_eeprom_shell_port,
    parse_calibration_read,
    parse_eeprom_dump,
    verify_calibration_bytes,
)
from nrfkit_tools.ppk2_eeprom_cli import _program_dfu, _switch_to_bootloader, command
from nrfkit_tools.process import ProcessResult


class Ppk2EepromTests(unittest.TestCase):
    @staticmethod
    def _eeprom_fixture():
        image = bytearray(range(256))
        lines = []
        for index, (name, offset) in enumerate(CALIBRATION_OFFSETS.items()):
            value = float(index + 1)
            raw = struct.pack('<f', value)
            image[offset:offset + 4] = raw
            lines.append(
                f"{name:>4} ({offset:3d}): {value:15.9f}, "
                + " ".join(f"{octet:02x}" for octet in raw)
            )
        dump = "\n".join(
            f"{offset:08x}: "
            + " ".join(f"{octet:02x}" for octet in image[offset:offset + 16])
            + " |................|"
            for offset in range(0, 256, 16)
        )
        return bytes(image), "\n".join(lines), dump

    def test_eeprom_dump_and_calibration_are_complete_and_cross_checked(self):
        expected, calibration_text, dump = self._eeprom_fixture()
        image = parse_eeprom_dump(dump)
        calibration = parse_calibration_read(calibration_text)
        self.assertEqual(image, expected)
        verify_calibration_bytes(calibration, image)
        self.assertEqual(calibration['r0']['classification'], 'finite')
        self.assertEqual(calibration['ug4']['value'], 35.0)

        with self.assertRaisesRegex(Ppk2Error, '256'):
            parse_eeprom_dump("\n".join(dump.splitlines()[:-1]))
        changed = bytearray(image)
        changed[CALIBRATION_OFFSETS['r0']] ^= 1
        with self.assertRaisesRegex(Ppk2Error, 'r0'):
            verify_calibration_bytes(calibration, bytes(changed))

    def test_calibration_parser_preserves_nonfinite_bytes_without_json_nan(self):
        _, calibration_text, _ = self._eeprom_fixture()
        nan_bytes = struct.pack('<f', float('nan'))
        replacement = (
            f"  r0 (  0):             nan, "
            + " ".join(f"{octet:02x}" for octet in nan_bytes)
        )
        calibration_text = "\n".join([replacement, *calibration_text.splitlines()[1:]])
        calibration = parse_calibration_read(calibration_text)
        self.assertIsNone(calibration['r0']['value'])
        self.assertEqual(calibration['r0']['classification'], 'nan')
        self.assertEqual(calibration['r0']['bytes'], nan_bytes.hex())

    def test_shell_discovery_uses_new_firmware_identity_not_usb_location(self):
        temporary_vid, temporary_pid = PPK2_EEPROM_USB_ID
        ports = [
            SimpleNamespace(device='existing-port', vid=temporary_vid, pid=temporary_pid),
            SimpleNamespace(device='new-port', vid=temporary_vid, pid=temporary_pid),
            SimpleNamespace(device='unrelated-port', vid=0x1915, pid=0x521f),
        ]
        with patch('serial.tools.list_ports.comports', return_value=ports):
            self.assertEqual(find_new_eeprom_shell_port({'existing-port'}), 'new-port')
            self.assertIsNone(
                find_new_eeprom_shell_port({'existing-port', 'new-port'}),
            )

    def test_verified_bootloader_state_overrides_nrfutil_disconnect_timeout(self):
        result = ProcessResult(1, False, 10.0, 'device event timeout')
        with TemporaryDirectory() as temporary, \
             patch('nrfkit_tools.ppk2_eeprom_cli.run_logged', return_value=result), \
             patch('nrfkit_tools.ppk2_eeprom_cli._wait_nrfutil_state') as wait_state:
            _switch_to_bootloader('nrfutil', 'test', Path(temporary), 30)
        wait_state.assert_called_once()

    def test_dfu_program_requests_application_state(self):
        result = ProcessResult(0, False, 1.0, '')
        with TemporaryDirectory() as temporary, \
             patch('nrfkit_tools.ppk2_eeprom_cli.run_logged', return_value=result) as run:
            _program_dfu(
                'nrfutil', 'test', Path(temporary) / 'image.zip',
                Path(temporary) / 'program.log', 30,
            )
        argv = run.call_args.args[0]
        self.assertIn('mcu_end_state=NRFDL_MCU_STATE_APPLICATION', argv)

    def test_audit_restores_the_firmware_identity_observed_before_the_transaction(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = {}
            instrument = MagicMock()
            instrument.metadata.return_value = {'calibrated': 0}
            shell = MagicMock()
            shell.calibration_read.side_effect = Ppk2Error('read failed')
            initial_firmware = 'identity reported by the connected instrument'
            args = Namespace(
                ppk_serial=None,
                temporary_package=root / 'temporary.zip',
                restore_package=root / 'restore.zip',
                restore_package_sha256='0' * 64,
                nrfutil='nrfutil', timeout=30,
            )
            with patch('nrfkit_tools.ppk2_eeprom_cli._validate_inputs'), \
                 patch('nrfkit_tools.cli._new_run', return_value=(root, report)), \
                 patch('nrfkit_tools.ppk2_eeprom_cli.select', return_value={
                     'serial': 'test', 'port': 'normal'}), \
                 patch('nrfkit_tools.ppk2_eeprom_cli.Ppk2', return_value=instrument), \
                 patch('nrfkit_tools.ppk2_eeprom_cli._firmware_identity', side_effect=[
                     initial_firmware, initial_firmware]), \
                 patch('nrfkit_tools.ppk2_eeprom_cli.eeprom_shell_ports', return_value=set()), \
                 patch('nrfkit_tools.ppk2_eeprom_cli._switch_to_bootloader'), \
                 patch('nrfkit_tools.ppk2_eeprom_cli._wait_nrfutil_state'), \
                 patch('nrfkit_tools.ppk2_eeprom_cli._program_dfu') as program, \
                 patch('nrfkit_tools.ppk2_eeprom_cli.wait_new_eeprom_shell_port',
                       return_value='shell'), \
                 patch('nrfkit_tools.ppk2_eeprom_cli.Ppk2EepromShell', return_value=shell):
                with self.assertRaisesRegex(Ppk2Error, 'read failed'):
                    command(args)
            self.assertEqual(program.call_count, 2)
            self.assertEqual(program.call_args_list[0].args[2], args.temporary_package)
            self.assertEqual(program.call_args_list[1].args[2], args.restore_package)
            shell.reset_to_bootloader.assert_called_once()
            self.assertEqual(report['restore_firmware']['expected_identity'], initial_firmware)
            self.assertTrue(report['cleanup']['official_firmware_restored'])


if __name__ == '__main__':
    unittest.main()
