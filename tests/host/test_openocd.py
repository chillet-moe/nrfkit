# SPDX-License-Identifier: BSD-3-Clause

from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch, MagicMock

from nrfkit_tools.image import ImageContractError, parse_ihex
from nrfkit_tools.openocd import (
    OpenOcd,
    OpenOcdError,
    addressed_hex,
    configuration,
    observation_path_valid,
    parse_identity,
    system_control_observation_address,
    tcl_word,
)
from nrfkit_tools.openocd_cli import (
    _backup,
    _backup_ranges,
    _clear_rram,
    _restore,
    _settings_span,
    command,
)
from nrfkit_tools.reference import sha256


class OpenOcdTests(unittest.TestCase):
    def test_gdb_observations_accept_only_identifiers_and_member_paths(self):
        for path in ("board_lcd_status", "nrfkit_last_fault.pc", "a.b2.c_3"):
            self.assertTrue(observation_path_valid(path))
        for path in ("record->pc", "record.pc+1", "*record", "record..pc", "1record.pc"):
            self.assertFalse(observation_path_valid(path))

    def test_system_control_observations_are_aligned_and_scs_only(self):
        self.assertEqual(system_control_observation_address("0xe000ed28"), 0xE000ED28)
        for address in ("0xe000ed29", "0xe000e004", "0x20000000", "not-an-address"):
            with self.assertRaises(OpenOcdError):
                system_control_observation_address(address)

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

    def test_configuration_binds_one_probe_and_defers_reset_to_target(self):
        text = configuration({'serial': 'probe', 'vid': 0x0d28, 'pid': 0x0204, 'interface': 0}, 2000)
        self.assertIn('adapter serial {probe}', text)
        self.assertIn('source [find target/nordic/nrf54lm20.cfg]', text)
        self.assertIn('nrf54lm20_reset_config system', text)
        self.assertNotIn('reset_config srst', text)
        self.assertIn('gdb port disabled', text)
        self.assertNotIn('sysresetreq', text)
        for speed in (0, 8000):
            with self.assertRaises(OpenOcdError):
                configuration({}, speed)

    def test_reset_precedes_identity_but_memory_operations_do_not(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            scripts = directory / "target/nordic"
            scripts.mkdir(parents=True)
            (scripts / "nrf54lm20.cfg").touch()
            executable = directory / "openocd"
            executable.touch()
            backend = OpenOcd(executable, directory,
                              {'serial': 'probe', 'vid': 0x0d28, 'pid': 0x0204,
                               'interface': 0}, directory, 1000, 20)
            identity = 'NRFKIT_ID 054bc20b 41414244 2036\nNRFKIT_DEVICEID 00000001 00000002\n'
            result = MagicMock(returncode=0, timed_out=False, stdout=identity)
            with patch('nrfkit_tools.openocd.run_logged', return_value=result):
                backend.reset(pin=True)
                script = (directory / 'reset.tcl').read_text()
                self.assertLess(script.index('reset run'), script.index('read_memory'))
                self.assertLess(script.index('adapter deassert srst'),
                                script.index('if {$reset_failed}'))
                self.assertNotIn('sysresetreq', script)
                backend.run('program', 'halt\nflash write_image {image.hex}')
                script = (directory / 'program.tcl').read_text()
                self.assertLess(script.index('read_memory'), script.index('flash write_image'))
                self.assertNotIn('reset run', script)
                with self.assertRaisesRegex(OpenOcdError, 'pin reset'):
                    backend.reset(halt=True, pin=True)
                (directory / 'reset.tcl').unlink()
                backend.reset(halt=True, diagnostics=True)
                script = (directory / 'reset.tcl').read_text()
                self.assertNotIn('connect_assert_srst', script)
                self.assertLess(script.index('debug_level 3'), script.index('\ninit\n'))
                self.assertLess(script.index('debug_level 2'), script.index('read_memory'))
                self.assertLess(script.index('reset halt'), script.index('read_memory'))
                self.assertNotIn('reset run', script)
                (directory / 'reset.tcl').unlink()
                backend.reset()
                script = (directory / 'reset.tcl').read_text()
                self.assertIn('reset halt\nresume\n', script)
                self.assertNotIn('reset run', script)
                (directory / 'reset.tcl').unlink()
                result.stdout = ''
                with self.assertRaisesRegex(OpenOcdError, 'identity'):
                    backend.reset()

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

    def test_clear_requires_matching_backup_and_checks_full_readback(self):
        identity = 'NRFKIT_ID 054bc20b 41414244 2036\nNRFKIT_DEVICEID 00000001 00000002\n'
        for failure in (None, 'backup', 'readback'):
            with self.subTest(failure=failure), TemporaryDirectory() as temporary:
                directory = Path(temporary)
                backend = MagicMock(run_dir=directory)
                report = {}

                def run(name, commands):
                    if name == 'backup':
                        (directory / 'backup-0-1.bin').write_bytes(b'A' * 32)
                        (directory / 'backup-0-2.bin').write_bytes(
                            (b'B' if failure == 'backup' else b'A') * 32)
                    else:
                        self.assertEqual(name, 'clear')
                        self.assertTrue((directory / 'backup.json').is_file())
                        self.assertIn('target changed after backup', commands)
                        self.assertLess(commands.index('target changed'),
                                        commands.index('flash write_image'))
                        self.assertNotIn('erase', commands)
                        self.assertNotIn('reset', commands)
                        self.assertEqual(parse_ihex(directory / 'clear-rram.hex').ranges,
                                         ((0, 32),))
                        (directory / 'clear-readback.bin').write_bytes(
                            (b'A' if failure == 'readback' else b'\xff') * 32)
                    return identity

                backend.run.side_effect = run
                with patch('nrfkit_tools.openocd_cli.RRAM_END', 32):
                    if failure:
                        with self.assertRaises(OpenOcdError):
                            _clear_rram(backend, report)
                        self.assertNotIn('clear_verified', report)
                        self.assertEqual(backend.run.call_count, 1 if failure == 'backup' else 2)
                    else:
                        _clear_rram(backend, report)
                        self.assertTrue(report['clear_verified'])
                        self.assertEqual(report['target_state'], 'halted')

    def test_backup_ranges_reject_config_and_misalignment_before_hardware(self):
        backend = MagicMock()
        for spans in ([], [(0, 17)], [(0, 0)], [(0x00ffd000, 0x00ffe000)]):
            with self.assertRaises((ImageContractError, OpenOcdError)):
                _backup_ranges(backend, spans, {})
        backend.run.assert_not_called()

    def test_backup_checks_rounded_range_before_target_access(self):
        backend = MagicMock()
        with self.assertRaises(ImageContractError):
            _backup(backend, [{'images': [{'ranges': [[4, 18]], 'allowlist': [[4, 18]]}]}], {})
        backend.run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
