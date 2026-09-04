/* SPDX-License-Identifier: BSD-3-Clause */

#include <stddef.h>
#include <stdint.h>

#include <nrf.h>
#include <nrf_cmake_sdk/board.h>

#ifndef NRF_CMAKE_SDK_BUILD_ID
#error "NRF_CMAKE_SDK_BUILD_ID must be defined"
#endif

#define BOOT_TOKEN "NRF_CMAKE_SDK_BOOT " NRF_CMAKE_SDK_BUILD_ID "\r\n"

volatile uint32_t nrf_cmake_sdk_reset_reason;
volatile uint32_t nrf_cmake_sdk_gdb_scratch;
volatile uint32_t nrf_cmake_sdk_main_observed;

static uint8_t tx_buffer[sizeof(BOOT_TOKEN) - 1u] __attribute__((aligned(4)));

__attribute__((noinline)) void nrf_cmake_sdk_post_main(void)
{
    __asm volatile ("" ::: "memory");
}

int main(void)
{
    nrf_cmake_sdk_reset_reason = NRF_RESET->RESETREAS;
    nrf_cmake_sdk_gdb_scratch = 0;
    nrf_cmake_sdk_main_observed = UINT32_C(0x4D324D41);

    NRF_CMAKE_SDK_LED0_PORT->PIN_CNF[NRF_CMAKE_SDK_LED0_PIN] =
        GPIO_PIN_CNF_DIR_Output << GPIO_PIN_CNF_DIR_Pos;
    NRF_CMAKE_SDK_LED0_PORT->OUTSET = 1u << NRF_CMAKE_SDK_LED0_PIN;

    static const char token[] = BOOT_TOKEN;
    for (size_t index = 0; index < sizeof(tx_buffer); ++index) {
        tx_buffer[index] = (uint8_t)token[index];
    }

    NRF_CMAKE_SDK_VCOM_TX_GPIO->OUTSET = 1u << NRF_CMAKE_SDK_VCOM_TX_PIN;
    NRF_CMAKE_SDK_VCOM_TX_GPIO->PIN_CNF[NRF_CMAKE_SDK_VCOM_TX_PIN] =
        (GPIO_PIN_CNF_DIR_Output << GPIO_PIN_CNF_DIR_Pos) |
        (GPIO_PIN_CNF_INPUT_Disconnect << GPIO_PIN_CNF_INPUT_Pos) |
        (GPIO_PIN_CNF_PULL_Disabled << GPIO_PIN_CNF_PULL_Pos) |
        (GPIO_PIN_CNF_DRIVE0_S0 << GPIO_PIN_CNF_DRIVE0_Pos) |
        (GPIO_PIN_CNF_DRIVE1_S1 << GPIO_PIN_CNF_DRIVE1_Pos) |
        (GPIO_PIN_CNF_SENSE_Disabled << GPIO_PIN_CNF_SENSE_Pos);
    NRF_CMAKE_SDK_VCOM_UARTE->PSEL.TXD =
        (NRF_CMAKE_SDK_VCOM_TX_PIN << UARTE_PSEL_TXD_PIN_Pos) |
        (NRF_CMAKE_SDK_VCOM_TX_PORT << UARTE_PSEL_TXD_PORT_Pos) |
        (UARTE_PSEL_TXD_CONNECT_Connected << UARTE_PSEL_TXD_CONNECT_Pos);
    NRF_CMAKE_SDK_VCOM_UARTE->BAUDRATE = NRF_CMAKE_SDK_VCOM_BAUDRATE;
    NRF_CMAKE_SDK_VCOM_UARTE->CONFIG = 0;
    NRF_CMAKE_SDK_VCOM_UARTE->ENABLE = UARTE_ENABLE_ENABLE_Enabled;
    NRF_CMAKE_SDK_VCOM_UARTE->EVENTS_DMA.TX.END = 0;
    NRF_CMAKE_SDK_VCOM_UARTE->EVENTS_DMA.TX.BUSERROR = 0;
    NRF_CMAKE_SDK_VCOM_UARTE->DMA.TX.PTR = (uint32_t)(uintptr_t)tx_buffer;
    NRF_CMAKE_SDK_VCOM_UARTE->DMA.TX.MAXCNT = sizeof(tx_buffer);
    NRF_CMAKE_SDK_VCOM_UARTE->TASKS_DMA.TX.START =
        UARTE_TASKS_DMA_TX_START_START_Trigger;
    while (NRF_CMAKE_SDK_VCOM_UARTE->EVENTS_DMA.TX.END == 0u) {
        if (NRF_CMAKE_SDK_VCOM_UARTE->EVENTS_DMA.TX.BUSERROR != 0u) {
            __asm volatile ("udf #0");
        }
    }

    nrf_cmake_sdk_post_main();
    for (;;) {
        NRF_CMAKE_SDK_LED0_PORT->OUT ^= 1u << NRF_CMAKE_SDK_LED0_PIN;
        for (volatile uint32_t delay = 0; delay != 1000000u; ++delay) {
            __asm volatile ("nop");
        }
    }
}
