/* SPDX-License-Identifier: BSD-3-Clause */

#include <nrf.h>

void nrfkit_board_init(void)
{
    /* DK: HFXO 15 pF, LFXO 17 pF internal loads (NCS v3.4.0 board).
     * Datasheet v1.0 sections 5.5.1/5.5.2 specify signed nine-bit slopes.
     * Keep fractional precision until rounding; the locked nrfx capacitor
     * macros do not implement these equations correctly. See the power audit. */
    const uint32_t hf_trim = NRF_FICR->XOSC32MTRIM;
    const uint32_t lf_trim = NRF_FICR->XOSC32KTRIM;
    const uint32_t hf_field = (hf_trim & FICR_XOSC32MTRIM_SLOPE_Msk) >>
                              FICR_XOSC32MTRIM_SLOPE_Pos;
    const uint32_t lf_field = (lf_trim & FICR_XOSC32KTRIM_SLOPE_Msk) >>
                              FICR_XOSC32KTRIM_SLOPE_Pos;
    const int32_t hf_slope = (int32_t)(hf_field ^ 256U) - 256;
    const int32_t lf_slope = (int32_t)(lf_field ^ 256U) - 256;
    const uint32_t hf_offset = (hf_trim & FICR_XOSC32MTRIM_OFFSET_Msk) >>
                               FICR_XOSC32MTRIM_OFFSET_Pos;
    const uint32_t lf_offset = (lf_trim & FICR_XOSC32KTRIM_OFFSET_Msk) >>
                               FICR_XOSC32KTRIM_OFFSET_Pos;
    const uint32_t hf_cap = (19U * (uint32_t)(hf_slope + 791) +
                              8U * hf_offset + 256U) / 512U;
    const uint32_t lf_cap = (22U * (uint32_t)(lf_slope + 392) +
                              8U * lf_offset + 256U) / 512U;

    /* Bootloader handoff may leave crystals running. Their owner must stop
     * them before changing loads; preserve active clocks and their requests. */
    if (NRF_CLOCK->XO.RUN == 0U &&
        (NRF_CLOCK->XO.STAT & CLOCK_XO_STAT_STATE_Msk) == 0U) {
        NRF_OSCILLATORS->XOSC32M.CONFIG.INTCAP = hf_cap;
    }
    if (NRF_CLOCK->LFCLK.RUN == 0U && NRF_OSCILLATORS->XOSC32KI.STATUS == 0U) {
        NRF_OSCILLATORS->XOSC32KI.INTCAP = lf_cap;
        NRF_OSCILLATORS->XOSC32KI.BYPASS =
            OSCILLATORS_XOSC32KI_BYPASS_BYPASS_Disabled;
    }
}
