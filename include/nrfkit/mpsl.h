/* SPDX-License-Identifier: BSD-3-Clause */

#ifndef NRFKIT_MPSL_H
#define NRFKIT_MPSL_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Request HFCLK24M through the MPSL clock arbiter.
 *
 * Link an SDC variant and initialize it before requesting the clock. Call these
 * functions from serialized main context, as with the SDC lifecycle API. Only
 * one outstanding request is supported; a duplicate or uninitialized request
 * returns -NRF_EPERM. Success retains MPSL until a successful release, even if
 * the Controller is disabled in the meantime. Hardware readiness is asynchronous.
 */
int32_t nrfkit_mpsl_hfclk24m_request(void);

/** Query readiness after a successful request; running must not be NULL. */
int32_t nrfkit_mpsl_hfclk24m_is_running(bool *running);

/**
 * Release the outstanding request after the peripheral no longer needs it.
 * On failure ownership remains held. Continue pumping nrfkit_sdc_process() so
 * MPSL can complete deferred teardown after the final client releases it.
 */
int32_t nrfkit_mpsl_hfclk24m_release(void);

#ifdef __cplusplus
}
#endif

#endif
