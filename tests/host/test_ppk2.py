# SPDX-License-Identifier: BSD-3-Clause

from pathlib import Path
from tempfile import TemporaryDirectory
import struct
import unittest
from unittest.mock import patch, MagicMock
from argparse import Namespace

from nrfkit_tools.ppk2 import Ppk2, Ppk2Error, Decoder, parse_metadata, decode_capture
from nrfkit_tools.ppk2_cli import command


class Ppk2Tests(unittest.TestCase):
    def test_power_session_holds_connection_and_turns_off_before_close(self):
        with TemporaryDirectory() as temporary:
            report = {}
            instrument = MagicMock()
            instrument.metadata.return_value = {'vdd': 1800, 'mode': 2}
            instrument.configure.return_value = {'vdd': 1800, 'mode': 2}
            args = Namespace(ppk_action='power', ppk_serial=None, manifest=None,
                             voltage_mv=1800, duration=60, state='on')
            def check_open(seconds):
                self.assertEqual(seconds, 60)
                instrument.close.assert_not_called()
                self.assertEqual(instrument.power.call_args.args, (True,))
            with patch('nrfkit_tools.cli._new_run', return_value=(Path(temporary), report)), \
                 patch('nrfkit_tools.ppk2_cli.discover', return_value=[]), \
                 patch('nrfkit_tools.ppk2_cli.select', return_value={'serial': 'test', 'port': 'unused'}), \
                 patch('nrfkit_tools.ppk2_cli.Ppk2', return_value=instrument), \
                 patch('nrfkit_tools.ppk2_cli.time.sleep', side_effect=check_open):
                command(args)
            self.assertEqual(instrument.power.call_args.args, (False,))
            instrument.close.assert_called_once()
            self.assertEqual(report['cleanup_output_requested'], 'off')

    def test_configuration_waits_for_readback_without_repeating_writes(self):
        instrument = object.__new__(Ppk2)
        instrument.command = MagicMock()
        instrument.metadata = MagicMock(side_effect=[
            {'mode': 2, 'vdd': 2400}, {'mode': 2, 'vdd': 1800}])
        with patch('nrfkit_tools.ppk2.time.sleep'):
            self.assertEqual(instrument.configure(1800, 'source')['vdd'], 1800)
        self.assertEqual(instrument.command.call_count, 2)
        instrument.metadata = MagicMock(return_value={'mode': 2, 'vdd': 2400})
        with patch('nrfkit_tools.ppk2.time.sleep'), \
             patch('nrfkit_tools.ppk2.time.monotonic', side_effect=[0, 3]):
            with self.assertRaisesRegex(Ppk2Error, 'vdd=2400'):
                instrument.configure(1800, 'source')

    def test_metadata_preserves_zero_and_marks_missing_calibration(self):
        metadata = parse_metadata(b'VDD: 1800\no0: 0\nr0: -nan\nEND\n')
        self.assertEqual(metadata['o0'], 0)
        self.assertIsNone(metadata['r0'])
        decoder = Decoder(metadata, 1800)
        self.assertNotIn('o0', decoder.defaulted)
        self.assertIn('r0', decoder.defaulted)
        for malformed in (b'\x80', b'vdd: 1800', b'x: 1\nx: 2\nEND'):
            with self.assertRaises(Ppk2Error):
                parse_metadata(malformed)

    def test_decoder_uses_gain_offset_and_counter_wrap(self):
        decoder = Decoder({'r0': 1000, 'o0': 4, 'gs0': 0, 'gi0': 2, 'ug0': 1}, 1800)
        expected = (100 * 4 - 4) * (1.8 / 163840) / 1000 * 2
        self.assertAlmostEqual(decoder.sample(100 | (63 << 18)), expected)
        self.assertAlmostEqual(decoder.sample(100), expected)
        with self.assertRaisesRegex(Ppk2Error, 'discontinuity'):
            decoder.sample(100 | (2 << 18))
        with self.assertRaisesRegex(Ppk2Error, 'range'):
            Decoder({}, 1800).sample(5 << 14)

    def test_current_csv_uses_instrument_sample_clock_and_flags_defaults(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / 'samples.bin'
            raw.write_bytes(b''.join(struct.pack('<I', 100 | (n << 18)) for n in range(3)))
            summary = decode_capture(raw, root / 'current.csv', {'calibrated': 0}, 1800)
            self.assertAlmostEqual(summary['duration_s'], 20e-6)
            self.assertFalse(summary['calibrated'])
            self.assertTrue(summary['defaulted_coefficients'])
            self.assertAlmostEqual(summary['estimated_energy_j'], summary['charge_c'] * 1.8)
            self.assertIn('0.00002,', (root / 'current.csv').read_text())

    def test_capture_failure_stops_supply_and_closes_instrument(self):
        with TemporaryDirectory() as temporary:
            report = {}
            instrument = MagicMock()
            instrument.metadata.return_value = {'vdd': 1800, 'mode': 2}
            instrument.configure.return_value = {'vdd': 1800, 'mode': 2}
            instrument.capture.side_effect = Ppk2Error('lost device')
            args = Namespace(ppk_action='capture', ppk_serial=None, manifest=None,
                             voltage_mv=1800, duration=1, settle=0, power_cycle=True, label='test')
            with patch('nrfkit_tools.cli._new_run', return_value=(Path(temporary), report)), \
                 patch('nrfkit_tools.ppk2_cli.discover', return_value=[]), \
                 patch('nrfkit_tools.ppk2_cli.select', return_value={'serial': 'test', 'port': 'unused'}), \
                 patch('nrfkit_tools.ppk2_cli.Ppk2', return_value=instrument), \
                 patch('nrfkit_tools.ppk2_cli.time.sleep'):
                with self.assertRaisesRegex(Ppk2Error, 'lost device'):
                    command(args)
            self.assertEqual(instrument.power.call_args.args, (False,))
            instrument.close.assert_called_once()
            self.assertEqual(report['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
