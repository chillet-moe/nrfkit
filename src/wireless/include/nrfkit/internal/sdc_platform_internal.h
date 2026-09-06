/* SPDX-License-Identifier: BSD-3-Clause */

#ifndef NRFKIT_SDC_PLATFORM_INTERNAL_H
#define NRFKIT_SDC_PLATFORM_INTERNAL_H

#include <stdbool.h>
#include <stdint.h>

bool nrfkit_mpsl_is_initialized(void);
int32_t nrfkit_mpsl_timeslot_retain(void);
void nrfkit_mpsl_timeslot_release(void);
int32_t nrfkit_mpsl_hfclk24m_request(void);
int32_t nrfkit_mpsl_hfclk24m_is_running(bool *running);
int32_t nrfkit_mpsl_hfclk24m_release(void);

#endif
