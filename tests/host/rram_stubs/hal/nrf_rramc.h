/* SPDX-License-Identifier: BSD-3-Clause */
#include <stdbool.h>
#include <stdint.h>
struct fake_rram { uint32_t CONFIG, READYNEXTTIMEOUT; struct {uint32_t CONFIG;} POWER; };
static struct fake_rram fake_rram;
#define NRF_RRAMC (&fake_rram)
#define __DSB() ((void)0)
typedef struct {bool mode_write; uint32_t write_buff_size;} nrf_rramc_config_t;
typedef struct {uint32_t access_timeout; bool abort_on_pof;} nrf_rramc_power_t;
typedef struct {uint32_t value; bool enable;} nrf_rramc_ready_next_timeout_t;
static bool hardware_ready = true;
static unsigned commits;
static bool corrupt_write;
#define NRF_RRAMC_TASK_COMMIT_WRITEBUF 1
static inline bool nrf_rramc_write_ready_check(const struct fake_rram *p) {return hardware_ready;}
static inline bool nrf_rramc_empty_buffer_check(const struct fake_rram *p) {return true;}
static inline void nrf_rramc_config_set(struct fake_rram *p,const nrf_rramc_config_t *c) {p->CONFIG=c->write_buff_size;}
static inline void nrf_rramc_power_config_set(struct fake_rram *p,const nrf_rramc_power_t *c) {p->POWER.CONFIG=1;}
static inline void nrf_rramc_ready_next_timeout_set(struct fake_rram *p,const nrf_rramc_ready_next_timeout_t *c) {p->READYNEXTTIMEOUT=1;}
static inline void nrf_rramc_task_trigger(struct fake_rram *p,int task) {
    ++commits;
    if (corrupt_write) *(volatile uint32_t *)(uintptr_t)0x100000 = 0;
}
