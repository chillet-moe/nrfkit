/* SPDX-License-Identifier: BSD-3-Clause */

#include <stddef.h>
#include <stdint.h>

#include <nrf.h>
#include <nrfkit/board.h>

#ifndef NRFKIT_BUILD_ID
#error "NRFKIT_BUILD_ID must be defined"
#endif

#define BOOT_TOKEN "NRFKIT_BOOT " NRFKIT_BUILD_ID "\r\n"

volatile uint32_t nrfkit_reset_reason;
volatile uint32_t nrfkit_gdb_scratch;
volatile uint32_t nrfkit_main_observed;

static uint8_t tx_buffer[sizeof(BOOT_TOKEN) - 1u] __attribute__((aligned(4)));

__attribute__((noinline)) void nrfkit_post_main(void)
{
    __asm volatile ("" ::: "memory");
}

int main(void)
{
    nrfkit_reset_reason = NRF_RESET->RESETREAS;
    nrfkit_gdb_scratch = 0;
    nrfkit_main_observed = UINT32_C(0x4D324D41);

    NRFKIT_LED0_PORT->PIN_CNF[NRFKIT_LED0_PIN] =
        GPIO_PIN_CNF_DIR_Output << GPIO_PIN_CNF_DIR_Pos;
    NRFKIT_LED0_PORT->OUTSET = 1u << NRFKIT_LED0_PIN;

    static const char token[] = BOOT_TOKEN;
    for (size_t index = 0; index < sizeof(tx_buffer); ++index) {
        tx_buffer[index] = (uint8_t)token[index];
    }

    NRFKIT_VCOM_TX_GPIO->OUTSET = 1u << NRFKIT_VCOM_TX_PIN;
    NRFKIT_VCOM_TX_GPIO->PIN_CNF[NRFKIT_VCOM_TX_PIN] =
        (GPIO_PIN_CNF_DIR_Output << GPIO_PIN_CNF_DIR_Pos) |
        (GPIO_PIN_CNF_INPUT_Disconnect << GPIO_PIN_CNF_INPUT_Pos) |
        (GPIO_PIN_CNF_PULL_Disabled << GPIO_PIN_CNF_PULL_Pos) |
        (GPIO_PIN_CNF_DRIVE0_S0 << GPIO_PIN_CNF_DRIVE0_Pos) |
        (GPIO_PIN_CNF_DRIVE1_S1 << GPIO_PIN_CNF_DRIVE1_Pos) |
        (GPIO_PIN_CNF_SENSE_Disabled << GPIO_PIN_CNF_SENSE_Pos);
    NRFKIT_VCOM_UARTE->PSEL.TXD =
        (NRFKIT_VCOM_TX_PIN << UARTE_PSEL_TXD_PIN_Pos) |
        (NRFKIT_VCOM_TX_PORT << UARTE_PSEL_TXD_PORT_Pos) |
        (UARTE_PSEL_TXD_CONNECT_Connected << UARTE_PSEL_TXD_CONNECT_Pos);
    NRFKIT_VCOM_UARTE->BAUDRATE = NRFKIT_VCOM_BAUDRATE;
    NRFKIT_VCOM_UARTE->CONFIG = 0;
    NRFKIT_VCOM_UARTE->ENABLE = UARTE_ENABLE_ENABLE_Enabled;
    NRFKIT_VCOM_UARTE->EVENTS_DMA.TX.END = 0;
    NRFKIT_VCOM_UARTE->EVENTS_DMA.TX.BUSERROR = 0;
    NRFKIT_VCOM_UARTE->DMA.TX.PTR = (uint32_t)(uintptr_t)tx_buffer;
    NRFKIT_VCOM_UARTE->DMA.TX.MAXCNT = sizeof(tx_buffer);
    NRFKIT_VCOM_UARTE->TASKS_DMA.TX.START =
        UARTE_TASKS_DMA_TX_START_START_Trigger;
    while (NRFKIT_VCOM_UARTE->EVENTS_DMA.TX.END == 0u) {
        if (NRFKIT_VCOM_UARTE->EVENTS_DMA.TX.BUSERROR != 0u) {
            __asm volatile ("udf #0");
        }
    }

    nrfkit_post_main();
    for (;;) {
        NRFKIT_LED0_PORT->OUT ^= 1u << NRFKIT_LED0_PIN;
        for (volatile uint32_t delay = 0; delay != 1000000u; ++delay) {
            __asm volatile ("nop");
        }
    }
}
