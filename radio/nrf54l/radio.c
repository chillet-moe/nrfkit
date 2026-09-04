/* SPDX-License-Identifier: BSD-3-Clause */

#include <nrfkit/radio.h>

#include <nrf.h>
#include <hal/nrf_radio.h>

static int validate_owner(enum nrfkit_radio_owner owner)
{
    if (owner != NRFKIT_RADIO_OWNER_PROPRIETARY && owner != NRFKIT_RADIO_OWNER_BLE) {
        return NRFKIT_RADIO_ERR_ARGUMENT;
    }
    if (nrfkit_radio_owner_get() != owner) {
        return NRFKIT_RADIO_ERR_OWNER;
    }
    if (nrf_radio_state_get(NRF_RADIO) != NRF_RADIO_STATE_DISABLED) {
        return NRFKIT_RADIO_ERR_ACTIVE;
    }
    return NRFKIT_RADIO_OK;
}

int nrfkit_radio_configure_packet(
    enum nrfkit_radio_owner owner,
    const struct nrfkit_radio_packet_config *config)
{
    if (config == NULL ||
        (config->phy != NRFKIT_RADIO_PHY_1MBIT &&
         config->phy != NRFKIT_RADIO_PHY_2MBIT &&
         config->phy != NRFKIT_RADIO_PHY_4MBIT) ||
        config->mode_4mbit > NRFKIT_RADIO_4MBIT_BT_0_4 ||
        config->channel > 100U || config->maximum_payload == 0U ||
        config->whitening_iv > 0x1FFU || config->whitening_polynomial > 0x3FFU ||
        config->crc_initial > 0xFFFFFFU || config->crc_polynomial > 0xFFFFFFU) {
        return NRFKIT_RADIO_ERR_ARGUMENT;
    }
    int const owner_result = validate_owner(owner);
    if (owner_result != NRFKIT_RADIO_OK) {
        return owner_result;
    }

    nrf_radio_mode_t mode = NRF_RADIO_MODE_NRF_1MBIT;
    nrf_radio_preamble_length_t preamble = NRF_RADIO_PREAMBLE_LENGTH_8BIT;
    if (config->phy == NRFKIT_RADIO_PHY_2MBIT) {
        mode = NRF_RADIO_MODE_NRF_2MBIT;
        preamble = NRF_RADIO_PREAMBLE_LENGTH_16BIT;
    } else if (config->phy == NRFKIT_RADIO_PHY_4MBIT) {
        mode = config->mode_4mbit == NRFKIT_RADIO_4MBIT_BT_0_4 ?
            NRF_RADIO_MODE_NRF_4MBIT_BT_0_4 : NRF_RADIO_MODE_NRF_4MBIT_BT_0_6;
        preamble = NRF_RADIO_PREAMBLE_LENGTH_16BIT;
    }

    nrf_radio_packet_conf_t packet = {0};
    packet.lflen = 8U;
    packet.plen = preamble;
    packet.maxlen = config->maximum_payload;
    packet.balen = 3U;
    packet.big_endian = false;
    packet.whiteen = true;

    nrf_radio_mode_set(NRF_RADIO, mode);
    nrf_radio_fast_ramp_up_enable_set(NRF_RADIO, true);
    nrf_radio_frequency_set(NRF_RADIO, (uint16_t)(2400U + config->channel));
    nrf_radio_txpower_set(NRF_RADIO, NRF_RADIO_TXPOWER_0DBM);
    nrf_radio_packet_configure(NRF_RADIO, &packet);
    nrf_radio_base0_set(NRF_RADIO, (config->access_address & UINT32_C(0x00FFFFFF)) << 8U);
    nrf_radio_prefix0_set(NRF_RADIO, (uint8_t)(config->access_address >> 24U));
    nrf_radio_txaddress_set(NRF_RADIO, 0U);
    nrf_radio_rxaddresses_set(NRF_RADIO, 1U);
    nrf_radio_datawhiteiv_set(NRF_RADIO, config->whitening_iv);
    nrf_radio_datawhite_poly_set(NRF_RADIO, config->whitening_polynomial);
    nrf_radio_crc_configure(NRF_RADIO, RADIO_CRCCNF_LEN_Three,
        NRF_RADIO_CRC_ADDR_SKIP, config->crc_polynomial);
    nrf_radio_crcinit_set(NRF_RADIO, config->crc_initial);
    return NRFKIT_RADIO_OK;
}

int nrfkit_radio_configure_1mbit(
    enum nrfkit_radio_owner owner,
    const struct nrfkit_radio_1mbit_config *config)
{
    if (config == NULL ||
        config->channel > 100U ||
        config->maximum_payload == 0U || config->whitening_iv > 0x1FFU ||
        config->whitening_polynomial > 0x3FFU || config->crc_initial > 0xFFFFFFU ||
        config->crc_polynomial > 0xFFFFFFU) {
        return NRFKIT_RADIO_ERR_ARGUMENT;
    }
    int const owner_result = validate_owner(owner);
    if (owner_result != NRFKIT_RADIO_OK) {
        return owner_result;
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
