/* SPDX-License-Identifier: BSD-3-Clause */

#include <nrfkit/sdc.h>
#include <nrfkit/usbhs.h>
#include <nrfx_rramc.h>

extern "C" void usb_dc_low_level_deinit(unsigned char busid);
extern "C" void usb_dc_low_level_init(unsigned char busid);

static_assert(__cplusplus >= 202302L);

alignas(8) static unsigned char controller_memory[65536];

extern "C" int main()
{
    /* Direct RRAMC use is confined to the phase before MPSL takes ownership. */
    if (!nrfx_rramc_ready_check()) {
        return 1;
    }

    const nrfkit_sdc_config config = {
        .lfclk_source = NRFKIT_SDC_LFCLK_XTAL,
        .lfclk_accuracy_ppm = 20,
        .rc_calibration_interval_250_ms = 0,
        .rc_temperature_interval_count = 0,
        .hfclk_startup_time_us = 1400,
    };
    size_t required_memory = 0;
    if (nrfkit_sdc_required_memory(&config, &required_memory) != 0 ||
        required_memory > sizeof(controller_memory) ||
        nrfkit_sdc_enable(&config, controller_memory,
                          sizeof(controller_memory)) != 0) {
        return 2;
    }

    /* Combined targets retain MPSL and request HFCLK24M through its arbiter. */
    usb_dc_low_level_init(0);
    if (nrfkit_usbhs_connect() != NRFKIT_USBHS_OK) {
        return 3;
    }
    usb_dc_low_level_deinit(0);
    return nrfkit_sdc_disable();
}
