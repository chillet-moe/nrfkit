/* SPDX-License-Identifier: BSD-3-Clause */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include <hal/nrf_radio.h>
#include <hal/nrf_timer.h>
#include <mpsl_hwres.h>
#include <mpsl_timeslot.h>
#include <nrf_errno.h>
#include <nrfkit/radio.h>
#include <nrfkit/timeslot.h>

#include <nrfkit/internal/sdc_platform_internal.h>

#define DEADLINE_CC NRF_TIMER_CC_CHANNEL0
#define MINIMUM_CLEANUP_MARGIN_US UINT32_C(100)

static mpsl_timeslot_signal_return_param_t signal_return;
static mpsl_timeslot_request_t next_request;
static mpsl_timeslot_session_id_t session_id;
static nrfkit_timeslot_handler_t application_handler;
static void *application_context;
static uint32_t grant_length_us;
static uint32_t cleanup_margin_us;
static uint32_t pending_extension_us;
static volatile uint8_t session_open;
static volatile uint8_t session_idle;
static volatile uint8_t session_closing;
static volatile uint8_t grant_active;

static mpsl_timeslot_signal_return_param_t *return_none(void)
{
    signal_return.callback_action = MPSL_TIMESLOT_SIGNAL_ACTION_NONE;
    return &signal_return;
}

static void cleanup_grant(void)
{
    if (grant_active == 0U) {
        return;
    }
    nrf_timer_int_disable(MPSL_TIMER0, nrf_timer_compare_int_get(DEADLINE_CC));
    nrf_timer_event_clear(MPSL_TIMER0, NRF_TIMER_EVENT_COMPARE0);
    nrf_radio_int_disable(NRF_RADIO, UINT32_MAX);
    nrf_radio_shorts_set(NRF_RADIO, 0U);
    if (nrf_radio_state_get(NRF_RADIO) != NRF_RADIO_STATE_DISABLED) {
        nrf_radio_task_trigger(NRF_RADIO, NRF_RADIO_TASK_DISABLE);
        for (uint32_t remaining = 1024U;
             remaining != 0U &&
                 nrf_radio_state_get(NRF_RADIO) != NRF_RADIO_STATE_DISABLED;
             --remaining) {
            __NOP();
        }
    }
    (void)nrfkit_radio_release(NRFKIT_RADIO_OWNER_TIMESLOT);
    grant_active = 0U;
}

static enum nrfkit_timeslot_signal translate_signal(uint32_t signal)
{
    switch (signal) {
    case MPSL_TIMESLOT_SIGNAL_START:
        return NRFKIT_TIMESLOT_SIGNAL_START;
    case MPSL_TIMESLOT_SIGNAL_TIMER0:
        return NRFKIT_TIMESLOT_SIGNAL_TIMER;
    case MPSL_TIMESLOT_SIGNAL_RADIO:
        return NRFKIT_TIMESLOT_SIGNAL_RADIO;
    case MPSL_TIMESLOT_SIGNAL_EXTEND_SUCCEEDED:
        return NRFKIT_TIMESLOT_SIGNAL_EXTEND_SUCCEEDED;
    case MPSL_TIMESLOT_SIGNAL_EXTEND_FAILED:
        return NRFKIT_TIMESLOT_SIGNAL_EXTEND_FAILED;
    case MPSL_TIMESLOT_SIGNAL_BLOCKED:
        return NRFKIT_TIMESLOT_SIGNAL_BLOCKED;
    case MPSL_TIMESLOT_SIGNAL_CANCELLED:
        return NRFKIT_TIMESLOT_SIGNAL_CANCELLED;
    case MPSL_TIMESLOT_SIGNAL_SESSION_IDLE:
        return NRFKIT_TIMESLOT_SIGNAL_IDLE;
    case MPSL_TIMESLOT_SIGNAL_INVALID_RETURN:
        return NRFKIT_TIMESLOT_SIGNAL_INVALID_RETURN;
    case MPSL_TIMESLOT_SIGNAL_SESSION_CLOSED:
        return NRFKIT_TIMESLOT_SIGNAL_CLOSED;
    default:
        return NRFKIT_TIMESLOT_SIGNAL_OVERSTAYED;
    }
}

static bool valid_length(uint32_t length_us)
{
    return length_us >= MPSL_TIMESLOT_LENGTH_MIN_US &&
        length_us <= MPSL_TIMESLOT_LENGTH_MAX_US;
}

static void arm_deadline(void)
{
    nrf_timer_event_clear(MPSL_TIMER0, NRF_TIMER_EVENT_COMPARE0);
    nrf_timer_cc_set(MPSL_TIMER0, DEADLINE_CC,
                     grant_length_us - cleanup_margin_us);
    nrf_timer_int_enable(MPSL_TIMER0, nrf_timer_compare_int_get(DEADLINE_CC));
}

static mpsl_timeslot_signal_return_param_t *end_grant(void)
{
    cleanup_grant();
    signal_return.callback_action = MPSL_TIMESLOT_SIGNAL_ACTION_END;
    return &signal_return;
}

static mpsl_timeslot_signal_return_param_t *handle_action(
    struct nrfkit_timeslot_action action)
{
    if (session_closing != 0U || action.kind == NRFKIT_TIMESLOT_ACTION_END) {
        return end_grant();
    }
    if (action.kind == NRFKIT_TIMESLOT_ACTION_NONE) {
        return return_none();
    }
    if (action.kind == NRFKIT_TIMESLOT_ACTION_EXTEND &&
        action.length_us >= MPSL_TIMESLOT_EXTENSION_TIME_MIN_US) {
        pending_extension_us = action.length_us;
        signal_return.callback_action = MPSL_TIMESLOT_SIGNAL_ACTION_EXTEND;
        signal_return.params.extend.length_us = action.length_us;
        return &signal_return;
    }
    if (action.kind == NRFKIT_TIMESLOT_ACTION_REQUEST_NORMAL &&
        valid_length(action.length_us) &&
        action.distance_us <= MPSL_TIMESLOT_DISTANCE_MAX_US &&
        cleanup_margin_us < action.length_us) {
        cleanup_grant();
        next_request.request_type = MPSL_TIMESLOT_REQ_TYPE_NORMAL;
        next_request.params.normal.hfclk =
            MPSL_TIMESLOT_HFCLK_CFG_XTAL_GUARANTEED;
        next_request.params.normal.priority = MPSL_TIMESLOT_PRIORITY_NORMAL;
        next_request.params.normal.distance_us = action.distance_us;
        next_request.params.normal.length_us = action.length_us;
        grant_length_us = action.length_us;
        signal_return.callback_action = MPSL_TIMESLOT_SIGNAL_ACTION_REQUEST;
        signal_return.params.request.p_next = &next_request;
        return &signal_return;
    }
    return end_grant();
}

static mpsl_timeslot_signal_return_param_t *timeslot_callback(
    mpsl_timeslot_session_id_t callback_session_id, uint32_t signal)
{
    if (callback_session_id != session_id) {
        return return_none();
    }
    if (signal == MPSL_TIMESLOT_SIGNAL_SESSION_CLOSED) {
        cleanup_grant();
        session_open = 0U;
        session_idle = 0U;
        session_closing = 0U;
        if (application_handler != NULL) {
            (void)application_handler(NRFKIT_TIMESLOT_SIGNAL_CLOSED,
                                      application_context);
        }
        application_handler = NULL;
        application_context = NULL;
        nrfkit_mpsl_timeslot_release();
        return return_none();
    }
    /* MPSL permits a new request after a blocked/cancelled request as well as
     * after SESSION_IDLE (mpsl/doc/timeslot.rst, blocked/canceled scenarios).
     */
    if (signal == MPSL_TIMESLOT_SIGNAL_SESSION_IDLE ||
        signal == MPSL_TIMESLOT_SIGNAL_BLOCKED ||
        signal == MPSL_TIMESLOT_SIGNAL_CANCELLED) {
        session_idle = 1U;
    }
    if (signal == MPSL_TIMESLOT_SIGNAL_START) {
        if (nrfkit_radio_acquire(NRFKIT_RADIO_OWNER_TIMESLOT) != NRFKIT_RADIO_OK) {
            return end_grant();
        }
        grant_active = 1U;
        arm_deadline();
    } else if (signal == MPSL_TIMESLOT_SIGNAL_TIMER0 &&
               nrf_timer_event_check(MPSL_TIMER0, NRF_TIMER_EVENT_COMPARE0)) {
        nrf_timer_event_clear(MPSL_TIMER0, NRF_TIMER_EVENT_COMPARE0);
        struct nrfkit_timeslot_action const action = application_handler(
            NRFKIT_TIMESLOT_SIGNAL_TIMER, application_context);
        if (action.kind == NRFKIT_TIMESLOT_ACTION_NONE) {
            return end_grant();
        }
        return handle_action(action);
    } else if (signal == MPSL_TIMESLOT_SIGNAL_EXTEND_SUCCEEDED) {
        grant_length_us += pending_extension_us;
        pending_extension_us = 0U;
        arm_deadline();
    } else if (signal == MPSL_TIMESLOT_SIGNAL_EXTEND_FAILED ||
               signal == MPSL_TIMESLOT_SIGNAL_OVERSTAYED ||
               signal == MPSL_TIMESLOT_SIGNAL_INVALID_RETURN) {
        cleanup_grant();
    }

    struct nrfkit_timeslot_action const action =
        application_handler(translate_signal(signal), application_context);
    if (signal == MPSL_TIMESLOT_SIGNAL_BLOCKED ||
        signal == MPSL_TIMESLOT_SIGNAL_CANCELLED ||
        signal == MPSL_TIMESLOT_SIGNAL_SESSION_IDLE ||
        signal == MPSL_TIMESLOT_SIGNAL_OVERSTAYED ||
        signal == MPSL_TIMESLOT_SIGNAL_INVALID_RETURN) {
        return return_none();
    }
    if (signal == MPSL_TIMESLOT_SIGNAL_EXTEND_FAILED) {
        return end_grant();
    }
    return handle_action(action);
}

int32_t nrfkit_timeslot_open(nrfkit_timeslot_handler_t handler, void *context)
{
    if (handler == NULL || session_open != 0U ||
        !nrfkit_mpsl_is_initialized()) {
        return -NRF_EPERM;
    }
    int32_t result = nrfkit_mpsl_timeslot_retain();
    if (result != 0) {
        return result;
    }
    result = mpsl_timeslot_session_open(timeslot_callback, &session_id);
    if (result != 0) {
        nrfkit_mpsl_timeslot_release();
        return result;
    }
    application_handler = handler;
    application_context = context;
    session_open = 1U;
    session_idle = 1U;
    return 0;
}

int32_t nrfkit_timeslot_request_earliest(uint32_t length_us,
                                         uint32_t timeout_us,
                                         uint32_t requested_cleanup_margin_us)
{
    if (session_open == 0U || session_closing != 0U ||
        !valid_length(length_us) ||
        requested_cleanup_margin_us < MINIMUM_CLEANUP_MARGIN_US ||
        requested_cleanup_margin_us < MPSL_TIMESLOT_EXTENSION_MARGIN_MIN_US ||
        requested_cleanup_margin_us >= length_us ||
        timeout_us > MPSL_TIMESLOT_EARLIEST_TIMEOUT_MAX_US) {
        return -NRF_EINVAL;
    }
    /* A pending grant owns these parameters until idle, blocked, or cancelled.
     * In particular,
     * an EAGAIN from a second request must not move the first grant's deadline.
     * Calls are serialized in the same context as mpsl_low_priority_process().
     */
    if (session_idle == 0U) {
        return -NRF_EAGAIN;
    }
    uint32_t const previous_length_us = grant_length_us;
    uint32_t const previous_margin_us = cleanup_margin_us;
    mpsl_timeslot_request_t const previous_request = next_request;
    session_idle = 0U;
    /* START may interrupt the vendor call, so publish the parameters first. */
    grant_length_us = length_us;
    cleanup_margin_us = requested_cleanup_margin_us;
    next_request.request_type = MPSL_TIMESLOT_REQ_TYPE_EARLIEST;
    next_request.params.earliest.hfclk =
        MPSL_TIMESLOT_HFCLK_CFG_XTAL_GUARANTEED;
    next_request.params.earliest.priority = MPSL_TIMESLOT_PRIORITY_NORMAL;
    next_request.params.earliest.length_us = length_us;
    next_request.params.earliest.timeout_us = timeout_us;
    int32_t const result = mpsl_timeslot_request(session_id, &next_request);
    if (result != 0) {
        grant_length_us = previous_length_us;
        cleanup_margin_us = previous_margin_us;
        next_request = previous_request;
        session_idle = 1U;
    }
    return result;
}

int32_t nrfkit_timeslot_close(void)
{
    if (session_open == 0U || session_closing != 0U) {
        return -NRF_EAGAIN;
    }
    session_closing = 1U;
    int32_t const result = mpsl_timeslot_session_close(session_id);
    if (result != 0) {
        session_closing = 0U;
    }
    return result;
}

bool nrfkit_timeslot_is_open(void)
{
    return session_open != 0U;
}

bool nrfkit_timeslot_is_granted(void)
{
    return grant_active != 0U;
}

bool nrfkit_timeslot_deadline_pending(void)
{
    return grant_active != 0U &&
        nrf_timer_event_check(MPSL_TIMER0, NRF_TIMER_EVENT_COMPARE0);
}
