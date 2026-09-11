/* SPDX-License-Identifier: BSD-3-Clause */

#include <stdint.h>
#include <nrf.h>
#include <hal/nrf_radio.h>
#include <nrfkit/radio.h>
#include <nrfkit/runtime.h>
#include <nrfx_clock.h>
#include <nrfx_grtc.h>

#define PACKET_LENGTH 16U
#define INTERVAL_US UINT64_C(10000)

volatile uint32_t nrfkit_power_stage;
volatile uint32_t nrfkit_power_packets;
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
    uint64_t next = nrfx_grtc_syscounter_get();
    nrfkit_power_stage = 1U;
    for (;;) {
        next += INTERVAL_US;
        require(next > nrfx_grtc_syscounter_get(), 107U);
        wake_pending = 0U;
        require(nrfx_grtc_syscounter_cc_absolute_set(&wake, next, true) == 0, 108U);
        while (wake_pending == 0U) {
            __WFE();
        }
        nrfx_clock_start(NRF_CLOCK_DOMAIN_HFCLK);
        packet[1] = (uint8_t)nrfkit_power_packets;
        packet[2] = (uint8_t)(nrfkit_power_packets >> 8U);
        for (uint32_t index = 3U; index < sizeof(packet); ++index) {
            packet[index] = (uint8_t)(nrfkit_power_packets + index);
        }
        nrf_radio_event_clear(NRF_RADIO, NRF_RADIO_EVENT_END);
        nrf_radio_event_clear(NRF_RADIO, NRF_RADIO_EVENT_DISABLED);
        nrf_radio_task_trigger(NRF_RADIO, NRF_RADIO_TASK_TXEN);
        /* This profile includes CPU polling during TX, but sleeps between packets. */
        uint32_t remaining = 200000U;
        while (!nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_DISABLED) &&
               remaining != 0U) {
            --remaining;
        }
        require(nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_DISABLED) &&
                nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_END), 109U);
        nrfx_clock_stop(NRF_CLOCK_DOMAIN_HFCLK);
        ++nrfkit_power_packets;
    }
}
