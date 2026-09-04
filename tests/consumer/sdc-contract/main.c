/* SPDX-License-Identifier: BSD-3-Clause */

#include <mpsl.h>
#include <nrfkit/sdc.h>
#include <sdc.h>

int main(void)
{
    struct nrfkit_sdc_config config = {
        .lfclk_source = NRFKIT_SDC_LFCLK_XTAL,
        .lfclk_accuracy_ppm = 20,
        .hfclk_startup_time_us = 1400,
    };
    size_t required_memory;
    return nrfkit_sdc_required_memory(&config, &required_memory);
}
