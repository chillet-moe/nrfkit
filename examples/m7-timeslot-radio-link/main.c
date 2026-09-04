/* SPDX-License-Identifier: BSD-3-Clause */

#include <stddef.h>
#include <stdint.h>

#include <hal/nrf_radio.h>
#include <nrf.h>
#include <nrfkit/board.h>
#include <nrfkit/radio.h>
#include <nrfkit/runtime.h>
#include <nrfkit/sdc.h>
#include <nrfkit/timeslot.h>

#define PACKET_COUNT 1000U
#define PACKET_LENGTH 16U
#define GRANT_LENGTH_US 500U
#define GRANT_DISTANCE_US 2000U
#define CLEANUP_MARGIN_US 120U
#define MAX_ATTEMPTS 4000U
#define RX_IDLE_LIMIT 20U

static uint8_t packet[PACKET_LENGTH + 1U] __attribute__((aligned(4)));
static uint8_t controller_memory[8U * 1024U] __attribute__((aligned(8)));
static uint8_t output[128] __attribute__((aligned(4)));
static volatile uint32_t attempts;
static volatile uint32_t received_packets;
static volatile uint32_t transmitted_packets;
static volatile uint32_t lost_packets;
static volatile uint32_t crc_rejected;
static volatile uint32_t invalid_packets;
static volatile uint32_t deadline_timeouts;
static volatile uint32_t idle_attempts;
static volatile uint32_t expected_sequence;
static volatile uint8_t transfer_complete;
static volatile uint8_t session_idle;
static volatile uint8_t session_closed;

static struct nrfkit_timeslot_action next_grant(void)
{
    struct nrfkit_timeslot_action action = {
        .kind = NRFKIT_TIMESLOT_ACTION_REQUEST_NORMAL,
        .length_us = GRANT_LENGTH_US,
        .distance_us = GRANT_DISTANCE_US,
    };
    return action;
}

static struct nrfkit_timeslot_action end_transfer(void)
{
    transfer_complete = 1U;
    struct nrfkit_timeslot_action action = {
        .kind = NRFKIT_TIMESLOT_ACTION_END,
    };
    return action;
}

static int packet_valid(uint32_t *sequence)
{
    if (packet[0] != PACKET_LENGTH) {
        return 0;
    }
    *sequence = packet[1] | ((uint32_t)packet[2] << 8U);
    for (size_t index = 3U; index < sizeof(packet); ++index) {
        if (packet[index] != (uint8_t)(*sequence + index)) {
            return 0;
        }
    }
    return 1;
}

static struct nrfkit_timeslot_action radio_completed(void)
{
#if defined(NRFKIT_M7_TIMESLOT_LINK_TX)
    ++transmitted_packets;
    if (transmitted_packets >= PACKET_COUNT) {
        return end_transfer();
    }
#else
    idle_attempts = 0U;
    if (!nrf_radio_crc_status_check(NRF_RADIO)) {
        ++crc_rejected;
    } else {
        uint32_t sequence;
        if (!packet_valid(&sequence) ||
            (received_packets != 0U && sequence < expected_sequence)) {
            ++invalid_packets;
        } else {
            if (received_packets != 0U && sequence > expected_sequence) {
                lost_packets += sequence - expected_sequence;
            }
            expected_sequence = sequence + 1U;
            ++received_packets;
        }
    }
    if (received_packets >= PACKET_COUNT || attempts >= MAX_ATTEMPTS) {
        return end_transfer();
    }
#endif
    return next_grant();
}

static struct nrfkit_timeslot_action timeslot_handler(
    enum nrfkit_timeslot_signal signal, void *context)
{
    (void)context;
    if (signal == NRFKIT_TIMESLOT_SIGNAL_START) {
        ++attempts;
#if defined(NRFKIT_M7_TIMESLOT_LINK_TX)
        uint32_t const sequence = transmitted_packets;
        packet[0] = PACKET_LENGTH;
        packet[1] = (uint8_t)sequence;
        packet[2] = (uint8_t)(sequence >> 8U);
        for (size_t index = 3U; index < sizeof(packet); ++index) {
            packet[index] = (uint8_t)(sequence + index);
        }
#endif
        struct nrfkit_radio_packet_config const config = {
            .phy = NRFKIT_RADIO_PHY_4MBIT,
            .mode_4mbit = NRFKIT_RADIO_4MBIT_BT_0_6,
            .channel = 16U,
            .maximum_payload = PACKET_LENGTH,
            .whitening_iv = 0x53U,
            .whitening_polynomial = 0x89U,
            .access_address = UINT32_C(0x71764567),
            .crc_initial = UINT32_C(0x555555),
            .crc_polynomial = UINT32_C(0x00065B),
        };
        if (nrfkit_radio_configure_packet(
                NRFKIT_RADIO_OWNER_TIMESLOT, &config) != NRFKIT_RADIO_OK) {
            return end_transfer();
        }
        nrf_radio_packetptr_set(NRF_RADIO, packet);
        nrf_radio_shorts_set(NRF_RADIO,
            NRF_RADIO_SHORT_READY_START_MASK |
            NRF_RADIO_SHORT_PHYEND_DISABLE_MASK);
        nrf_radio_event_clear(NRF_RADIO, NRF_RADIO_EVENT_END);
        nrf_radio_event_clear(NRF_RADIO, NRF_RADIO_EVENT_DISABLED);
#if defined(NRFKIT_M7_TIMESLOT_LINK_TX)
        nrf_radio_task_trigger(NRF_RADIO, NRF_RADIO_TASK_TXEN);
#else
        nrf_radio_task_trigger(NRF_RADIO, NRF_RADIO_TASK_RXEN);
#endif
        while (!nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_END) &&
               !nrfkit_timeslot_deadline_pending()) {
            __NOP();
        }
        if (nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_END)) {
            nrf_radio_event_clear(NRF_RADIO, NRF_RADIO_EVENT_END);
            return radio_completed();
        }
        ++deadline_timeouts;
#if defined(NRFKIT_M7_TIMESLOT_LINK_RX)
        if (received_packets != 0U && ++idle_attempts >= RX_IDLE_LIMIT) {
            return end_transfer();
        }
#endif
        return attempts >= MAX_ATTEMPTS ? end_transfer() : next_grant();
    }
    if (signal == NRFKIT_TIMESLOT_SIGNAL_RADIO &&
        nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_END)) {
        nrf_radio_event_clear(NRF_RADIO, NRF_RADIO_EVENT_END);
        return radio_completed();
    }
    if (signal == NRFKIT_TIMESLOT_SIGNAL_TIMER) {
        ++deadline_timeouts;
#if defined(NRFKIT_M7_TIMESLOT_LINK_RX)
        if (received_packets != 0U && ++idle_attempts >= RX_IDLE_LIMIT) {
            return end_transfer();
        }
#endif
        return attempts >= MAX_ATTEMPTS ? end_transfer() : next_grant();
    }
    if (signal == NRFKIT_TIMESLOT_SIGNAL_BLOCKED ||
        signal == NRFKIT_TIMESLOT_SIGNAL_CANCELLED) {
        ++deadline_timeouts;
    } else if (signal == NRFKIT_TIMESLOT_SIGNAL_IDLE) {
        session_idle = 1U;
    } else if (signal == NRFKIT_TIMESLOT_SIGNAL_CLOSED) {
        session_closed = 1U;
    }
    return (struct nrfkit_timeslot_action){
        .kind = NRFKIT_TIMESLOT_ACTION_NONE,
    };
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

static void append_text(size_t *position, const char *text)
{
    while (*text != '\0') {
        output[(*position)++] = (uint8_t)*text++;
    }
}

static void uart_write(size_t length)
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
    NRFKIT_VCOM_UARTE->DMA.TX.PTR = (uint32_t)(uintptr_t)output;
    NRFKIT_VCOM_UARTE->DMA.TX.MAXCNT = length;
    NRFKIT_VCOM_UARTE->TASKS_DMA.TX.START = UARTE_TASKS_DMA_TX_START_START_Trigger;
    while (NRFKIT_VCOM_UARTE->EVENTS_DMA.TX.END == 0U) {
        __WFE();
    }
}

int main(void)
{
    struct nrfkit_sdc_config const controller = {
        .lfclk_source = NRFKIT_SDC_LFCLK_XTAL,
        .lfclk_accuracy_ppm = 20U,
        .hfclk_startup_time_us = 1400U,
    };
    size_t required_memory;
    if (nrfkit_sdc_required_memory(&controller, &required_memory) != 0 ||
        required_memory > sizeof(controller_memory) ||
        nrfkit_sdc_enable(&controller, controller_memory,
                          sizeof(controller_memory)) != 0 ||
        nrfkit_timeslot_open(timeslot_handler, NULL) != 0 ||
        nrfkit_timeslot_request_earliest(
            GRANT_LENGTH_US, 100000U, CLEANUP_MARGIN_US) != 0) {
        nrfkit_assert_fail();
    }
    while (transfer_complete == 0U || session_idle == 0U) {
        nrfkit_sdc_process();
        __WFE();
    }
    if (nrfkit_timeslot_close() != 0) {
        nrfkit_assert_fail();
    }
    while (session_closed == 0U) {
        nrfkit_sdc_process();
        __WFE();
    }
    if (nrfkit_sdc_disable() != 0) {
        nrfkit_assert_fail();
    }

    size_t position = 0U;
#if defined(NRFKIT_M7_TIMESLOT_LINK_TX)
    append_text(&position, transmitted_packets == PACKET_COUNT ?
        "NRFKIT_M7_TS_TX PASS sent=" : "NRFKIT_M7_TS_TX FAIL sent=");
    position = append_u32(position, transmitted_packets);
#else
    int const passed = received_packets >= 10U && invalid_packets == 0U;
    append_text(&position, passed ?
        "NRFKIT_M7_TS_RX PASS received=" :
        "NRFKIT_M7_TS_RX FAIL received=");
    position = append_u32(position, received_packets);
    append_text(&position, " lost=");
    position = append_u32(position, lost_packets);
    append_text(&position, " crc=");
    position = append_u32(position, crc_rejected);
    append_text(&position, " invalid=");
    position = append_u32(position, invalid_packets);
#endif
    append_text(&position, " attempts=");
    position = append_u32(position, attempts);
    append_text(&position, " timeouts=");
    position = append_u32(position, deadline_timeouts);
    append_text(&position, "\r\n");
    uart_write(position);
    for (;;) {
        __WFE();
    }
}
