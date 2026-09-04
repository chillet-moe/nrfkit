/* SPDX-License-Identifier: BSD-3-Clause */

#ifndef NRFKIT_RADIO_H
#define NRFKIT_RADIO_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum nrfkit_radio_owner {
    NRFKIT_RADIO_OWNER_NONE = 0,
    NRFKIT_RADIO_OWNER_PROPRIETARY = 1,
    NRFKIT_RADIO_OWNER_BLE = 2,
};

enum nrfkit_radio_result {
    NRFKIT_RADIO_OK = 0,
    NRFKIT_RADIO_ERR_ARGUMENT = -1,
    NRFKIT_RADIO_ERR_BUSY = -2,
    NRFKIT_RADIO_ERR_OWNER = -3,
    NRFKIT_RADIO_ERR_ACTIVE = -4,
};

enum nrfkit_radio_phy {
    NRFKIT_RADIO_PHY_1MBIT = 1,
    NRFKIT_RADIO_PHY_2MBIT = 2,
    NRFKIT_RADIO_PHY_4MBIT = 4,
};

struct nrfkit_radio_packet_config {
    enum nrfkit_radio_phy phy;
    /* Datasheet FREQUENCY offset: carrier is 2400 MHz + channel. */
    uint8_t channel;
    uint8_t maximum_payload;
    uint16_t whitening_iv;
    uint16_t whitening_polynomial;
    uint32_t access_address;
    uint32_t crc_initial;
    uint32_t crc_polynomial;
};

struct nrfkit_radio_1mbit_config {
    /* Datasheet FREQUENCY offset: carrier is 2400 MHz + channel. */
    uint8_t channel;
    uint8_t address_prefix;
    uint8_t maximum_payload;
    uint16_t whitening_iv;
    uint16_t whitening_polynomial;
    uint32_t base_address;
    uint32_t crc_initial;
    uint32_t crc_polynomial;
};

/* Cooperative ownership: callers must stop their stack before release. */
int nrfkit_radio_acquire(enum nrfkit_radio_owner owner);
int nrfkit_radio_release(enum nrfkit_radio_owner owner);
enum nrfkit_radio_owner nrfkit_radio_owner_get(void);

/* Configure a Nordic proprietary packet PHY; an accurate HF clock is required. */
int nrfkit_radio_configure_packet(
    enum nrfkit_radio_owner owner,
    const struct nrfkit_radio_packet_config *config);

/* Compatibility entry point for the original five-byte-address 1 Mbit API. */
int nrfkit_radio_configure_1mbit(
    enum nrfkit_radio_owner owner,
    const struct nrfkit_radio_1mbit_config *config);

#ifdef __cplusplus
}
#endif

#endif
