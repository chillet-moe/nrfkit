# SPDX-License-Identifier: BSD-3-Clause

import ctypes
from fractions import Fraction
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PlatformInitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('cc')
        if not compiler:
            raise unittest.SkipTest('host C compiler required')
        cls.temp = tempfile.TemporaryDirectory()
        directory = Path(cls.temp.name)
        # Register values are checked against the locked MDK by cross builds.
        (directory / 'nrf.h').write_text('''
#include <stdint.h>
struct clock_regs { struct { uint32_t RUN, STAT; } XO, LFCLK; };
struct oscillator_regs {
    struct { struct { uint32_t INTCAP; } CONFIG; } XOSC32M;
    struct { uint32_t STATUS, INTCAP, BYPASS; } XOSC32KI;
};
struct ficr_regs { uint32_t XOSC32MTRIM, XOSC32KTRIM; };
extern struct clock_regs clock_regs;
extern struct oscillator_regs oscillator_regs;
extern struct ficr_regs ficr_regs;
#define NRF_CLOCK (&clock_regs)
#define NRF_OSCILLATORS (&oscillator_regs)
#define NRF_FICR (&ficr_regs)
#define CLOCK_XO_STAT_STATE_Msk (1U << 16)
#define OSCILLATORS_XOSC32KI_BYPASS_BYPASS_Disabled 0
#define FICR_XOSC32MTRIM_SLOPE_Msk 511U
#define FICR_XOSC32MTRIM_SLOPE_Pos 0
#define FICR_XOSC32KTRIM_SLOPE_Msk 511U
#define FICR_XOSC32KTRIM_SLOPE_Pos 0
#define FICR_XOSC32MTRIM_OFFSET_Msk (1023U << 16)
#define FICR_XOSC32MTRIM_OFFSET_Pos 16
#define FICR_XOSC32KTRIM_OFFSET_Msk (1023U << 16)
#define FICR_XOSC32KTRIM_OFFSET_Pos 16
''')
        (directory / 'probe.c').write_text('''
#include "nrf.h"
struct clock_regs clock_regs;
struct oscillator_regs oscillator_regs;
struct ficr_regs ficr_regs;
extern void nrfkit_board_init(void);
uint32_t probe(uint32_t trim, uint32_t active, uint32_t lf) {
    ficr_regs.XOSC32MTRIM = ficr_regs.XOSC32KTRIM = trim;
    clock_regs.XO.RUN = clock_regs.LFCLK.RUN = active & 1;
    clock_regs.XO.STAT = (active & 2) ? CLOCK_XO_STAT_STATE_Msk : 0;
    oscillator_regs.XOSC32KI.STATUS = (active & 2) != 0;
    oscillator_regs.XOSC32M.CONFIG.INTCAP = 123;
    oscillator_regs.XOSC32KI.INTCAP = 123;
    nrfkit_board_init();
    return lf ? oscillator_regs.XOSC32KI.INTCAP : oscillator_regs.XOSC32M.CONFIG.INTCAP;
}
''')
        library = directory / 'probe.so'
        subprocess.run([compiler, '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                        '-I', str(directory), str(directory / 'probe.c'),
                        str(ROOT / 'src/boards/nrf54lm20dk/init.c'), '-o', str(library)],
                       check=True, capture_output=True)
        cls.library = ctypes.CDLL(str(library))
        cls.probe = cls.library.probe
        cls.probe.argtypes = [ctypes.c_uint32] * 3
        cls.probe.restype = ctypes.c_uint32

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_signed_trim_and_rounding_match_datasheet_equations(self):
        for slope in range(-256, 256):
            for offset in (0, 1, 63, 64, 511, 1023):
                trim = (slope & 511) | (offset << 16)
                hf = (Fraction('15') - Fraction('5.5')) * (slope + 791) / 256 + Fraction(offset, 64)
                lf = (2 * 17 - 12) * (Fraction(slope, 512) + Fraction('0.765625')) + Fraction(offset, 64)
                self.assertEqual(self.probe(trim, 0, 0), int(hf + Fraction(1, 2)))
                self.assertEqual(self.probe(trim, 0, 1), int(lf + Fraction(1, 2)))

    def test_preserves_requested_or_running_crystal_loads(self):
        for active in (1, 2, 3):
            for lf in (0, 1):
                self.assertEqual(self.probe(0, active, lf), 123)
