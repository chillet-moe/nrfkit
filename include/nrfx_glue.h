/* SPDX-License-Identifier: BSD-3-Clause */

#ifndef NRFKIT_NRFX_GLUE_H
#define NRFKIT_NRFX_GLUE_H

#include <stdbool.h>
#include <stdint.h>

#include <nrf.h>
#include <nrfkit/runtime.h>
#include <lib/nrfx_coredep.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NRFX_ASSERT(expression)                                              \
    do {                                                                     \
        if (!(expression)) {                                                 \
            nrfkit_assert_fail();                                     \
        }                                                                    \
    } while (0)

#ifdef __cplusplus
#define NRFX_STATIC_ASSERT(expression) static_assert((expression), "")
#else
#define NRFX_STATIC_ASSERT(expression) _Static_assert((expression), "")
#endif

#define NRFX_IRQ_PRIORITY_SET(irq_number, priority) \
    NVIC_SetPriority((irq_number), (priority))
#define NRFX_IRQ_ENABLE(irq_number) NVIC_EnableIRQ(irq_number)
#define NRFX_IRQ_IS_ENABLED(irq_number) (NVIC_GetEnableIRQ(irq_number) != 0U)
#define NRFX_IRQ_DISABLE(irq_number) NVIC_DisableIRQ(irq_number)
#define NRFX_IRQ_PENDING_SET(irq_number) NVIC_SetPendingIRQ(irq_number)
#define NRFX_IRQ_PENDING_CLEAR(irq_number) NVIC_ClearPendingIRQ(irq_number)
#define NRFX_IRQ_IS_PENDING(irq_number) (NVIC_GetPendingIRQ(irq_number) != 0U)

/* The braces give every pair its own saved PRIMASK and make nesting safe. */
#define NRFX_CRITICAL_SECTION_ENTER()                                        \
    {                                                                        \
        uint32_t const nrfkit_saved_primask = __get_PRIMASK();        \
        __disable_irq()
#define NRFX_CRITICAL_SECTION_EXIT()                                         \
        if (nrfkit_saved_primask == 0U) {                             \
            __enable_irq();                                                  \
        }                                                                    \
    }

#define NRFX_COREDEP_DELAY_DWT_BASED 0
#define NRFX_DELAY_US(us_time) nrfx_coredep_delay_us(us_time)

typedef uint32_t nrfx_atomic_t;
#define NRFX_ATOMIC_FETCH_STORE(p_data, value) \
    __atomic_exchange_n((p_data), (value), __ATOMIC_SEQ_CST)
#define NRFX_ATOMIC_FETCH_OR(p_data, value) \
    __atomic_fetch_or((p_data), (value), __ATOMIC_SEQ_CST)
#define NRFX_ATOMIC_FETCH_AND(p_data, value) \
    __atomic_fetch_and((p_data), (value), __ATOMIC_SEQ_CST)
#define NRFX_ATOMIC_FETCH_XOR(p_data, value) \
    __atomic_fetch_xor((p_data), (value), __ATOMIC_SEQ_CST)
#define NRFX_ATOMIC_FETCH_ADD(p_data, value) \
    __atomic_fetch_add((p_data), (value), __ATOMIC_SEQ_CST)
#define NRFX_ATOMIC_FETCH_SUB(p_data, value) \
    __atomic_fetch_sub((p_data), (value), __ATOMIC_SEQ_CST)
#define NRFX_CLZ(value) ((uint32_t)__builtin_clz((uint32_t)(value)))
#define NRFX_CTZ(value) ((uint32_t)__builtin_ctz((uint32_t)(value)))

#define NRFX_CUSTOM_ERROR_CODES 0
#define NRFX_EVENT_READBACK_ENABLED 1

/* nRF54LM20A application core exposes no data cache. */
#define NRFY_CACHE_WB(p_buffer, size) ((void)(p_buffer), (void)(size))
#define NRFY_CACHE_INV(p_buffer, size) ((void)(p_buffer), (void)(size))
#define NRFY_CACHE_WBINV(p_buffer, size) ((void)(p_buffer), (void)(size))

#ifdef __cplusplus
}
#endif

#endif
