/* SPDX-License-Identifier: BSD-3-Clause */

#include <stdint.h>

#include <zephyr/drivers/clock_control.h>
#include <zephyr/drivers/clock_control/nrf_clock_control.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/onoff.h>
#include <zephyr/sys/printk.h>

#include <hal/nrf_radio.h>

#define PACKET_COUNT 1000U
#define PACKET_LENGTH 16U
#define WAIT_LIMIT UINT32_C(2000000)
#define IDLE_ATTEMPT_LIMIT 4U

static uint8_t packet[PACKET_LENGTH + 1U] __attribute__((aligned(4)));

static int clock_start(void)
{
    struct onoff_manager *manager =
        z_nrf_clock_control_get_onoff(CLOCK_CONTROL_NRF_SUBSYS_HF);
    struct onoff_client client;
    int result = 0;
    if (manager == NULL) {
        return -1;
    }
    sys_notify_init_spinwait(&client.notify);
    if (onoff_request(manager, &client) < 0) {
        return -1;
    }
    int status;
    do {
        status = sys_notify_fetch_result(&client.notify, &result);
    } while (status != 0);
    return result;
}

static void radio_prepare(void)
{
    nrf_radio_packet_conf_t config = {0};
    config.lflen = 8U;
#if defined(CONFIG_NRFKIT_M5_PEER_PHY_1M) && CONFIG_NRFKIT_M5_PEER_PHY_1M
    config.plen = NRF_RADIO_PREAMBLE_LENGTH_8BIT;
#else
    config.plen = NRF_RADIO_PREAMBLE_LENGTH_16BIT;
#endif
    config.maxlen = PACKET_LENGTH;
    config.balen = 3U;
    config.big_endian = false;
    config.whiteen = true;

#if defined(CONFIG_NRFKIT_M7_PEER_PHY_4M) && CONFIG_NRFKIT_M7_PEER_PHY_4M
#if defined(CONFIG_NRFKIT_M7_PEER_4M_BT_0_4) && CONFIG_NRFKIT_M7_PEER_4M_BT_0_4
    nrf_radio_mode_set(NRF_RADIO, NRF_RADIO_MODE_NRF_4MBIT_BT_0_4);
#else
    nrf_radio_mode_set(NRF_RADIO, NRF_RADIO_MODE_NRF_4MBIT_BT_0_6);
#endif
#elif defined(CONFIG_NRFKIT_M5_PEER_PHY_1M) && CONFIG_NRFKIT_M5_PEER_PHY_1M
    nrf_radio_mode_set(NRF_RADIO, NRF_RADIO_MODE_NRF_1MBIT);
#else
    nrf_radio_mode_set(NRF_RADIO, NRF_RADIO_MODE_NRF_2MBIT);
#endif
    nrf_radio_fast_ramp_up_enable_set(NRF_RADIO, true);
    nrf_radio_frequency_set(NRF_RADIO, 2416U);
    nrf_radio_txpower_set(NRF_RADIO, NRF_RADIO_TXPOWER_0DBM);
    nrf_radio_packet_configure(NRF_RADIO, &config);
    nrf_radio_base0_set(NRF_RADIO, UINT32_C(0x76456700));
    nrf_radio_prefix0_set(NRF_RADIO, 0x71U);
    nrf_radio_txaddress_set(NRF_RADIO, 0U);
    nrf_radio_rxaddresses_set(NRF_RADIO, 1U);
    nrf_radio_datawhiteiv_set(NRF_RADIO, 0x53U);
    nrf_radio_datawhite_poly_set(NRF_RADIO, 0x89U);
    nrf_radio_crc_configure(NRF_RADIO, RADIO_CRCCNF_LEN_Three,
        NRF_RADIO_CRC_ADDR_SKIP, UINT32_C(0x00065B));
    nrf_radio_crcinit_set(NRF_RADIO, UINT32_C(0x555555));
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
    while (!nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_DISABLED) && timeout != 0U) {
        --timeout;
        __NOP();
    }
    if (!nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_DISABLED)) {
        nrf_radio_task_trigger(NRF_RADIO, NRF_RADIO_TASK_DISABLE);
        timeout = WAIT_LIMIT;
        while (!nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_DISABLED) && timeout != 0U) {
            --timeout;
            __NOP();
        }
        return 0;
    }
    return nrf_radio_event_check(NRF_RADIO, NRF_RADIO_EVENT_END);
}

int main(void)
{
    if (clock_start() != 0) {
        printk("NRFKIT_M5_PEER FAIL clock\n");
        return 1;
    }
    radio_prepare();
#if defined(CONFIG_NRFKIT_M7_PEER_RETRY_SERVER) && \
    CONFIG_NRFKIT_M7_PEER_RETRY_SERVER
    uint8_t dropped_once[64] = {0};
    uint32_t completed = 0U;
    uint32_t intentional_drops = 0U;
    uint32_t channel_switches = 0U;
    uint32_t invalid = 0U;
    uint32_t attempts = 0U;
    while (completed < 64U && attempts++ < 100000U) {
        if (!transfer(NRF_RADIO_TASK_RXEN)) {
            continue;
        }
        if (!nrf_radio_crc_status_check(NRF_RADIO) ||
            packet[0] != PACKET_LENGTH) {
            ++invalid;
            continue;
        }
        uint8_t const sequence = packet[1];
        if (sequence >= 64U || sequence != completed) {
            ++invalid;
            continue;
        }
        if ((sequence % 8U) == 0U && dropped_once[sequence] == 0U) {
            dropped_once[sequence] = 1U;
            ++intentional_drops;
            continue;
        }
        packet[0] = 2U;
        packet[1] = sequence;
        packet[2] = 0xACU;
        if (!transfer(NRF_RADIO_TASK_TXEN)) {
            printk("NRFKIT_M7_PEER_RETRY FAIL ack\n");
            return 1;
        }
        ++completed;
        if ((completed % 16U) == 0U) {
            uint16_t const frequency =
                ((completed / 16U) & 1U) != 0U ? 2440U : 2416U;
            nrf_radio_frequency_set(NRF_RADIO, frequency);
            ++channel_switches;
        }
    }
    if (completed != 64U || intentional_drops != 8U ||
        channel_switches != 4U || invalid != 0U) {
        printk("NRFKIT_M7_PEER_RETRY FAIL completed=%u drops=%u channels=%u invalid=%u\n",
               completed, intentional_drops, channel_switches, invalid);
        return 1;
    }
    printk("NRFKIT_M7_PEER_RETRY PASS completed=64 drops=8 channels=4 invalid=0\n");
#elif defined(CONFIG_NRFKIT_M5_PEER_TX) && CONFIG_NRFKIT_M5_PEER_TX
    k_sleep(K_SECONDS(1));
    packet[0] = PACKET_LENGTH;
#if (defined(CONFIG_NRFKIT_M7_PEER_BAD_CRC_PREFIX) && \
     CONFIG_NRFKIT_M7_PEER_BAD_CRC_PREFIX) || \
    (defined(CONFIG_NRFKIT_M7_PEER_BAD_WHITENING_PREFIX) && \
     CONFIG_NRFKIT_M7_PEER_BAD_WHITENING_PREFIX)
    for (uint32_t index = 1U; index < sizeof(packet); ++index) {
        packet[index] = (uint8_t)(0xA0U + index);
    }
#if defined(CONFIG_NRFKIT_M7_PEER_BAD_CRC_PREFIX) && \
    CONFIG_NRFKIT_M7_PEER_BAD_CRC_PREFIX
    nrf_radio_crcinit_set(NRF_RADIO, UINT32_C(0xAAAAAA));
#else
    nrf_radio_datawhiteiv_set(NRF_RADIO, 0x35U);
#endif
    for (uint32_t invalid = 0U; invalid < 64U; ++invalid) {
        if (!transfer(NRF_RADIO_TASK_TXEN)) {
            printk("NRFKIT_M7_PEER FAIL negative-prefix\n");
            return 1;
        }
        k_busy_wait(1000U);
    }
    nrf_radio_crcinit_set(NRF_RADIO, UINT32_C(0x555555));
    nrf_radio_datawhiteiv_set(NRF_RADIO, 0x53U);
#endif
    for (uint32_t sequence = 0U; sequence < PACKET_COUNT; ++sequence) {
        packet[1] = (uint8_t)sequence;
        packet[2] = (uint8_t)(sequence >> 8U);
        for (uint32_t index = 3U; index < sizeof(packet); ++index) {
            packet[index] = (uint8_t)(sequence + index);
        }
        if (!transfer(NRF_RADIO_TASK_TXEN)) {
            printk("NRFKIT_M5_PEER FAIL tx\n");
            return 1;
        }
#if defined(CONFIG_NRFKIT_M7_PEER_PACED_TX) && CONFIG_NRFKIT_M7_PEER_PACED_TX
        k_busy_wait(1000U);
#endif
    }
#if defined(CONFIG_NRFKIT_M7_PEER_PHY_4M) && CONFIG_NRFKIT_M7_PEER_PHY_4M
    printk("NRFKIT_M7_PEER_TX PASS\n");
#else
    printk("NRFKIT_M5_PEER_TX PASS\n");
#endif
#elif defined(CONFIG_NRFKIT_M5_PEER_RX) && CONFIG_NRFKIT_M5_PEER_RX
    uint32_t received = 0U;
    uint32_t expected = 0U;
    uint32_t lost = 0U;
    uint32_t invalid = 0U;
    uint32_t attempts = 0U;
    uint32_t idle_attempts = 0U;
    while (received < PACKET_COUNT && attempts++ < PACKET_COUNT * 4U) {
        if (!transfer(NRF_RADIO_TASK_RXEN)) {
            if (received != 0U && ++idle_attempts >= IDLE_ATTEMPT_LIMIT) {
                break;
            }
            continue;
        }
        idle_attempts = 0U;
        if (!nrf_radio_crc_status_check(NRF_RADIO)) {
            continue;
        }
        if (packet[0] != PACKET_LENGTH) {
            ++invalid;
            continue;
        }
        uint32_t const sequence = packet[1] | ((uint32_t)packet[2] << 8U);
        int valid = 1;
        for (uint32_t index = 3U; index < sizeof(packet); ++index) {
            if (packet[index] != (uint8_t)(sequence + index)) {
                valid = 0;
                break;
            }
        }
        if (!valid || (received != 0U && sequence < expected)) {
            ++invalid;
            continue;
        }
        if (received != 0U && sequence > expected) {
            lost += sequence - expected;
        }
        expected = sequence + 1U;
        ++received;
    }
    if (received < 10U || invalid != 0U) {
        printk("NRFKIT_M5_PEER FAIL rx=%u invalid=%u\n", received, invalid);
        return 1;
    }
#if defined(CONFIG_NRFKIT_M7_PEER_PHY_4M) && CONFIG_NRFKIT_M7_PEER_PHY_4M
    printk("NRFKIT_M7_PEER_RX PASS received=%u lost=%u invalid=0\n", received, lost);
#else
    printk("NRFKIT_M5_PEER_RX PASS received=%u lost=%u invalid=0\n", received, lost);
#endif
#else
#error "Select exactly one peer role"
#endif
    for (;;) {
        k_sleep(K_FOREVER);
    }
    return 0;
}
