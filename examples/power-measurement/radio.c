/* SPDX-License-Identifier: BSD-3-Clause */

#include <stdint.h>
#include <nrf.h>
#include <hal/nrf_radio.h>
#include <hal/nrf_power.h>
#include <nrfkit/radio.h>
#include <nrfkit/runtime.h>
#include <nrfx_clock.h>
#include <nrfx_grtc.h>

#define PACKET_LENGTH 16U
#ifndef NRFKIT_POWER_BATCH_PACKETS
#define NRFKIT_POWER_BATCH_PACKETS 1U
#endif
#ifndef NRFKIT_POWER_BATCH_COUNT
#define NRFKIT_POWER_BATCH_COUNT 1000U
#endif
#ifndef NRFKIT_POWER_INTERVAL_US
#define NRFKIT_POWER_INTERVAL_US 10000U
#endif

volatile uint32_t nrfkit_power_stage;
volatile uint32_t nrfkit_power_packets;
volatile uint32_t nrfkit_power_batches;
volatile uint32_t nrfkit_power_active_us;
volatile uint32_t nrfkit_power_active_min_us = UINT32_MAX;
volatile uint32_t nrfkit_power_active_max_us;
volatile uint32_t nrfkit_power_first_us;
volatile uint32_t nrfkit_power_last_us;
volatile uint32_t nrfkit_power_elapsed_us;
static volatile uint32_t wake_pending;
static uint8_t packet[PACKET_LENGTH + 1U] __attribute__((aligned(4)));

static void require(int condition, uint32_t stage)
{
    if (!condition) {
        nrfkit_power_stage = stage;
        nrfkit_assert_fail();
    }
}

static void wake_handler(int32_t event, uint64_t compare_value, void *context)
{
    (void)event;
    (void)compare_value;
    (void)context;
    wake_pending = 1U;
    /* Preserve a wakeup even when this IRQ runs just before main's WFE. */
    __SEV();
}

int main(void)
{
    require(nrfx_clock_init(NULL) == 0, 101U);
    nrfx_clock_start(NRF_CLOCK_DOMAIN_LFCLK);
    require(nrfx_grtc_init(NRFX_GRTC_DEFAULT_CONFIG_IRQ_PRIORITY) == 0, 102U);
    uint8_t main_channel;
    require(nrfx_grtc_syscounter_start(true, &main_channel) == 0, 103U);
    uint8_t wake_channel;
    require(nrfx_grtc_channel_alloc(&wake_channel) == 0, 104U);
    nrfx_grtc_channel_t wake = {.handler = wake_handler, .channel = wake_channel};

    require(nrfkit_radio_acquire(NRFKIT_RADIO_OWNER_PROPRIETARY) == 0, 105U);
    struct nrfkit_radio_packet_config const config = {
        .phy = NRFKIT_POWER_PHY,
        .mode_4mbit = NRFKIT_RADIO_4MBIT_BT_0_6,
        .channel = 16U,
        .maximum_payload = PACKET_LENGTH,
        .whitening_iv = 0x53U,
        .whitening_polynomial = 0x89U,
        .access_address = UINT32_C(0x71764567),
        .crc_initial = UINT32_C(0x555555),
        .crc_polynomial = UINT32_C(0x00065B),
    };
    nrfx_clock_start(NRF_CLOCK_DOMAIN_HFCLK);
    require(nrfkit_radio_configure_packet(NRFKIT_RADIO_OWNER_PROPRIETARY, &config) == 0,
            106U);
    nrf_radio_packetptr_set(NRF_RADIO, packet);
    nrf_radio_shorts_set(NRF_RADIO,
        NRF_RADIO_SHORT_READY_START_MASK | NRF_RADIO_SHORT_PHYEND_DISABLE_MASK);
    nrfx_clock_stop(NRF_CLOCK_DOMAIN_HFCLK);
    packet[0] = PACKET_LENGTH;
    uint64_t next = nrfx_grtc_syscounter_get() + UINT64_C(2000000);
    nrfkit_power_stage = 1U;
    for (uint32_t batch = 0; batch < NRFKIT_POWER_BATCH_COUNT; ++batch) {
        next += NRFKIT_POWER_INTERVAL_US;
        require(next > nrfx_grtc_syscounter_get(), 107U);
        wake_pending = 0U;
        require(nrfx_grtc_syscounter_cc_absolute_set(&wake, next, true) == 0, 108U);
        while (wake_pending == 0U) {
            __WFE();
        }
        uint32_t active_start = (uint32_t)nrfx_grtc_syscounter_get();
        if (batch == 0U) {
            nrfkit_power_first_us = active_start;
        }
        /* LM20 anomaly 20 requires constant latency during RADIO TX/RX. */
        nrf_power_task_trigger(NRF_POWER, NRF_POWER_TASK_CONSTLAT);
        uint32_t latency_wait = 200000U;
        while ((NRF_POWER->CONSTLATSTAT & POWER_CONSTLATSTAT_STATUS_Msk) !=
               POWER_CONSTLATSTAT_STATUS_Enable && latency_wait != 0U) {
            --latency_wait;
        }
        require(latency_wait != 0U, 110U);
        nrfx_clock_start(NRF_CLOCK_DOMAIN_HFCLK);
        for (uint32_t index_in_batch = 0; index_in_batch < NRFKIT_POWER_BATCH_PACKETS;
             ++index_in_batch) {
            packet[1] = (uint8_t)nrfkit_power_packets;
            packet[2] = (uint8_t)(nrfkit_power_packets >> 8U);
            for (uint32_t index = 3U; index < sizeof(packet); ++index) {
                packet[index] = (uint8_t)(nrfkit_power_packets + index);
            }
            nrf_radio_event_clear(NRF_RADIO, NRF_RADIO_EVENT_END);
            nrf_radio_event_clear(NRF_RADIO, NRF_RADIO_EVENT_DISABLED);
            nrf_radio_task_trigger(NRF_RADIO, NRF_RADIO_TASK_TXEN);
            /* CPU polling during TX is included; sleep occurs between batches. */
            uint32_t remaining = 200000U;
            while (!nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_DISABLED) &&
                   remaining != 0U) {
                --remaining;
            }
            require(nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_DISABLED) &&
                    nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_END), 109U);
            ++nrfkit_power_packets;
        }
        nrfx_clock_stop(NRF_CLOCK_DOMAIN_HFCLK);
        nrf_power_task_trigger(NRF_POWER, NRF_POWER_TASK_LOWPWR);
        uint32_t active_end = (uint32_t)nrfx_grtc_syscounter_get();
        uint32_t duration = active_end - active_start;
        nrfkit_power_active_us += duration;
        if (duration < nrfkit_power_active_min_us) {
            nrfkit_power_active_min_us = duration;
        }
        if (duration > nrfkit_power_active_max_us) {
            nrfkit_power_active_max_us = duration;
        }
        nrfkit_power_last_us = active_end;
        ++nrfkit_power_batches;
    }
    nrfkit_power_elapsed_us = nrfkit_power_last_us - nrfkit_power_first_us;
    nrfkit_power_stage = 2U;
    for (;;) {
        __WFE();
    }
}
