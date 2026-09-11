/* SPDX-License-Identifier: BSD-3-Clause */

#include <stdint.h>
#include <nrf.h>

volatile uint32_t nrfkit_power_stage;

int main(void)
{
    nrfkit_power_stage = 1U;
    for (;;) {
        __WFE();
    }
}
