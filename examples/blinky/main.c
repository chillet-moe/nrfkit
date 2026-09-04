/* SPDX-License-Identifier: BSD-3-Clause */

#include <nrf.h>
#include <nrf_cmake_sdk/board.h>

int main(void)
{
    NRF_CMAKE_SDK_LED0_PORT->PIN_CNF[NRF_CMAKE_SDK_LED0_PIN] =
        GPIO_PIN_CNF_DIR_Output << GPIO_PIN_CNF_DIR_Pos;

    for (;;) {
        NRF_CMAKE_SDK_LED0_PORT->OUTSET = 1u << NRF_CMAKE_SDK_LED0_PIN;
        for (volatile unsigned delay = 0; delay != 1000000u; ++delay) {
            __asm volatile ("nop");
        }
        NRF_CMAKE_SDK_LED0_PORT->OUTCLR = 1u << NRF_CMAKE_SDK_LED0_PIN;
        for (volatile unsigned delay = 0; delay != 1000000u; ++delay) {
            __asm volatile ("nop");
        }
    }
}
