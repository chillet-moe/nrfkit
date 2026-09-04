/* SPDX-License-Identifier: BSD-3-Clause */

#include <nrf.h>
#include <hal/nrf_cache.h>
#include <hal/nrf_grtc.h>
#include <hal/nrf_oscillators.h>
#include <hal/nrf_regulators.h>
#include <lib/nrfx_coredep.h>

#include <nrfkit/board.h>

void nrfkit_board_prepare_s115(void)
{
    /* nRF54LM20 DK BOM values: LFXO 17 pF and HFXO 15 pF internal load. */
    const uint32_t trim32k = NRF_FICR->XOSC32KTRIM;
    const uint32_t slope32k_field =
        (trim32k & FICR_XOSC32KTRIM_SLOPE_Msk) >>
        FICR_XOSC32KTRIM_SLOPE_Pos;
    const uint32_t slope32k_mask =
        FICR_XOSC32KTRIM_SLOPE_Msk >> FICR_XOSC32KTRIM_SLOPE_Pos;
    const uint32_t slope32k_sign = slope32k_mask - (slope32k_mask >> 1U);
    const int32_t slope32k =
        (int32_t)(slope32k_field ^ slope32k_sign) - (int32_t)slope32k_sign;
    const uint32_t offset32k =
        (trim32k & FICR_XOSC32KTRIM_OFFSET_Msk) >>
        FICR_XOSC32KTRIM_OFFSET_Pos;
    const uint32_t lfxo_scaled =
        (2U * 17000U - 12000U) * (uint32_t)(slope32k + 392) +
        (offset32k << 3U) * 1000U;
    const uint32_t lfxo_cap =
        lfxo_scaled / 512000U + (lfxo_scaled % 512000U >= 256000U);
    nrf_oscillators_lfxo_cap_set(
        NRF_OSCILLATORS, (nrf_oscillators_lfxo_cap_t)lfxo_cap);
    nrf_oscillators_lfxo_bypass_set(NRF_OSCILLATORS, false);

    const uint32_t trim32m = NRF_FICR->XOSC32MTRIM;
    const uint32_t slope32m_field =
        (trim32m & FICR_XOSC32MTRIM_SLOPE_Msk) >>
        FICR_XOSC32MTRIM_SLOPE_Pos;
    const uint32_t slope32m_mask =
        FICR_XOSC32MTRIM_SLOPE_Msk >> FICR_XOSC32MTRIM_SLOPE_Pos;
    const uint32_t slope32m_sign = slope32m_mask - (slope32m_mask >> 1U);
    const int32_t slope32m =
        (int32_t)(slope32m_field ^ slope32m_sign) - (int32_t)slope32m_sign;
    const uint32_t offset32m =
        (trim32m & FICR_XOSC32MTRIM_OFFSET_Msk) >>
        FICR_XOSC32MTRIM_OFFSET_Pos;
    const uint32_t hfxo_scaled =
        (((15000U - 5500U) * (uint32_t)(slope32m + 791)) +
         (offset32m << 2U) * 1000U) >> 8U;
    const uint32_t hfxo_cap =
        hfxo_scaled / 1000U + (hfxo_scaled % 1000U >= 500U);
    nrf_oscillators_hfxo_cap_set(NRF_OSCILLATORS, true, hfxo_cap);

    nrf_regulators_vreg_enable_set(
        NRF_REGULATORS, NRF_REGULATORS_VREG_MAIN, true);
    nrf_cache_enable(NRF_ICACHE);
}

int nrfkit_board_start_s115_grtc(void)
{
    nrf_grtc_clksel_set(NRF_GRTC, NRF_GRTC_CLKSEL_LFXO);
    nrf_grtc_sys_counter_set(NRF_GRTC, false);
    nrf_grtc_sys_counter_auto_mode_set(NRF_GRTC, true);
    nrf_grtc_timeout_set(NRF_GRTC, 5U);
    nrf_grtc_waketime_set(NRF_GRTC, 4U);
    nrf_grtc_task_trigger(NRF_GRTC, NRF_GRTC_TASK_START);
    __DSB();

    /* Match the official timer setup's three low-frequency clock cycles. */
    nrfx_coredep_delay_us(93U);
    nrf_grtc_sys_counter_set(NRF_GRTC, true);
    __DSB();

    const bool was_active = nrf_grtc_sys_counter_active_check(NRF_GRTC);
    if (!was_active) {
        nrf_grtc_sys_counter_active_set(NRF_GRTC, true);
        __DSB();
    }

    uint32_t timeout = SystemCoreClock;
    while (timeout-- != 0U) {
        (void)nrf_grtc_sys_counter_low_get(NRF_GRTC);
        __DMB();
        if ((nrf_grtc_sys_counter_high_get(NRF_GRTC) &
             GRTC_SYSCOUNTER_SYSCOUNTERH_BUSY_Msk) ==
            GRTC_SYSCOUNTER_SYSCOUNTERH_BUSY_Ready) {
            if (!was_active) {
                nrf_grtc_sys_counter_active_set(NRF_GRTC, false);
                __DSB();
            }
            return 0;
        }
    }

    if (!was_active) {
        nrf_grtc_sys_counter_active_set(NRF_GRTC, false);
        __DSB();
    }
    return -1;
}
