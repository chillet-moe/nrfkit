// SPDX-License-Identifier: BSD-3-Clause

#if LINKED_SERIAL
#include <nrfx_timer.h>
#include <nrfx_uarte.h>
#elif LINKED_SDC
#include <nrfkit/sdc.h>
alignas(8) static unsigned char sdc_memory[65536];
#elif LINKED_RADIO
#include <nrfkit/radio.h>
#elif LINKED_TIMESLOT
#include <nrfkit/timeslot.h>
#elif LINKED_RRAM
#include <nrfkit/rram.h>
#elif LINKED_USB
#include <nrfkit/usbhs.h>
#endif

extern "C" int main()
{
#if LINKED_SERIAL
    (void)nrfx_timer_init_check(nullptr);
    (void)nrfx_uarte_init_check(nullptr);
#elif LINKED_SDC
    const struct nrfkit_sdc_config config = {
        .lfclk_source = NRFKIT_SDC_LFCLK_XTAL,
        .lfclk_accuracy_ppm = 20,
        .hfclk_startup_time_us = 1400,
    };
    (void)nrfkit_sdc_enable(&config, sdc_memory, sizeof(sdc_memory));
#elif LINKED_RADIO
    (void)nrfkit_radio_configure_packet(NRFKIT_RADIO_OWNER_PROPRIETARY, nullptr);
#elif LINKED_TIMESLOT
    (void)nrfkit_timeslot_is_open();
#elif LINKED_RRAM
    (void)nrfkit_rram_result();
#elif LINKED_USB
    (void)nrfkit_usbhs_vbus_present();
#endif
    return 0;
}
