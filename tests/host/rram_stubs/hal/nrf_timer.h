/* SPDX-License-Identifier: BSD-3-Clause */
#define NRF_TIMER_TASK_CAPTURE1 1
#define NRF_TIMER_CC_CHANNEL1 1
static inline void nrf_timer_task_trigger(int p,int task) {}
static inline uint32_t nrf_timer_cc_get(int p,int cc) {return 0;}
