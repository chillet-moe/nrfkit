/* SPDX-License-Identifier: BSD-3-Clause */

#include <string.h>
#include <hal/nrf_rramc.h>
#include <hal/nrf_timer.h>
#include <haly/nrfy_grtc.h>
#include <mpsl_hwres.h>
#include <mpsl_timeslot.h>
#include <nrf_errno.h>
#include <nrfkit/rram.h>
#include <nrfkit/runtime.h>
#include <nrfkit/internal/sdc_platform_internal.h>

/* NCS v3.4.0 soc_flash_nrf_rram.c uses 500 us for a single buffer line;
 * flash_sync_mpsl.c adds 100 us slack. One 128-bit unit per grant keeps the
 * bounded operation short and never consumes another client's TIMER state.
 */
#define SLOT_US 600U
#define TIMEOUT_US 2000000U
static uint32_t buffer[NRFKIT_RRAM_MAX_WRITE / 4U];
static uint32_t destination;
static volatile size_t remaining;
static size_t offset;
static uint32_t started;
static volatile int32_t result;
static volatile int32_t operation_result;
static volatile uint8_t opened;
static volatile uint8_t idle;
static volatile uint8_t closing;
static volatile uint8_t retry;
static mpsl_timeslot_session_id_t session;
static mpsl_timeslot_signal_return_param_t response;
static mpsl_timeslot_request_t request;

static uint32_t elapsed_us(void)
{
    nrf_timer_task_trigger(MPSL_TIMER0, NRF_TIMER_TASK_CAPTURE1);
    return nrf_timer_cc_get(MPSL_TIMER0, NRF_TIMER_CC_CHANNEL1);
}

static void wait_ready(void)
{
    while (!nrf_rramc_write_ready_check(NRF_RRAMC) ||
           !nrf_rramc_empty_buffer_check(NRF_RRAMC)) {
        /* An unresponsive controller cannot safely be handed back to MPSL.
         * Reset before the grant expires rather than return with a live write.
         */
        if (elapsed_us() >= 450U) {
            nrfkit_system_reset();
        }
    }
}

static int32_t write_unit(void)
{
    if (!nrf_rramc_write_ready_check(NRF_RRAMC) ||
        !nrf_rramc_empty_buffer_check(NRF_RRAMC)) {
        return -NRF_EAGAIN;
    }
    uint32_t saved_config = NRF_RRAMC->CONFIG;
    uint32_t saved_power = NRF_RRAMC->POWER.CONFIG;
    uint32_t saved_timeout = NRF_RRAMC->READYNEXTTIMEOUT;
    nrf_rramc_config_t config = {.mode_write = true, .write_buff_size = 1U};
    nrf_rramc_power_t power = {.access_timeout = 0x100U, .abort_on_pof = true};
    nrf_rramc_ready_next_timeout_t timeout = {.value = 0x80U, .enable = true};
    nrf_rramc_power_config_set(NRF_RRAMC, &power);
    nrf_rramc_ready_next_timeout_set(NRF_RRAMC, &timeout);
    nrf_rramc_config_set(NRF_RRAMC, &config);
    wait_ready();
    volatile uint32_t *target = (volatile uint32_t *)(uintptr_t)(destination + offset);
    for (size_t i = 0; i < 4U; ++i) {
        target[i] = buffer[offset / 4U + i];
    }
    __DSB();
    nrf_rramc_task_trigger(NRF_RRAMC, NRF_RRAMC_TASK_COMMIT_WRITEBUF);
    wait_ready();
    int32_t status = 0;
    for (size_t i = 0; i < 4U; ++i) {
        if (target[i] != buffer[offset / 4U + i]) {
            status = -NRF_EIO;
        }
    }
    NRF_RRAMC->CONFIG = saved_config;
    NRF_RRAMC->READYNEXTTIMEOUT = saved_timeout;
    NRF_RRAMC->POWER.CONFIG = saved_power;
    __DSB();
    return status;
}

static mpsl_timeslot_signal_return_param_t *callback(
    mpsl_timeslot_session_id_t id, uint32_t signal)
{
    response.callback_action = MPSL_TIMESLOT_SIGNAL_ACTION_NONE;
    if (id != session) {
        return &response;
    }
    switch (signal) {
    case MPSL_TIMESLOT_SIGNAL_START:
        if (operation_result == 0 && remaining != 0U) {
            operation_result = write_unit();
            if (operation_result == 0) {
                offset += 16U;
                remaining -= 16U;
                retry = 0U;
            }
        }
        response.callback_action = MPSL_TIMESLOT_SIGNAL_ACTION_END;
        break;
    case MPSL_TIMESLOT_SIGNAL_BLOCKED:
    case MPSL_TIMESLOT_SIGNAL_CANCELLED:
        retry = 1U;
        idle = 1U;
        break;
    case MPSL_TIMESLOT_SIGNAL_SESSION_IDLE:
        idle = 1U;
        break;
    case MPSL_TIMESLOT_SIGNAL_SESSION_CLOSED:
        opened = 0U;
        closing = 0U;
        nrfkit_mpsl_timeslot_release();
        result = operation_result;
        break;
    default:
        operation_result = -NRF_EIO;
        break;
    }
    return &response;
}

int32_t nrfkit_rram_submit(const struct nrfkit_rram_region *region,
                          uint32_t address, const void *data, size_t size)
{
    if (region == NULL || data == NULL || size == 0U ||
        size > sizeof(buffer) || (address % 16U) != 0U || (size % 16U) != 0U ||
        region->origin >= 0x001FD000U || region->length == 0U ||
        region->length > 0x001FD000U - region->origin ||
        address < region->origin || address - region->origin > region->length ||
        size > region->length - (address - region->origin)) {
        return -NRF_EINVAL;
    }
    if (result == -NRF_EINPROGRESS || opened) {
        return -NRF_EAGAIN;
    }
    if (!nrfkit_mpsl_is_initialized()) {
        return -NRF_EPERM;
    }
    int32_t status = nrfkit_mpsl_timeslot_retain();
    if (status != 0) {
        return status;
    }
    memcpy(buffer, data, size);
    destination = address;
    remaining = size;
    offset = 0;
    operation_result = 0;
    idle = 1U;
    closing = 0U;
    retry = 0U;
    status = mpsl_timeslot_session_open(callback, &session);
    if (status != 0) {
        nrfkit_mpsl_timeslot_release();
        return status;
    }
    /* Read the running 1 MHz counter without reserving a compare channel.
     * DWT is not an exclusive application clock while wireless is active.
     */
    started = (uint32_t)nrfy_grtc_sys_counter_get(NRF_GRTC);
    opened = 1U;
    result = -NRF_EINPROGRESS;
    return 0;
}

void nrfkit_rram_process(void)
{
    if (!opened || closing) {
        return;
    }
    if ((uint32_t)((uint32_t)nrfy_grtc_sys_counter_get(NRF_GRTC) - started) >= TIMEOUT_US) {
        operation_result = -NRF_ETIMEDOUT;
    }
    if (operation_result != 0 || remaining == 0U) {
        closing = 1U;
        int32_t status = mpsl_timeslot_session_close(session);
        if (status != 0) {
            closing = 0U;
            operation_result = status;
        }
    } else if (idle) {
        request.request_type = MPSL_TIMESLOT_REQ_TYPE_EARLIEST;
        request.params.earliest.hfclk = MPSL_TIMESLOT_HFCLK_CFG_XTAL_GUARANTEED;
        request.params.earliest.priority = retry ? MPSL_TIMESLOT_PRIORITY_HIGH
                                                 : MPSL_TIMESLOT_PRIORITY_NORMAL;
        request.params.earliest.length_us = SLOT_US;
        request.params.earliest.timeout_us = 100000U;
        idle = 0U;
        int32_t status = mpsl_timeslot_request(session, &request);
        if (status != 0) {
            operation_result = status;
            idle = 1U;
        }
    }
}

int32_t nrfkit_rram_result(void) { return result; }
