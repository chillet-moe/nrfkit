/* SPDX-License-Identifier: BSD-3-Clause */

#include <stdint.h>
#include <nrf.h>
#include <hal/nrf_grtc.h>
#include <hal/nrf_regulators.h>
#include <helpers/nrfx_ram_ctrl.h>
#include <helpers/nrfx_reset_reason.h>
#include <nrfkit/runtime.h>
#include <nrfx_clock.h>
#include <nrfx_grtc.h>

#define RETAINED_MAGIC UINT32_C(0x504F5746)

struct retained_state {
    uint32_t magic;
    uint32_t inverse;
    uint32_t armed;
};

static volatile struct retained_state retained __attribute__((section(".noinit.power")));
volatile uint32_t nrfkit_power_stage;
volatile uint32_t nrfkit_power_reset_reason;

static void require(int condition, uint32_t stage)
{
    if (!condition) {
        nrfkit_power_stage = stage;
        nrfkit_assert_fail();
    }
}

int main(void)
{
    uint32_t const reason = nrfx_reset_reason_get();
    nrfkit_power_reset_reason = reason;
    if ((reason & RESET_RESETREAS_GRTC_Msk) != 0U) {
        require((reason & RESET_RESETREAS_DIF_Msk) == 0U &&
                retained.magic == RETAINED_MAGIC && retained.inverse == ~RETAINED_MAGIC &&
                retained.armed == 1U, 101U);
        retained.armed = 0U;
        nrfkit_power_stage = 2U;
        for (;;) {
            __WFE();
        }
    }
    require((CoreDebug->DHCSR & CoreDebug_DHCSR_C_DEBUGEN_Msk) == 0U, 102U);
    require(nrfx_clock_init(NULL) == 0, 103U);
    nrfx_clock_start(NRF_CLOCK_DOMAIN_LFCLK);
    require(nrfx_grtc_init(NRFX_GRTC_DEFAULT_CONFIG_IRQ_PRIORITY) == 0, 104U);
    uint8_t main_channel;
    require(nrfx_grtc_syscounter_start(true, &main_channel) == 0, 105U);
    uint8_t wake_channel;
    require(nrfx_grtc_channel_alloc(&wake_channel) == 0, 106U);
    nrfx_grtc_channel_t wake = {.channel = wake_channel};

    /* Datasheet v1.0 sections 5.2 and 8.11.2: keep SYSCOUNTER active while
     * programming CC, use the maximum 8-bit wake margin (about 7.8 ms), then
     * wait for RTCOMPARESYNC.
     * No SYSCOUNTER reads are allowed in the synchronization wait: those can
     * request the active state again. This probe needs no post-reset compare IRQ. */
    nrfx_grtc_active_request_set(true);
    nrfx_grtc_sleep_config_t sleep = {
        .timeout = 257U, .waketime = 255U, .auto_mode = false,
    };
    nrfx_grtc_sleep_configure(&sleep);
    /* Match the locked official GRTC wakeup_prepare compare-IRQ setup.
     * Detached GRTC wake remains unverified; see the measurement results. */
    require(nrfx_grtc_syscounter_cc_absolute_set(
                &wake, nrfx_grtc_syscounter_get() + UINT64_C(5000000), true) == 0, 107U);
    require(nrfx_grtc_syscounter_cc_disable(main_channel) == 0, 108U);
    retained.magic = RETAINED_MAGIC;
    retained.inverse = ~RETAINED_MAGIC;
    retained.armed = 1U;
    nrfx_ram_ctrl_retention_enable_set((const void *)&retained, sizeof(retained), true);
    nrfx_reset_reason_clear(UINT32_MAX);
    nrfx_clock_stop(NRF_CLOCK_DOMAIN_HFCLK);
    nrf_grtc_event_clear(NRF_GRTC, NRF_GRTC_EVENT_RTCOMPARESYNC);
    nrfx_grtc_active_request_set(false);
    uint32_t remaining = 2000000U;
    while (!nrf_grtc_event_check(NRF_GRTC, NRF_GRTC_EVENT_RTCOMPARESYNC) &&
           !nrfx_grtc_syscounter_compare_event_check(wake_channel) && remaining != 0U) {
        --remaining;
    }
    require(nrf_grtc_event_check(NRF_GRTC, NRF_GRTC_EVENT_RTCOMPARESYNC) &&
            !nrfx_grtc_syscounter_compare_event_check(wake_channel), 109U);
    nrfkit_power_stage = 1U;
    __DSB();
    nrf_regulators_system_off(NRF_REGULATORS);
    for (;;) {
        __WFE();
    }
}
