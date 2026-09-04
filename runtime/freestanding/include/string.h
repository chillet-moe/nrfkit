/* SPDX-License-Identifier: BSD-3-Clause */

#ifndef NRFKIT_FREESTANDING_STRING_H
#define NRFKIT_FREESTANDING_STRING_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

void *memcpy(void *restrict destination, const void *restrict source, size_t count);
void *memmove(void *destination, const void *source, size_t count);
void *memset(void *destination, int value, size_t count);

#ifdef __cplusplus
}
#endif

#endif
