/* SPDX-License-Identifier: BSD-3-Clause */

#include <nrf.h>
#include <nrfkit/runtime.h>

/* A board target may supply oscillator configuration; chip-only clients need
 * no board dependency. Custom runtimes call nrfkit_platform_init explicitly. */
extern void nrfkit_board_init(void) __attribute__((weak));

void nrfkit_platform_init(void)
{
    /* LM20 Datasheet v1.0 sections 4.2.3 and 5.7.1: neither default is
     * supplied by MDK SystemInit. DC/DC is the normal supported supply mode. */
    NRF_REGULATORS->VREGMAIN.DCDCEN = REGULATORS_VREGMAIN_DCDCEN_VAL_Enabled;
    NRF_ICACHE->ENABLE = CACHE_ENABLE_ENABLE_Enabled;
    __DSB();
    __ISB();
    SystemCoreClockUpdate();
    if (nrfkit_board_init != 0) {
        nrfkit_board_init();
    }
}
