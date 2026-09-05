/* SPDX-License-Identifier: BSD-3-Clause */

#include <stddef.h>
#include <stdint.h>

#include <nrfkit/board.h>
#include <nrfkit/nrfx.h>
#include <nrfx_clock.h>
#include <nrfx_gpiote.h>
#include <nrfx_grtc.h>
#include <nrfx_timer.h>
#include <nrfx_uarte.h>
#include <helpers/nrfx_gppi.h>
#include <helpers/nrfx_ram_ctrl.h>
#include <helpers/nrfx_reset_reason.h>

#define PASS_TOKEN "NRFKIT_M3_CORE PASS\r\n"
#define RETAINED_MAGIC UINT32_C(0x4D335254)
#define LED_PIN NRF_PIN_PORT_TO_PIN_NUMBER(NRFKIT_LED0_PIN, 1U)
#define VCOM_TX_PIN \
    NRF_PIN_PORT_TO_PIN_NUMBER(NRFKIT_VCOM_TX_PIN, NRFKIT_VCOM_TX_PORT)

struct retained_state {
    uint32_t magic;
    uint32_t inverse;
    uint32_t reset_count;
};

static volatile struct retained_state retained __attribute__((section(".noinit.m3_retained")));
static volatile uint32_t timer_events;
static volatile uint32_t uart_done;
volatile uint32_t nrfkit_m3_stage;
static uint8_t token[sizeof(PASS_TOKEN) - 1U] __attribute__((aligned(4)));

static nrfx_timer_t timer = NRFX_TIMER_INSTANCE(NRF_TIMER21);
static nrfx_gpiote_t gpiote = NRFX_GPIOTE_INSTANCE(NRF_GPIOTE20);
static nrfx_uarte_t uarte = NRFX_UARTE_INSTANCE(NRF_UARTE20);

NRFX_INSTANCE_IRQ_HANDLER_DEFINE(timer, 21, &timer);

static void timer_handler(nrf_timer_event_t event, void *context)
{
    (void)context;
    if (event == NRF_TIMER_EVENT_COMPARE0) {
        ++timer_events;
    }
}

static void uarte_handler(const nrfx_uarte_event_t *event, void *context)
{
    (void)context;
    if (event->type == NRFX_UARTE_EVT_TX_DONE) {
        uart_done = 1U;
    }
}

static void require_stage(int condition, uint32_t stage)
{
    if (!condition) {
        nrfkit_m3_stage = stage;
        nrfkit_assert_fail();
    }
}

#define REQUIRE(condition, stage) require_stage((condition), (stage))

int main(void)
{
    if (retained.magic != RETAINED_MAGIC || retained.inverse != ~RETAINED_MAGIC ||
        retained.reset_count != 1U) {
        retained.magic = RETAINED_MAGIC;
        retained.inverse = ~RETAINED_MAGIC;
        retained.reset_count = 1U;
        nrfx_ram_ctrl_retention_enable_set((const void *)&retained, sizeof(retained), true);
        __DSB();
        nrfkit_system_reset();
    }
    REQUIRE(retained.reset_count == 1U, 1U);
    retained.reset_count = 2U;
    nrfx_ram_ctrl_retention_enable_set((const void *)&retained, sizeof(retained), true);
    REQUIRE(nrfx_reset_reason_get() != 0U, 2U);

    REQUIRE(nrfx_clock_init(NULL) == 0, 3U);
    nrfx_clock_start(NRF_CLOCK_DOMAIN_LFCLK);
    REQUIRE(nrfx_clock_is_running(NRF_CLOCK_DOMAIN_LFCLK, NULL), 4U);

    REQUIRE(nrfx_grtc_init(NRFX_GRTC_DEFAULT_CONFIG_IRQ_PRIORITY) == 0, 5U);
    uint8_t grtc_main_channel;
    REQUIRE(nrfx_grtc_syscounter_start(true, &grtc_main_channel) == 0, 6U);
    uint64_t const grtc_start = nrfx_grtc_syscounter_get();

    nrfkit_gppi_init();
    REQUIRE(nrfx_gpiote_init(&gpiote, NRFX_GPIOTE_DEFAULT_CONFIG_IRQ_PRIORITY) == 0, 7U);
    uint8_t gpiote_channel;
    REQUIRE(nrfx_gpiote_channel_alloc(&gpiote, &gpiote_channel) == 0, 8U);
    const nrfx_gpiote_output_config_t output = {
        .drive = NRF_GPIO_PIN_S0S1,
        .input_connect = NRF_GPIO_PIN_INPUT_CONNECT,
        .pull = NRF_GPIO_PIN_NOPULL,
    };
    const nrfx_gpiote_task_config_t task = {
        .task_ch = gpiote_channel,
        .polarity = NRF_GPIOTE_POLARITY_TOGGLE,
        .init_val = NRF_GPIOTE_INITIAL_VALUE_LOW,
    };
    REQUIRE(nrfx_gpiote_output_configure(&gpiote, LED_PIN, &output, &task) == 0, 9U);
    nrfx_gpiote_out_task_enable(&gpiote, LED_PIN);

    uint32_t const frequency = NRF_TIMER_BASE_FREQUENCY_GET(timer.p_reg);
    nrfx_timer_config_t timer_config = NRFX_TIMER_DEFAULT_CONFIG(frequency);
    timer_config.bit_width = NRF_TIMER_BIT_WIDTH_32;
    REQUIRE(nrfx_timer_init(&timer, &timer_config, timer_handler) == 0, 10U);
    uint32_t const period = nrfx_timer_ms_to_ticks(&timer, 25U);
    nrfx_timer_extended_compare(&timer, NRF_TIMER_CC_CHANNEL0, period,
        NRF_TIMER_SHORT_COMPARE0_CLEAR_MASK, true);

    nrfx_gppi_handle_t connection;
    REQUIRE(nrfx_gppi_conn_alloc(
        nrfx_timer_compare_event_address_get(&timer, NRF_TIMER_CC_CHANNEL0),
        nrfx_gpiote_out_task_address_get(&gpiote, LED_PIN), &connection) == 0, 11U);
    nrfx_gppi_conn_enable(connection);
    nrfx_timer_enable(&timer);
    uint32_t timeout = UINT32_C(50000000);
    while (timer_events == 0U && timeout-- != 0U) {
        __NOP();
    }
    REQUIRE(timer_events != 0U, 16U);
    while (timer_events < 4U) {
        __WFE();
    }
    nrfx_timer_disable(&timer);
    uint64_t const elapsed = nrfx_grtc_syscounter_get() - grtc_start;
    uint64_t const expected_elapsed = NRF_GRTC_SYSCOUNTER_MAIN_FREQUENCY_HZ / 10U;
    REQUIRE(elapsed > (expected_elapsed * 8U) / 10U &&
        elapsed < (expected_elapsed * 12U) / 10U, 12U);
    REQUIRE(!nrfx_gpiote_in_is_set(LED_PIN), 13U);

    for (size_t index = 0; index < sizeof(token); ++index) {
        token[index] = (uint8_t)PASS_TOKEN[index];
    }
    nrfx_uarte_config_t uart_config = NRFX_UARTE_DEFAULT_CONFIG(
        VCOM_TX_PIN, NRF_UARTE_PSEL_DISCONNECTED);
    REQUIRE(nrfx_uarte_init(&uarte, &uart_config, uarte_handler) == 0, 14U);
    REQUIRE(nrfx_uarte_tx(&uarte, token, sizeof(token), 0U) == 0, 15U);
    timeout = UINT32_C(50000000);
    while (uart_done == 0U && timeout-- != 0U) {
        __NOP();
    }
    REQUIRE(uart_done != 0U, 17U);

    for (;;) {
        __WFE();
    }
}
