/* SPDX-License-Identifier: BSD-3-Clause */
static uint32_t fake_time;
#define NRF_GRTC 0
static inline uint64_t nrfy_grtc_sys_counter_get(int p) {return fake_time;}
