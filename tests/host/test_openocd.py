# SPDX-License-Identifier: BSD-3-Clause

from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch, MagicMock

from nrfkit_tools.image import ImageContractError, parse_ihex
from nrfkit_tools.openocd import OpenOcdError, addressed_hex, configuration, parse_identity, tcl_word
from nrfkit_tools.openocd_cli import command, _restore, _backup, _settings_span
from nrfkit_tools.reference import sha256


class OpenOcdTests(unittest.TestCase):
    def test_settings_backup_accepts_only_separate_audited_ordinary_rram(self):
        manifest = {'debug_allowlist': [[0, 0x10000]], 'image_layout': {
            'source': 'elf-symbols', 'symbols': {
                '__nrfkit_settings_start': 0x10000, '__nrfkit_settings_end': 0x11000}}}
        self.assertEqual(_settings_span(manifest), (0x10000, 0x11000))
        for start, end in ((0, 16), (0x10001, 0x11000), (0x10000, 0x10000),
                           (0x00ffd000, 0x00ffe000)):
            manifest['image_layout']['symbols'].update(
                __nrfkit_settings_start=start, __nrfkit_settings_end=end)
            with self.assertRaises((OpenOcdError, ImageContractError)):
                _settings_span(manifest)
        with self.assertRaises(OpenOcdError):
            _settings_span({'debug_allowlist': [[0, 16]]})

    def test_tcl_argument_injection_is_rejected(self):
        for text in ('x} ; reset', 'a\\b', 'a\nb', 'a\x00b'):
            with self.assertRaises(OpenOcdError):
                tcl_word(text)
        self.assertEqual(tcl_word('a space/$value[command]'), '{a space/$value[command]}')

    def test_configuration_binds_one_probe_and_uses_physical_reset(self):
        text = configuration({'serial': 'probe', 'vid': 0x0d28, 'pid': 0x0204, 'interface': 0}, 2000)
        self.assertIn('adapter serial {probe}', text)
        self.assertIn('reset_config srst_only srst_nogate', text)
        self.assertIn('gdb port disabled', text)
        self.assertNotIn('sysresetreq', text)
        for speed in (0, 8000):
            with self.assertRaises(OpenOcdError):
                configuration({}, speed)

    def test_identity_accepts_both_lm20_parts_but_not_other_chips(self):
        for part in ('054bc20a', '054bc20b'):
            self.assertEqual(parse_identity(f'NRFKIT_ID {part} 41414244 2036\nNRFKIT_DEVICEID 00000001 00000002\n')['rram_kib'], 2036)
        with self.assertRaises(OpenOcdError):
            parse_identity('NRFKIT_ID 054bc20b 41414244 2048\nNRFKIT_DEVICEID 00000001 00000002\n')

    def test_addressed_backup_preserves_boundary_and_rejects_config(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'backup.hex'
            path.write_text(addressed_hex(0xfff0, bytes(range(32))))
            self.assertEqual(parse_ihex(path).ranges, ((0xfff0, 0x10010),))
            with self.assertRaises(ImageContractError):
                addressed_hex(0x00ffd000, bytes(16))
            with self.assertRaises(OpenOcdError):
                addressed_hex(1, bytes(16))

    def test_invalid_manifest_is_rejected_before_usb_discovery(self):
        with TemporaryDirectory() as temporary:
            with patch('nrfkit_tools.cli._new_run', return_value=(Path(temporary), {})), \
                 patch('nrfkit_tools.cli.load_manifest', side_effect=ImageContractError('unsafe')), \
                 patch('nrfkit_tools.openocd_cli.discover') as discover:
                with self.assertRaises(ImageContractError):
                    command(Namespace(openocd_action='flash', manifest=Path('unsafe')))
                discover.assert_not_called()

    def test_restore_rejects_stale_hash_outside_allowlist_and_different_chip(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / 'backup.hex'
            source.write_text(addressed_hex(0, bytes(32)))
            report_path = directory / 'backup.json'
            value = {'operation': 'openocd-backup', 'status': 'ok', 'target': {'part': 1},
                     'backups': [{'path': str(source), 'sha256': sha256(source), 'range': [0, 32]}]}
            report_path.write_text(json.dumps(value))
            backend = MagicMock(run_dir=directory)
            with self.assertRaises(ImageContractError):
                _restore(backend, {'debug_allowlist': [[16, 32]]}, report_path, {})
            backend.run.assert_not_called()
            (directory / 'restore-0.hex').unlink()
            value['backups'][0]['sha256'] = 'wrong'
            report_path.write_text(json.dumps(value))
            with self.assertRaisesRegex(OpenOcdError, 'changed'):
                _restore(backend, {'debug_allowlist': [[0, 32]]}, report_path, {})
            backend.run.assert_not_called()
            (directory / 'restore-0.hex').unlink()
            value['backups'][0]['sha256'] = sha256(source)
            report_path.write_text(json.dumps(value))
            backend.run.return_value = 'NRFKIT_ID 054bc20b 41414244 2036\nNRFKIT_DEVICEID 00000001 00000002\n'
            with self.assertRaisesRegex(OpenOcdError, 'different target'):
                _restore(backend, {'debug_allowlist': [[0, 32]]}, report_path, {})
            self.assertEqual(backend.run.call_count, 1)
            self.assertEqual(backend.run.call_args.args[0], 'restore-identity')

    def test_backup_checks_rounded_range_before_target_access(self):
        backend = MagicMock()
        with self.assertRaises(ImageContractError):
            _backup(backend, [{'images': [{'ranges': [[4, 18]], 'allowlist': [[4, 18]]}]}], {})
        backend.run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
