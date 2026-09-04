/* SPDX-License-Identifier: BSD-3-Clause */

#include <stdint.h>

#include <nrfkit/runtime.h>

volatile struct nrfkit_fault_record nrfkit_last_fault
    __attribute__((section(".noinit.fault")));

__attribute__((noinline)) void nrfkit_fault_observed(void)
{
    __asm volatile ("" ::: "memory");
}

void nrfkit_capture_fault(const uint32_t *frame, uint32_t exc_return)
{
    nrfkit_last_fault.magic = NRFKIT_FAULT_MAGIC;
    nrfkit_last_fault.exc_return = exc_return;
    nrfkit_last_fault.r0 = frame[0];
    nrfkit_last_fault.r1 = frame[1];
    nrfkit_last_fault.r2 = frame[2];
    nrfkit_last_fault.r3 = frame[3];
    nrfkit_last_fault.r12 = frame[4];
    nrfkit_last_fault.lr = frame[5];
    nrfkit_last_fault.pc = frame[6];
    nrfkit_last_fault.xpsr = frame[7];
    nrfkit_fault_observed();

    for (;;) {
        __asm volatile ("dsb\n\twfe");
    }
}

void nrfkit_assert_fail(void)
{
    __asm volatile ("udf #0");
    __builtin_unreachable();
}

__attribute__((naked)) void HardFault_Handler(void)
{
    __asm volatile (
        "tst lr, #4\n"
        "ite eq\n"
        "mrseq r0, msp\n"
        "mrsne r0, psp\n"
        "mov r1, lr\n"
        "b nrfkit_capture_fault\n");
}
