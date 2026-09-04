/* SPDX-License-Identifier: BSD-3-Clause */

#include <stddef.h>
#include <stdint.h>

#include <nrf.h>
#include <nrfkit/board.h>
#include <nrfkit/radio.h>
#include <hal/nrf_radio.h>
#include <nrfx_clock.h>

#define PACKET_COUNT 1000U
#define PACKET_LENGTH 16U
#define WAIT_LIMIT UINT32_C(500000)

static uint8_t packet[PACKET_LENGTH + 1U] __attribute__((aligned(4)));
static uint8_t output[96] __attribute__((aligned(4)));

static void fail(void)
{
    nrfkit_assert_fail();
}

static void uart_write(const uint8_t *data, size_t length)
{
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
    NRFKIT_VCOM_UARTE->DMA.TX.PTR = (uint32_t)(uintptr_t)data;
    NRFKIT_VCOM_UARTE->DMA.TX.MAXCNT = length;
    NRFKIT_VCOM_UARTE->TASKS_DMA.TX.START = UARTE_TASKS_DMA_TX_START_START_Trigger;
    while (NRFKIT_VCOM_UARTE->EVENTS_DMA.TX.END == 0U) {
        __NOP();
    }
}

static size_t append_u32(size_t position, uint32_t value)
{
    uint8_t reversed[10];
    size_t count = 0U;
    do {
        reversed[count++] = (uint8_t)('0' + value % 10U);
        value /= 10U;
    } while (value != 0U);
    while (count != 0U) {
        output[position++] = reversed[--count];
    }
    return position;
}

static void radio_prepare(void)
{
    if (nrfx_clock_init(NULL) != 0) {
        fail();
    }
    nrfx_clock_start(NRF_CLOCK_DOMAIN_HFCLK);
    if (nrfkit_radio_acquire(NRFKIT_RADIO_OWNER_PROPRIETARY) != NRFKIT_RADIO_OK) {
        fail();
    }
    struct nrfkit_radio_1mbit_config const config = {
        .channel = 80U,
        .address_prefix = 0xC7U,
        .maximum_payload = PACKET_LENGTH,
        .whitening_iv = 0x53U,
        .whitening_polynomial = 0x89U,
        .base_address = UINT32_C(0xE7E7E7E7),
        .crc_initial = UINT32_C(0x555555),
        .crc_polynomial = UINT32_C(0x00065B),
    };
    if (nrfkit_radio_configure_1mbit(
            NRFKIT_RADIO_OWNER_PROPRIETARY, &config) != NRFKIT_RADIO_OK) {
        fail();
    }
    nrf_radio_packetptr_set(NRF_RADIO, packet);
    nrf_radio_shorts_set(NRF_RADIO,
        NRF_RADIO_SHORT_READY_START_MASK | NRF_RADIO_SHORT_PHYEND_DISABLE_MASK);
}

static int transfer(nrf_radio_task_t task)
{
    nrf_radio_event_clear(NRF_RADIO, NRF_RADIO_EVENT_END);
    nrf_radio_event_clear(NRF_RADIO, NRF_RADIO_EVENT_DISABLED);
    nrf_radio_task_trigger(NRF_RADIO, task);
    uint32_t timeout = WAIT_LIMIT;
    while (!nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_DISABLED) && timeout-- != 0U) {
        __NOP();
    }
    if (timeout == 0U) {
        nrf_radio_task_trigger(NRF_RADIO, NRF_RADIO_TASK_DISABLE);
        timeout = WAIT_LIMIT;
        while (!nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_DISABLED) && timeout-- != 0U) {
            __NOP();
        }
    }
    return timeout != 0U && nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_END);
}

int main(void)
{
    radio_prepare();
#if defined(NRFKIT_M5_LINK_TX)
    for (volatile uint32_t delay = 0U; delay < 4000000U; ++delay) {
        __NOP();
    }
    packet[0] = PACKET_LENGTH;
    for (uint32_t sequence = 0U; sequence < PACKET_COUNT; ++sequence) {
        packet[1] = (uint8_t)sequence;
        packet[2] = (uint8_t)(sequence >> 8U);
        for (size_t index = 3U; index < sizeof(packet); ++index) {
            packet[index] = (uint8_t)(sequence + index);
        }
        if (!transfer(NRF_RADIO_TASK_TXEN)) {
            fail();
        }
    }
    static uint8_t const pass[] = "NRFKIT_M5_TX PASS\r\n";
    uart_write(pass, sizeof(pass) - 1U);
#elif defined(NRFKIT_M5_LINK_RX)
    uint32_t received = 0U;
    uint32_t crc_errors = 0U;
    uint32_t lost = 0U;
    uint32_t expected = 0U;
    uint32_t attempts = 0U;
    while (received < PACKET_COUNT && attempts++ < PACKET_COUNT * 4U) {
        if (!transfer(NRF_RADIO_TASK_RXEN)) {
            continue;
        }
        if (!nrf_radio_crc_status_check(NRF_RADIO)) {
            ++crc_errors;
            continue;
        }
        uint32_t const sequence = packet[1] | ((uint32_t)packet[2] << 8U);
        if (received != 0U && sequence > expected) {
            lost += sequence - expected;
        }
        expected = sequence + 1U;
        ++received;
    }
    if (received < 10U || crc_errors != 0U) {
        fail();
    }
    static char const prefix[] = "NRFKIT_M5_RX PASS received=";
    size_t position = 0U;
    while (position < sizeof(prefix) - 1U) {
        output[position] = (uint8_t)prefix[position];
        ++position;
    }
    position = append_u32(position, received);
    static char const middle[] = " lost=";
    for (size_t index = 0U; index < sizeof(middle) - 1U; ++index) {
        output[position++] = (uint8_t)middle[index];
    }
    position = append_u32(position, lost);
    static char const suffix[] = " crc=0\r\n";
    for (size_t index = 0U; index < sizeof(suffix) - 1U; ++index) {
        output[position++] = (uint8_t)suffix[index];
    }
    uart_write(output, position);
#else
#error "Select NRFKIT_M5_LINK_TX or NRFKIT_M5_LINK_RX"
#endif
    for (;;) {
        __WFE();
    }
}
