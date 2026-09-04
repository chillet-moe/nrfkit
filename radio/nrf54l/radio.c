/* SPDX-License-Identifier: BSD-3-Clause */

#include <nrfkit/radio.h>

#include <nrf.h>
#include <hal/nrf_radio.h>

int nrfkit_radio_configure_1mbit(
    enum nrfkit_radio_owner owner,
    const struct nrfkit_radio_1mbit_config *config)
{
    if (config == NULL ||
        (owner != NRFKIT_RADIO_OWNER_PROPRIETARY && owner != NRFKIT_RADIO_OWNER_BLE) ||
        config->channel > 100U ||
        config->maximum_payload == 0U || config->whitening_iv > 0x1FFU ||
        config->whitening_polynomial > 0x3FFU || config->crc_initial > 0xFFFFFFU ||
        config->crc_polynomial > 0xFFFFFFU) {
        return NRFKIT_RADIO_ERR_ARGUMENT;
    }
    if (nrfkit_radio_owner_get() != owner) {
        return NRFKIT_RADIO_ERR_OWNER;
    }
    if (nrf_radio_state_get(NRF_RADIO) != NRF_RADIO_STATE_DISABLED) {
        return NRFKIT_RADIO_ERR_ACTIVE;
    }

    nrf_radio_packet_conf_t packet = {0};
    packet.lflen = 8U;
    packet.plen = NRF_RADIO_PREAMBLE_LENGTH_8BIT;
    packet.maxlen = config->maximum_payload;
    packet.balen = 4U;
    packet.big_endian = false;
    packet.whiteen = true;

    nrf_radio_mode_set(NRF_RADIO, NRF_RADIO_MODE_NRF_1MBIT);
    nrf_radio_fast_ramp_up_enable_set(NRF_RADIO, true);
    nrf_radio_frequency_set(NRF_RADIO, (uint16_t)(2400U + config->channel));
    nrf_radio_txpower_set(NRF_RADIO, NRF_RADIO_TXPOWER_NEG40DBM);
    nrf_radio_packet_configure(NRF_RADIO, &packet);
    nrf_radio_base0_set(NRF_RADIO, config->base_address);
    nrf_radio_prefix0_set(NRF_RADIO, config->address_prefix);
    nrf_radio_txaddress_set(NRF_RADIO, 0U);
    nrf_radio_rxaddresses_set(NRF_RADIO, 1U);
    nrf_radio_datawhiteiv_set(NRF_RADIO, config->whitening_iv);
    nrf_radio_datawhite_poly_set(NRF_RADIO, config->whitening_polynomial);
    nrf_radio_crc_configure(NRF_RADIO, RADIO_CRCCNF_LEN_Three,
        NRF_RADIO_CRC_ADDR_SKIP, config->crc_polynomial);
    nrf_radio_crcinit_set(NRF_RADIO, config->crc_initial);
    return NRFKIT_RADIO_OK;
}
