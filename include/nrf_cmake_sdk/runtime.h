/* SPDX-License-Identifier: BSD-3-Clause */

#ifndef NRF_CMAKE_SDK_RUNTIME_H
#define NRF_CMAKE_SDK_RUNTIME_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NRF_CMAKE_SDK_FAULT_MAGIC UINT32_C(0x4E524646)

struct nrf_cmake_sdk_fault_record {
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

extern volatile struct nrf_cmake_sdk_fault_record nrf_cmake_sdk_last_fault;

void nrf_sdk_start(void) __attribute__((noreturn));

#ifdef __cplusplus
}
#endif

#endif
