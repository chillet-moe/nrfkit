/* SPDX-License-Identifier: BSD-3-Clause */

#include <nrfkit/radio.h>

#include <stdbool.h>

#include <nrf.h>

static volatile enum nrfkit_radio_owner radio_owner;

static uint32_t critical_enter(void)
{
    uint32_t const primask = __get_PRIMASK();
    __disable_irq();
    __DMB();
    return primask;
}

static void critical_exit(uint32_t primask)
{
    __DMB();
    if (primask == 0U) {
        __enable_irq();
    }
}

static bool valid_owner(enum nrfkit_radio_owner owner)
{
    return owner == NRFKIT_RADIO_OWNER_PROPRIETARY ||
        owner == NRFKIT_RADIO_OWNER_BLE ||
        owner == NRFKIT_RADIO_OWNER_TIMESLOT;
}

int nrfkit_radio_acquire(enum nrfkit_radio_owner owner)
{
    if (!valid_owner(owner)) {
        return NRFKIT_RADIO_ERR_ARGUMENT;
    }
    uint32_t const primask = critical_enter();
    int result = NRFKIT_RADIO_OK;
    if (radio_owner != NRFKIT_RADIO_OWNER_NONE) {
        result = NRFKIT_RADIO_ERR_BUSY;
    } else {
        radio_owner = owner;
    }
    critical_exit(primask);
    return result;
}

int nrfkit_radio_release(enum nrfkit_radio_owner owner)
{
    if (!valid_owner(owner)) {
        return NRFKIT_RADIO_ERR_ARGUMENT;
    }
    uint32_t const primask = critical_enter();
    int result = NRFKIT_RADIO_OK;
    if (radio_owner != owner) {
        result = NRFKIT_RADIO_ERR_OWNER;
    } else if (NRF_RADIO->STATE != RADIO_STATE_STATE_Disabled) {
        result = NRFKIT_RADIO_ERR_ACTIVE;
    } else {
        radio_owner = NRFKIT_RADIO_OWNER_NONE;
    }
    critical_exit(primask);
    return result;
}

enum nrfkit_radio_owner nrfkit_radio_owner_get(void)
{
    return radio_owner;
}
