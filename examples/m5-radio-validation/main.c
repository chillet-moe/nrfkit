/* SPDX-License-Identifier: BSD-3-Clause */

#include <stddef.h>
#include <stdint.h>

#include <nrf.h>
#include <nrfkit/board.h>
#include <nrfkit/radio.h>
#include <hal/nrf_dppi.h>
#include <hal/nrf_radio.h>
#include <hal/nrf_timer.h>
#include <nrfx_clock.h>

#define PASS_TOKEN "NRFKIT_M5_RADIO PASS\r\n"
#define TIMEOUT UINT32_C(10000000)
#define RADIO_DPPI_CHANNEL 0U

static uint8_t tx_packet[33] __attribute__((aligned(4)));
static uint8_t token[sizeof(PASS_TOKEN) - 1U] __attribute__((aligned(4)));
static volatile uint32_t radio_disabled_irq;
volatile uint32_t nrfkit_m5_radio_stage;
volatile int32_t nrfkit_m5_radio_result;

static void require_stage(int condition, uint32_t stage)
{
    if (!condition) {
        nrfkit_m5_radio_stage = stage;
        nrfkit_assert_fail();
    }
}

#define REQUIRE(condition, stage) require_stage((condition), (stage))

void RADIO_0_IRQHandler(void)
{
    if (nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_DISABLED)) {
        nrf_radio_event_clear(NRF_RADIO, NRF_RADIO_EVENT_DISABLED);
        radio_disabled_irq = 1U;
    }
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
    nrfkit_m5_radio_stage = 1U;
    REQUIRE(nrfx_clock_init(NULL) == 0, 1U);
    nrfx_clock_start(NRF_CLOCK_DOMAIN_HFCLK);
    /* Blocking start completion is the clock contract used by the packet engine. */
    nrfkit_m5_radio_stage = 2U;

    nrfkit_m5_radio_stage = 3U;
    REQUIRE(nrfkit_radio_acquire(NRFKIT_RADIO_OWNER_PROPRIETARY) == NRFKIT_RADIO_OK, 3U);
    nrfkit_m5_radio_stage = 4U;
    REQUIRE(nrfkit_radio_acquire(NRFKIT_RADIO_OWNER_BLE) == NRFKIT_RADIO_ERR_BUSY, 4U);
    struct nrfkit_radio_packet_config const config = {
        .phy = NRFKIT_RADIO_PHY_2MBIT,
        .channel = 16U,
        .maximum_payload = 32U,
        .whitening_iv = 0x53U,
        .whitening_polynomial = 0x89U,
        .access_address = UINT32_C(0x71764567),
        .crc_initial = UINT32_C(0x555555),
        .crc_polynomial = UINT32_C(0x00065B),
    };
    nrfkit_m5_radio_stage = 5U;
    nrfkit_m5_radio_result = nrfkit_radio_configure_packet(
        NRFKIT_RADIO_OWNER_PROPRIETARY, &config);
    REQUIRE(nrfkit_m5_radio_result == NRFKIT_RADIO_OK, 5U);
    REQUIRE(nrf_radio_frequency_get(NRF_RADIO) == 2400U + config.channel, 6U);
    REQUIRE(nrf_radio_base0_get(NRF_RADIO) == UINT32_C(0x76456700), 7U);
    REQUIRE(nrf_radio_prefix0_get(NRF_RADIO) == 0x71U, 8U);
    REQUIRE(nrf_radio_datawhiteiv_get(NRF_RADIO) == config.whitening_iv, 9U);
    REQUIRE(nrf_radio_datawhite_poly_get(NRF_RADIO) == config.whitening_polynomial, 10U);
    REQUIRE(nrf_radio_crcinit_get(NRF_RADIO) == config.crc_initial, 11U);

    tx_packet[0] = 32U;
    for (size_t index = 1; index < sizeof(tx_packet); ++index) {
        tx_packet[index] = (uint8_t)(index ^ 0xA5U);
    }
    nrf_radio_packetptr_set(NRF_RADIO, tx_packet);
    nrf_radio_event_clear(NRF_RADIO, NRF_RADIO_EVENT_READY);
    nrf_radio_event_clear(NRF_RADIO, NRF_RADIO_EVENT_END);
    nrf_radio_event_clear(NRF_RADIO, NRF_RADIO_EVENT_PHYEND);
    nrf_radio_event_clear(NRF_RADIO, NRF_RADIO_EVENT_DISABLED);
    nrf_radio_shorts_set(NRF_RADIO,
        NRF_RADIO_SHORT_READY_START_MASK | NRF_RADIO_SHORT_PHYEND_DISABLE_MASK);
    nrf_radio_int_enable(NRF_RADIO, NRF_RADIO_INT_DISABLED_MASK);
    NVIC_ClearPendingIRQ(RADIO_0_IRQn);
    NVIC_EnableIRQ(RADIO_0_IRQn);

    nrf_timer_task_trigger(NRF_TIMER10, NRF_TIMER_TASK_STOP);
    nrf_timer_task_trigger(NRF_TIMER10, NRF_TIMER_TASK_CLEAR);
    nrf_timer_mode_set(NRF_TIMER10, NRF_TIMER_MODE_TIMER);
    nrf_timer_bit_width_set(NRF_TIMER10, NRF_TIMER_BIT_WIDTH_32);
    nrf_timer_prescaler_set(NRF_TIMER10, 4U);
    nrf_timer_cc_set(NRF_TIMER10, NRF_TIMER_CC_CHANNEL0, 1000U);
    nrf_timer_shorts_set(NRF_TIMER10, NRF_TIMER_SHORT_COMPARE0_STOP_MASK);
    nrf_timer_event_clear(NRF_TIMER10, NRF_TIMER_EVENT_COMPARE0);
    nrf_timer_publish_set(NRF_TIMER10, NRF_TIMER_EVENT_COMPARE0, RADIO_DPPI_CHANNEL);
    nrf_radio_subscribe_set(NRF_RADIO, NRF_RADIO_TASK_TXEN, RADIO_DPPI_CHANNEL);
    nrf_dppi_channels_enable(NRF_DPPIC10, 1U << RADIO_DPPI_CHANNEL);

    nrfkit_m5_radio_stage = 12U;
    nrf_timer_task_trigger(NRF_TIMER10, NRF_TIMER_TASK_START);
    __SEV();
    __WFE();
    uint32_t timeout = TIMEOUT;
    while (radio_disabled_irq == 0U && timeout-- != 0U) {
        __WFE();
    }
    REQUIRE(timeout != 0U, 12U);
    REQUIRE(nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_READY), 13U);
    REQUIRE(nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_END), 14U);
    REQUIRE(nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_PHYEND), 15U);
    REQUIRE(nrf_radio_state_get(NRF_RADIO) == NRF_RADIO_STATE_DISABLED, 16U);

    nrf_dppi_channels_disable(NRF_DPPIC10, 1U << RADIO_DPPI_CHANNEL);
    nrf_timer_publish_clear(NRF_TIMER10, NRF_TIMER_EVENT_COMPARE0);
    nrf_radio_subscribe_clear(NRF_RADIO, NRF_RADIO_TASK_TXEN);
    nrf_radio_int_disable(NRF_RADIO, UINT32_MAX);
    nrf_radio_shorts_set(NRF_RADIO, 0U);
    NVIC_DisableIRQ(RADIO_0_IRQn);
    REQUIRE(nrfkit_radio_release(NRFKIT_RADIO_OWNER_BLE) == NRFKIT_RADIO_ERR_OWNER, 17U);
    REQUIRE(nrfkit_radio_release(
        NRFKIT_RADIO_OWNER_PROPRIETARY) == NRFKIT_RADIO_OK, 18U);
    REQUIRE(nrfkit_radio_acquire(NRFKIT_RADIO_OWNER_BLE) == NRFKIT_RADIO_OK, 19U);
    REQUIRE(nrfkit_radio_release(NRFKIT_RADIO_OWNER_BLE) == NRFKIT_RADIO_OK, 20U);

    nrfkit_m5_radio_stage = 21U;
    uart_write_token();
    nrfkit_m5_radio_stage = 0U;
    for (;;) {
        __WFE();
    }
}
