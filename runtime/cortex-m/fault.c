/* SPDX-License-Identifier: BSD-3-Clause */

#include <stdint.h>

#include <nrf_cmake_sdk/runtime.h>

volatile struct nrf_cmake_sdk_fault_record nrf_cmake_sdk_last_fault
    __attribute__((section(".noinit.fault")));

__attribute__((noinline)) void nrf_cmake_sdk_fault_observed(void)
{
    __asm volatile ("" ::: "memory");
}

void nrf_cmake_sdk_capture_fault(const uint32_t *frame, uint32_t exc_return)
{
    nrf_cmake_sdk_last_fault.magic = NRF_CMAKE_SDK_FAULT_MAGIC;
    nrf_cmake_sdk_last_fault.exc_return = exc_return;
    nrf_cmake_sdk_last_fault.r0 = frame[0];
    nrf_cmake_sdk_last_fault.r1 = frame[1];
    nrf_cmake_sdk_last_fault.r2 = frame[2];
    nrf_cmake_sdk_last_fault.r3 = frame[3];
    nrf_cmake_sdk_last_fault.r12 = frame[4];
    nrf_cmake_sdk_last_fault.lr = frame[5];
    nrf_cmake_sdk_last_fault.pc = frame[6];
    nrf_cmake_sdk_last_fault.xpsr = frame[7];
    nrf_cmake_sdk_fault_observed();

    for (;;) {
        __asm volatile ("dsb\n\twfe");
    }
}

__attribute__((naked)) void HardFault_Handler(void)
{
    __asm volatile (
        "tst lr, #4\n"
        "ite eq\n"
        "mrseq r0, msp\n"
        "mrsne r0, psp\n"
        "mov r1, lr\n"
        "b nrf_cmake_sdk_capture_fault\n");
}
