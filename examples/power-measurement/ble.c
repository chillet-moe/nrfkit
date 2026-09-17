/* SPDX-License-Identifier: BSD-3-Clause */

#include <stddef.h>
#include <stdint.h>

#include <hal/nrf_radio.h>
#include <nrf.h>
#include <nrfkit/radio.h>
#include <nrfkit/runtime.h>
#include <nrfkit/sdc.h>
#if defined(NRFKIT_POWER_TIMESLOT)
#include <nrfkit/timeslot.h>
#endif

#define CONTROLLER_MEMORY_SIZE (8U * 1024U)

static uint8_t controller_memory[CONTROLLER_MEMORY_SIZE]
    __attribute__((aligned(8)));
volatile uint32_t nrfkit_power_stage;
volatile uint32_t nrfkit_power_ble_events;
volatile uint32_t nrfkit_power_timeslot_grants;
volatile uint32_t nrfkit_power_timeslot_packets;

static void require(int condition, uint32_t stage)
{
    if (!condition) {
        nrfkit_power_stage = stage;
        nrfkit_assert_fail();
    }
}

static void hci_command(const uint8_t *command, size_t size, uint32_t stage)
{
    uint8_t event[40];
    size_t event_size = 0U;
    require(nrfkit_sdc_hci_command(command, size, event, sizeof(event),
                                   &event_size) == 0,
            stage);
    require(event_size >= 6U && event[0] == 0x0EU && event[5] == 0U, stage);
}

static void drain_controller(void)
{
    uint8_t packet[260];
    uint8_t message_type;
    while (nrfkit_sdc_hci_get(packet, &message_type) == 0) {
        ++nrfkit_power_ble_events;
    }
}

#if defined(NRFKIT_POWER_TIMESLOT)
static volatile uint8_t timeslot_remaining;
static volatile uint8_t timeslot_idle;
static uint8_t timeslot_packet[17] __attribute__((aligned(4)));

static struct nrfkit_timeslot_action timeslot_handler(
    enum nrfkit_timeslot_signal signal, void *context)
{
    (void)context;
    struct nrfkit_timeslot_action action = {
        .kind = NRFKIT_TIMESLOT_ACTION_NONE,
    };
    if (signal == NRFKIT_TIMESLOT_SIGNAL_START) {
        ++nrfkit_power_timeslot_grants;
        uint32_t const sequence = nrfkit_power_timeslot_packets;
        struct nrfkit_radio_packet_config const config = {
            .phy = NRFKIT_RADIO_PHY_4MBIT,
            .mode_4mbit = NRFKIT_RADIO_4MBIT_BT_0_6,
            .channel = 16U,
            .maximum_payload = 16U,
            .whitening_iv = 0x53U,
            .whitening_polynomial = 0x89U,
            .access_address = UINT32_C(0x71764567),
            .crc_initial = UINT32_C(0x555555),
            .crc_polynomial = UINT32_C(0x00065B),
        };
        timeslot_packet[0] = 16U;
        timeslot_packet[1] = (uint8_t)sequence;
        timeslot_packet[2] = (uint8_t)(sequence >> 8U);
        for (size_t index = 3U; index < sizeof(timeslot_packet); ++index) {
            timeslot_packet[index] = (uint8_t)(sequence + index);
        }
        if (nrfkit_radio_configure_packet(NRFKIT_RADIO_OWNER_TIMESLOT,
                                          &config) == NRFKIT_RADIO_OK) {
            nrf_radio_packetptr_set(NRF_RADIO, timeslot_packet);
            nrf_radio_shorts_set(NRF_RADIO,
                                 NRF_RADIO_SHORT_READY_START_MASK |
                                     NRF_RADIO_SHORT_PHYEND_DISABLE_MASK);
            nrf_radio_event_clear(NRF_RADIO, NRF_RADIO_EVENT_END);
            nrf_radio_task_trigger(NRF_RADIO, NRF_RADIO_TASK_TXEN);
            while (!nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_END) &&
                   !nrfkit_timeslot_deadline_pending()) {
                __NOP();
            }
            if (nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_END)) {
                ++nrfkit_power_timeslot_packets;
            }
        }
    } else if (signal == NRFKIT_TIMESLOT_SIGNAL_TIMER) {
        if (timeslot_remaining > 1U) {
            --timeslot_remaining;
            action.kind = NRFKIT_TIMESLOT_ACTION_REQUEST_NORMAL;
            action.length_us = 1000U;
            action.distance_us = 10000U;
        } else {
            timeslot_remaining = 0U;
            action.kind = NRFKIT_TIMESLOT_ACTION_END;
        }
    } else if (signal == NRFKIT_TIMESLOT_SIGNAL_IDLE ||
               signal == NRFKIT_TIMESLOT_SIGNAL_BLOCKED ||
               signal == NRFKIT_TIMESLOT_SIGNAL_CANCELLED) {
        timeslot_idle = 1U;
    }
    return action;
}
#endif

int main(void)
{
    struct nrfkit_sdc_config const controller = {
        .lfclk_source = NRFKIT_SDC_LFCLK_XTAL,
        .lfclk_accuracy_ppm = 20U,
        .hfclk_startup_time_us = 1400U,
    };
    size_t required_memory;
    require(nrfkit_sdc_required_memory(&controller, &required_memory) == 0 &&
                required_memory <= sizeof(controller_memory) &&
                nrfkit_sdc_enable(&controller, controller_memory,
                                  sizeof(controller_memory)) == 0,
            101U);

    static uint8_t const reset[] = {0x03U, 0x0CU, 0U};
    static uint8_t const random_address[] = {
        0x05U, 0x20U, 6U, 0x02U, 0U, 0U, 0U, 0U, 0xC0U,
    };
    static uint8_t const advertising_parameters[] = {
        0x06U, 0x20U, 15U,
        0xA0U, 0U, 0xA0U, 0U, 0U, 1U, 0U,
        0U, 0U, 0U, 0U, 0U, 0U, 7U, 0U,
    };
    static uint8_t const advertising_enable[] = {0x0AU, 0x20U, 1U, 1U};
    hci_command(reset, sizeof(reset), 102U);
    hci_command(random_address, sizeof(random_address), 103U);
    hci_command(advertising_parameters, sizeof(advertising_parameters), 104U);
    hci_command(advertising_enable, sizeof(advertising_enable), 105U);
    nrfkit_power_stage = 1U;

#if defined(NRFKIT_POWER_TIMESLOT)
    require(nrfkit_timeslot_open(timeslot_handler, NULL) == 0, 106U);
    timeslot_remaining = 8U;
    timeslot_idle = 0U;
    require(nrfkit_timeslot_request_earliest(1000U, 100000U, 150U) == 0,
            107U);
#endif
    for (;;) {
        nrfkit_sdc_process();
        drain_controller();
#if defined(NRFKIT_POWER_TIMESLOT)
        if (timeslot_remaining == 0U && timeslot_idle != 0U) {
            nrfkit_power_stage = 2U;
        }
#endif
        __WFE();
    }
}
