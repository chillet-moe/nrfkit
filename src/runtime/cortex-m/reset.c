/* SPDX-License-Identifier: BSD-3-Clause */

#include <nrf.h>
#include <nrfkit/runtime.h>

void nrfkit_system_reset(void)
{
    /* LM20 Engineering B v1.1 and Revision 1 v1.0, anomaly 63:
     * enter constant latency before AIRCR.SYSRESETREQ. Keep MPSL callbacks
     * from releasing this final request between the task and SYSRESETREQ.
     */
    __disable_irq();
    NRF_POWER->TASKS_CONSTLAT = POWER_TASKS_CONSTLAT_TASKS_CONSTLAT_Trigger;
    while ((NRF_POWER->CONSTLATSTAT & POWER_CONSTLATSTAT_STATUS_Msk) !=
           POWER_CONSTLATSTAT_STATUS_Enable) {
        __NOP();
    }
    __DSB();
    NVIC_SystemReset();
    __builtin_unreachable();
}
