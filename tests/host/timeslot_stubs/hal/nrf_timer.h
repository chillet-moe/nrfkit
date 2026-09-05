/* SPDX-License-Identifier: BSD-3-Clause */

#include <stdint.h>
#define NRF_TIMER_CC_CHANNEL0 0
#define NRF_TIMER_EVENT_COMPARE0 0
static uint32_t armed_deadline;
static inline int nrf_timer_compare_int_get(int c) { return 1; }
static inline void nrf_timer_int_disable(int p,int m) {}
static inline void nrf_timer_int_enable(int p,int m) {}
static inline void nrf_timer_event_clear(int p,int e) {}
static inline int nrf_timer_event_check(int p,int e) { return 0; }
static inline void nrf_timer_cc_set(int p,int c,uint32_t v) { armed_deadline=v; }
