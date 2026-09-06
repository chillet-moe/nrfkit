/* SPDX-License-Identifier: BSD-3-Clause */

#ifndef NRFKIT_FREESTANDING_STDIO_H
#define NRFKIT_FREESTANDING_STDIO_H

#if defined(__cplusplus) && defined(NRFKIT_USE_GNU_ARM_CXX_HEADERS)
#include_next <stdio.h>
#else
/* Hosted I/O is intentionally unavailable on freestanding firmware targets. */
#endif

#endif
