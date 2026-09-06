/* SPDX-License-Identifier: BSD-3-Clause */

#ifndef NRFKIT_FREESTANDING_STDLIB_H
#define NRFKIT_FREESTANDING_STDLIB_H

#if defined(__cplusplus) && defined(NRFKIT_USE_GNU_ARM_CXX_HEADERS)
#include_next <stdlib.h>
#else
#include <stddef.h>

/*
 * Freestanding targets intentionally provide no heap. This header exists so
 * libraries whose allocation-dependent features are disabled can include the
 * standard name without pulling in a hosted C library.
 */
#ifdef __cplusplus
extern "C" {
#endif
void abort(void) __attribute__((noreturn));
#ifdef __cplusplus
}
#endif
#endif

#endif
