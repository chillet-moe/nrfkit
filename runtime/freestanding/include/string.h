/* SPDX-License-Identifier: BSD-3-Clause */

#ifndef NRFKIT_FREESTANDING_STRING_H
#define NRFKIT_FREESTANDING_STRING_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#define NRFKIT_RESTRICT __restrict
#else
#define NRFKIT_RESTRICT restrict
#endif

void *memcpy(void *NRFKIT_RESTRICT destination,
             const void *NRFKIT_RESTRICT source,
             size_t count);
void *memmove(void *destination, const void *source, size_t count);
void *memset(void *destination, int value, size_t count);
int memcmp(const void *left, const void *right, size_t count);
size_t strlen(const char *string);

#ifdef __cplusplus
}
#endif

#undef NRFKIT_RESTRICT

#endif
