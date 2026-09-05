/* SPDX-License-Identifier: BSD-3-Clause */

#ifndef NRFKIT_TIMESLOT_H
#define NRFKIT_TIMESLOT_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum nrfkit_timeslot_signal {
    NRFKIT_TIMESLOT_SIGNAL_START = 0,
    NRFKIT_TIMESLOT_SIGNAL_TIMER = 1,
    NRFKIT_TIMESLOT_SIGNAL_RADIO = 2,
    NRFKIT_TIMESLOT_SIGNAL_EXTEND_SUCCEEDED = 3,
    NRFKIT_TIMESLOT_SIGNAL_EXTEND_FAILED = 4,
    NRFKIT_TIMESLOT_SIGNAL_BLOCKED = 5,
    NRFKIT_TIMESLOT_SIGNAL_CANCELLED = 6,
    NRFKIT_TIMESLOT_SIGNAL_IDLE = 7,
    NRFKIT_TIMESLOT_SIGNAL_INVALID_RETURN = 8,
    NRFKIT_TIMESLOT_SIGNAL_CLOSED = 9,
    NRFKIT_TIMESLOT_SIGNAL_OVERSTAYED = 10,
};

enum nrfkit_timeslot_action_kind {
    NRFKIT_TIMESLOT_ACTION_NONE = 0,
    NRFKIT_TIMESLOT_ACTION_END = 1,
    NRFKIT_TIMESLOT_ACTION_EXTEND = 2,
    NRFKIT_TIMESLOT_ACTION_REQUEST_NORMAL = 3,
};

struct nrfkit_timeslot_action {
    enum nrfkit_timeslot_action_kind kind;
    /* EXTEND: extension length. REQUEST_NORMAL: next grant length. */
    uint32_t length_us;
    /* REQUEST_NORMAL: distance from the start of the current grant. */
    uint32_t distance_us;
};

typedef struct nrfkit_timeslot_action (*nrfkit_timeslot_handler_t)(
    enum nrfkit_timeslot_signal signal, void *context);

/**
 * Open the single SDK Timeslot session on an already initialized MPSL.
 *
 * The handler runs in MPSL interrupt context for START/TIMER/RADIO/extension
 * signals and in deferred main context for scheduler signals. RADIO access is
 * permitted only between START and the corresponding cleanup/end signal.
 */
int32_t nrfkit_timeslot_open(nrfkit_timeslot_handler_t handler, void *context);

/**
 * Request the first or next idle grant with an accurate crystal HFCLK.
 * Serialize calls with nrfkit_sdc_process(); pending/active requests return
 * -NRF_EAGAIN without changing the existing grant. Retry after IDLE, BLOCKED,
 * or CANCELLED.
 */
int32_t nrfkit_timeslot_request_earliest(uint32_t length_us,
                                         uint32_t timeout_us,
                                         uint32_t cleanup_margin_us);

/** Begin asynchronous close. CLOSED is the final handler notification. */
int32_t nrfkit_timeslot_close(void);

bool nrfkit_timeslot_is_open(void);
bool nrfkit_timeslot_is_granted(void);
/** True once the backend cleanup deadline has elapsed inside a grant. */
bool nrfkit_timeslot_deadline_pending(void);

#ifdef __cplusplus
}
#endif

#endif
