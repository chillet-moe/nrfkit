/* SPDX-License-Identifier: BSD-3-Clause */

#include <stddef.h>
#include <stdint.h>

#include <nrf.h>
#include <nrfkit/runtime.h>
#include <nrfkit/board.h>
#include <nrfx_clock.h>
#include <nrfx_grtc.h>
#include <helpers/nrfx_ram_ctrl.h>
#include <helpers/nrfx_reset_reason.h>

#define PASS_TOKEN "NRFKIT_M3_POWER PASS\r\n"
#define RETAINED_MAGIC UINT32_C(0x4D33504D)

struct retained_state {
    uint32_t magic;
    uint32_t inverse;
    uint32_t phase;
};

static volatile struct retained_state retained __attribute__((section(".noinit.m3_power")));
volatile uint32_t nrfkit_m3_power_stage;
static volatile uint32_t wake_irq;
static uint8_t token[sizeof(PASS_TOKEN) - 1U] __attribute__((aligned(4)));

static void require_stage(int condition, uint32_t stage)
{
    if (!condition) {
        nrfkit_m3_power_stage = stage;
        nrfkit_assert_fail();
    }
}

#define REQUIRE(condition, stage) require_stage((condition), (stage))

static void wake_handler(int32_t event, uint64_t compare_value, void *context)
{
    (void)event;
    (void)compare_value;
    (void)context;
    wake_irq = 1U;
}

static void uart_write_token(void)
{
    for (size_t index = 0; index < sizeof(token); ++index) {
        token[index] = (uint8_t)PASS_TOKEN[index];
    }
    NRFKIT_VCOM_TX_GPIO->OUTSET = 1U << NRFKIT_VCOM_TX_PIN;
    NRFKIT_VCOM_TX_GPIO->PIN_CNF[NRFKIT_VCOM_TX_PIN] =
        (GPIO_PIN_CNF_DIR_Output << GPIO_PIN_CNF_DIR_Pos) |
        (GPIO_PIN_CNF_INPUT_Disconnect << GPIO_PIN_CNF_INPUT_Pos);
    NRFKIT_VCOM_UARTE->PSEL.TXD =
        (NRFKIT_VCOM_TX_PIN << UARTE_PSEL_TXD_PIN_Pos) |
        (NRFKIT_VCOM_TX_PORT << UARTE_PSEL_TXD_PORT_Pos);
    NRFKIT_VCOM_UARTE->BAUDRATE = NRFKIT_VCOM_BAUDRATE;
    NRFKIT_VCOM_UARTE->ENABLE = UARTE_ENABLE_ENABLE_Enabled;
    NRFKIT_VCOM_UARTE->EVENTS_DMA.TX.END = 0U;
    NRFKIT_VCOM_UARTE->DMA.TX.PTR = (uint32_t)(uintptr_t)token;
    NRFKIT_VCOM_UARTE->DMA.TX.MAXCNT = sizeof(token);
    NRFKIT_VCOM_UARTE->TASKS_DMA.TX.START = UARTE_TASKS_DMA_TX_START_START_Trigger;
    while (NRFKIT_VCOM_UARTE->EVENTS_DMA.TX.END == 0U) {
        __NOP();
    }
}

int main(void)
{
    if (retained.magic != RETAINED_MAGIC || retained.inverse != ~RETAINED_MAGIC ||
        retained.phase != 1U) {
        retained.magic = RETAINED_MAGIC;
        retained.inverse = ~RETAINED_MAGIC;
        retained.phase = 1U;
        nrfx_ram_ctrl_retention_enable_set((const void *)&retained, sizeof(retained), true);
        __DSB();
        nrfkit_system_reset();
    }
    REQUIRE(nrfx_reset_reason_get() != 0U, 1U);
    retained.phase = 2U;

    REQUIRE(nrfx_clock_init(NULL) == 0, 2U);
    nrfx_clock_start(NRF_CLOCK_DOMAIN_LFCLK);
    REQUIRE(nrfx_clock_is_running(NRF_CLOCK_DOMAIN_LFCLK, NULL), 3U);
    REQUIRE(nrfx_grtc_init(NRFX_GRTC_DEFAULT_CONFIG_IRQ_PRIORITY) == 0, 4U);
    uint8_t main_channel;
    REQUIRE(nrfx_grtc_syscounter_start(true, &main_channel) == 0, 5U);

    uint8_t wake_channel;
    REQUIRE(nrfx_grtc_channel_alloc(&wake_channel) == 0, 6U);
    nrfx_grtc_channel_t wake = {
        .handler = wake_handler,
        .channel = wake_channel,
    };
    uint64_t const start = nrfx_grtc_syscounter_get();
    REQUIRE(nrfx_grtc_syscounter_cc_absolute_set(
        &wake, start + UINT64_C(100000), true) == 0, 7U);

    __SEV();
    __WFE();
    while (wake_irq == 0U) {
        __WFE();
    }

    uint64_t const elapsed = nrfx_grtc_syscounter_get() - start;
    REQUIRE(elapsed >= UINT64_C(90000) && elapsed <= UINT64_C(150000), 8U);
    REQUIRE(retained.magic == RETAINED_MAGIC && retained.inverse == ~RETAINED_MAGIC &&
        retained.phase == 2U, 9U);
    uart_write_token();
    for (;;) {
        __WFE();
    }
}
