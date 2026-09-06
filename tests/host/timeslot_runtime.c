/* SPDX-License-Identifier: BSD-3-Clause */

#include <assert.h>

/* Exercise the real backend with only the peripheral and MPSL calls replaced. */
#include <timeslot/nrf54l/timeslot.c>

static mpsl_timeslot_callback_t callback;
static int request_result;
static unsigned request_calls;
static bool start_during_request;

bool nrfkit_mpsl_is_initialized(void) { return true; }
int32_t nrfkit_mpsl_timeslot_retain(void) { return 0; }
void nrfkit_mpsl_timeslot_release(void) {}
int nrfkit_radio_acquire(enum nrfkit_radio_owner owner) { return 0; }
int nrfkit_radio_release(enum nrfkit_radio_owner owner) { return 0; }

int32_t mpsl_timeslot_session_count_set(void *memory, uint8_t count) { return 0; }
int32_t mpsl_timeslot_session_open(mpsl_timeslot_callback_t handler,
                                   mpsl_timeslot_session_id_t *id)
{
    callback = handler;
    *id = 0;
    return 0;
}
int32_t mpsl_timeslot_session_close(mpsl_timeslot_session_id_t id) { return 0; }
int32_t mpsl_timeslot_request(mpsl_timeslot_session_id_t id,
                              mpsl_timeslot_request_t const *request)
{
    ++request_calls;
    if (start_during_request) {
        callback(id, MPSL_TIMESLOT_SIGNAL_START);
    }
    return request_result;
}

static struct nrfkit_timeslot_action handler(enum nrfkit_timeslot_signal signal,
                                             void *context)
{
    return (struct nrfkit_timeslot_action){NRFKIT_TIMESLOT_ACTION_NONE, 0, 0};
}

int main(void)
{
    assert(nrfkit_timeslot_open(handler, NULL) == 0);
    assert(nrfkit_timeslot_request_earliest(1000, 100000, 200) == 0);
    request_result = -NRF_EAGAIN;
    assert(nrfkit_timeslot_request_earliest(10000, 100000, 300) == -NRF_EAGAIN);
    callback(0, MPSL_TIMESLOT_SIGNAL_START);
    assert(armed_deadline == 800);
    assert(request_calls == 1);

    /* Requests during the active grant must not change extension accounting. */
    assert(nrfkit_timeslot_request_earliest(20000, 100000, 400) == -NRF_EAGAIN);
    pending_extension_us = 500;
    callback(0, MPSL_TIMESLOT_SIGNAL_EXTEND_SUCCEEDED);
    assert(armed_deadline == 1300);
    end_grant();
    callback(0, MPSL_TIMESLOT_SIGNAL_SESSION_IDLE);

    request_result = -NRF_EINVAL;
    assert(nrfkit_timeslot_request_earliest(3000, 100000, 200) == -NRF_EINVAL);
    request_result = 0;
    start_during_request = true;
    assert(nrfkit_timeslot_request_earliest(2000, 100000, 300) == 0);
    assert(armed_deadline == 1700);
    assert(nrfkit_timeslot_close() == 0);
    callback(0, MPSL_TIMESLOT_SIGNAL_SESSION_CLOSED);
    assert(nrfkit_timeslot_open(handler, NULL) == 0);
    assert(nrfkit_timeslot_request_earliest(1000, 100000, 200) == 0);
    assert(armed_deadline == 800);
    end_grant();
    callback(0, MPSL_TIMESLOT_SIGNAL_SESSION_IDLE);
    start_during_request = false;
    assert(nrfkit_timeslot_request_earliest(1000, 100000, 200) == 0);
    callback(0, MPSL_TIMESLOT_SIGNAL_BLOCKED);
    assert(nrfkit_timeslot_request_earliest(1000, 100000, 200) == 0);
    callback(0, MPSL_TIMESLOT_SIGNAL_CANCELLED);
    assert(nrfkit_timeslot_request_earliest(1000, 100000, 200) == 0);
    return 0;
}
