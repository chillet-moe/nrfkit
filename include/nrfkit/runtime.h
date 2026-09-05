/* SPDX-License-Identifier: BSD-3-Clause */

#ifndef NRFKIT_RUNTIME_H
#define NRFKIT_RUNTIME_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NRFKIT_FAULT_MAGIC UINT32_C(0x4E524646)

struct nrfkit_fault_record {
    uint32_t magic;
    uint32_t exc_return;
    uint32_t r0;
    uint32_t r1;
    uint32_t r2;
    uint32_t r3;
    uint32_t r12;
    uint32_t lr;
    uint32_t pc;
    uint32_t xpsr;
};

extern volatile struct nrfkit_fault_record nrfkit_last_fault;

void nrfkit_start(void) __attribute__((noreturn));
void nrfkit_assert_fail(void) __attribute__((noreturn));
/** Reset LM20 with the revision-matched anomaly 63 workaround. */
void nrfkit_system_reset(void) __attribute__((noreturn));

#ifdef __cplusplus
}
#endif

#endif
