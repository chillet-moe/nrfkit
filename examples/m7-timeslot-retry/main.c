/* SPDX-License-Identifier: BSD-3-Clause */

#include <stddef.h>
#include <stdint.h>

#include <hal/nrf_radio.h>
#include <hal/nrf_grtc.h>
#include <nrf.h>
#include <nrfkit/board.h>
#include <nrfkit/radio.h>
#include <nrfkit/runtime.h>
#include <nrfkit/sdc.h>
#include <nrfkit/timeslot.h>

#define TOTAL_PACKETS 64U
#define QUEUE_CAPACITY 8U
#define MAX_RETRIES 3U
#define INTENTIONAL_RETRIES (TOTAL_PACKETS / 8U)
#define PACKET_LENGTH 16U
#define GRANT_LENGTH_US 3000U
#define CLEANUP_MARGIN_US 200U

static uint8_t controller_memory[8U * 1024U] __attribute__((aligned(8)));
static uint8_t packet[PACKET_LENGTH + 1U] __attribute__((aligned(4)));
static uint8_t queue[QUEUE_CAPACITY];
static uint8_t queue_head;
static uint8_t queue_count;
static uint8_t next_sequence;
static uint8_t current_attempt;
static uint8_t current_channel = 16U;
static volatile uint32_t accepted;
static volatile uint32_t completed;
static volatile uint32_t retries;
static volatile uint32_t dropped;
static volatile uint32_t channel_switches;
static volatile uint32_t grants;
static volatile uint32_t sleeps;
static volatile uint8_t queue_peak;
static volatile uint8_t transfer_complete;
static volatile uint8_t session_idle;
static volatile uint8_t session_closed;

static struct nrfkit_timeslot_action action(enum nrfkit_timeslot_action_kind kind)
{
    return (struct nrfkit_timeslot_action){
        .kind = kind,
        .length_us = GRANT_LENGTH_US,
        .distance_us = 5000U,
    };
}

static void fill_queue(void)
{
    while (queue_count < QUEUE_CAPACITY && next_sequence < TOTAL_PACKETS) {
        queue[(queue_head + queue_count) % QUEUE_CAPACITY] = next_sequence++;
        ++queue_count;
        ++accepted;
        if (queue_count > queue_peak) {
            queue_peak = queue_count;
        }
    }
}

static int configure_radio(void)
{
    struct nrfkit_radio_packet_config const config = {
        .phy = NRFKIT_RADIO_PHY_4MBIT,
        .mode_4mbit = NRFKIT_RADIO_4MBIT_BT_0_6,
        .channel = current_channel,
        .maximum_payload = PACKET_LENGTH,
        .whitening_iv = 0x53U,
        .whitening_polynomial = 0x89U,
        .access_address = UINT32_C(0x71764567),
        .crc_initial = UINT32_C(0x555555),
        .crc_polynomial = UINT32_C(0x00065B),
    };
    return nrfkit_radio_configure_packet(
        NRFKIT_RADIO_OWNER_TIMESLOT, &config);
}

static int transfer(nrf_radio_task_t task)
{
    nrf_radio_event_clear(NRF_RADIO, NRF_RADIO_EVENT_END);
    nrf_radio_event_clear(NRF_RADIO, NRF_RADIO_EVENT_DISABLED);
    nrf_radio_task_trigger(NRF_RADIO, task);
    while (!nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_END) &&
           !nrfkit_timeslot_deadline_pending()) {
        __NOP();
    }
    while (nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_END) &&
           nrf_radio_state_get(NRF_RADIO) != NRF_RADIO_STATE_DISABLED &&
           !nrfkit_timeslot_deadline_pending()) {
        __NOP();
    }
    return nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_END) &&
        nrf_radio_state_get(NRF_RADIO) == NRF_RADIO_STATE_DISABLED;
}

static struct nrfkit_timeslot_action timeslot_handler(
    enum nrfkit_timeslot_signal signal, void *context)
{
    (void)context;
    if (signal == NRFKIT_TIMESLOT_SIGNAL_START) {
        ++grants;
        if (queue_count == 0U || configure_radio() != NRFKIT_RADIO_OK) {
            transfer_complete = 1U;
            return action(NRFKIT_TIMESLOT_ACTION_END);
        }
        uint8_t const sequence = queue[queue_head];
        packet[0] = PACKET_LENGTH;
        packet[1] = sequence;
        packet[2] = current_attempt;
        for (size_t index = 3U; index < sizeof(packet); ++index) {
            packet[index] = (uint8_t)(sequence + index);
        }
        nrf_radio_packetptr_set(NRF_RADIO, packet);
        nrf_radio_shorts_set(NRF_RADIO,
            NRF_RADIO_SHORT_READY_START_MASK |
            NRF_RADIO_SHORT_PHYEND_DISABLE_MASK);
        if (!transfer(NRF_RADIO_TASK_TXEN)) {
            transfer_complete = 1U;
            return action(NRFKIT_TIMESLOT_ACTION_END);
        }
        packet[0] = 0U;
        if (!transfer(NRF_RADIO_TASK_RXEN) ||
            !nrf_radio_crc_status_check(NRF_RADIO) || packet[0] != 2U ||
            packet[1] != sequence || packet[2] != 0xACU) {
            if (++current_attempt > MAX_RETRIES) {
                ++dropped;
                transfer_complete = 1U;
                return action(NRFKIT_TIMESLOT_ACTION_END);
            }
            ++retries;
            return action(NRFKIT_TIMESLOT_ACTION_REQUEST_NORMAL);
        }

        current_attempt = 0U;
        queue_head = (uint8_t)((queue_head + 1U) % QUEUE_CAPACITY);
        --queue_count;
        ++completed;
        if ((completed % 16U) == 0U) {
            current_channel = current_channel == 16U ? 40U : 16U;
            ++channel_switches;
        }
        fill_queue();
        if (completed == TOTAL_PACKETS) {
            transfer_complete = 1U;
            return action(NRFKIT_TIMESLOT_ACTION_END);
        }
        return action(NRFKIT_TIMESLOT_ACTION_REQUEST_NORMAL);
    }
    if (signal == NRFKIT_TIMESLOT_SIGNAL_TIMER) {
        transfer_complete = 1U;
        return action(NRFKIT_TIMESLOT_ACTION_END);
    }
    if (signal == NRFKIT_TIMESLOT_SIGNAL_IDLE) {
        session_idle = 1U;
    } else if (signal == NRFKIT_TIMESLOT_SIGNAL_CLOSED) {
        session_closed = 1U;
    }
    return action(NRFKIT_TIMESLOT_ACTION_NONE);
}

static size_t append_u32(uint8_t *output, size_t position, uint32_t value)
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

static void append_text(uint8_t *output, size_t *position, const char *text)
{
    while (*text != '\0') {
        output[(*position)++] = (uint8_t)*text++;
    }
}

int main(void)
{
    fill_queue();
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
    uint64_t const transfer_start_ticks = nrf_grtc_sys_counter_get(NRF_GRTC);
    while (transfer_complete == 0U || session_idle == 0U) {
        nrfkit_sdc_process();
        ++sleeps;
        __WFE();
    }
    uint64_t const transfer_ticks =
        nrf_grtc_sys_counter_get(NRF_GRTC) - transfer_start_ticks;
    if (nrfkit_timeslot_close() != 0) {
        nrfkit_assert_fail();
    }
    while (session_closed == 0U) {
        nrfkit_sdc_process();
        ++sleeps;
        __WFE();
    }
    if (nrfkit_sdc_disable() != 0) {
        nrfkit_assert_fail();
    }

    int const passed = accepted == TOTAL_PACKETS && completed == TOTAL_PACKETS &&
        dropped == 0U && retries >= INTENTIONAL_RETRIES &&
        retries <= TOTAL_PACKETS * MAX_RETRIES && queue_peak == QUEUE_CAPACITY &&
        channel_switches == 4U && sleeps != 0U;
    uint8_t output[192] __attribute__((aligned(4)));
    size_t position = 0U;
    append_text(output, &position,
        passed ? "NRFKIT_M7_RETRY PASS accepted=" :
                 "NRFKIT_M7_RETRY FAIL accepted=");
#define APPEND_COUNTER(label, value) \
    do { append_text(output, &position, label); \
         position = append_u32(output, position, value); } while (0)
    position = append_u32(output, position, accepted);
    APPEND_COUNTER(" completed=", completed);
    APPEND_COUNTER(" retries=", retries);
    APPEND_COUNTER(" dropped=", dropped);
    APPEND_COUNTER(" peak=", queue_peak);
    APPEND_COUNTER(" channels=", channel_switches);
    APPEND_COUNTER(" grants=", grants);
    APPEND_COUNTER(" sleeps=", sleeps);
    APPEND_COUNTER(" ticks=", (uint32_t)transfer_ticks);
    append_text(output, &position, "\r\n");
#undef APPEND_COUNTER
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
    NRFKIT_VCOM_UARTE->DMA.TX.MAXCNT = position;
    NRFKIT_VCOM_UARTE->TASKS_DMA.TX.START = UARTE_TASKS_DMA_TX_START_START_Trigger;
    while (NRFKIT_VCOM_UARTE->EVENTS_DMA.TX.END == 0U) {
        __WFE();
    }
    for (;;) {
        __WFE();
    }
}
