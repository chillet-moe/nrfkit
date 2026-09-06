/* SPDX-License-Identifier: BSD-3-Clause */
/* Both services run inside the explicitly selected Controller/MPSL context. */
#if !defined(NRFKIT_SDC_ENABLED) || !NRFKIT_SDC_ENABLED
#error "NrfKit Timeslot/RRAM requires an explicit SDC variant target"
#endif
