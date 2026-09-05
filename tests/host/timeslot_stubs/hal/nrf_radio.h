/* SPDX-License-Identifier: BSD-3-Clause */

#include <stdint.h>
#define NRF_RADIO 0
#define NRF_RADIO_STATE_DISABLED 0
#define NRF_RADIO_TASK_DISABLE 0
static inline void __NOP(void) {}
static inline void nrf_radio_int_disable(int p, uint32_t m) {}
static inline void nrf_radio_shorts_set(int p, uint32_t m) {}
static inline int nrf_radio_state_get(int p) { return 0; }
static inline void nrf_radio_task_trigger(int p,int t) {}
