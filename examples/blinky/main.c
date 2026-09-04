/* SPDX-License-Identifier: BSD-3-Clause */

#include <nrf.h>
#include <nrfkit/board.h>

int main(void)
{
    NRFKIT_LED0_PORT->PIN_CNF[NRFKIT_LED0_PIN] =
        GPIO_PIN_CNF_DIR_Output << GPIO_PIN_CNF_DIR_Pos;

    for (;;) {
        NRFKIT_LED0_PORT->OUTSET = 1u << NRFKIT_LED0_PIN;
        for (volatile unsigned delay = 0; delay != 1000000u; ++delay) {
            __asm volatile ("nop");
        }
        NRFKIT_LED0_PORT->OUTCLR = 1u << NRFKIT_LED0_PIN;
        for (volatile unsigned delay = 0; delay != 1000000u; ++delay) {
            __asm volatile ("nop");
        }
    }
}
