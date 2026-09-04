/* SPDX-License-Identifier: BSD-3-Clause */

#include <nrfx_clock.h>
#include <nrfx_gpiote.h>
#include <nrfx_grtc.h>
#include <nrfx_pwm.h>
#include <nrfx_rramc.h>
#include <nrfx_saadc.h>
#include <nrfx_spim.h>
#include <nrfx_timer.h>
#include <nrfx_twim.h>
#include <nrfx_uarte.h>
#include <nrfx_wdt.h>
#include <helpers/nrfx_gppi.h>
#include <helpers/nrfx_ram_ctrl.h>
#include <helpers/nrfx_reset_reason.h>

int main(void)
{
    for (;;) {
        __asm volatile ("wfe");
    }
}
