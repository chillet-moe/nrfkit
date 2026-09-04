/* SPDX-License-Identifier: BSD-3-Clause */

#include <stddef.h>

typedef void (*init_function)(void);

extern init_function __preinit_array_start[];
extern init_function __preinit_array_end[];
extern init_function __init_array_start[];
extern init_function __init_array_end[];
extern init_function __fini_array_start[];
extern init_function __fini_array_end[];

extern int main(void);
extern void SystemCoreClockUpdate(void);

void *memcpy(void *restrict destination, const void *restrict source, size_t count)
{
    unsigned char *to = destination;
    const unsigned char *from = source;
    while (count-- != 0U) {
        *to++ = *from++;
    }
    return destination;
}

void *memmove(void *destination, const void *source, size_t count)
{
    unsigned char *to = destination;
    const unsigned char *from = source;
    if (to < from) {
        while (count-- != 0U) {
            *to++ = *from++;
        }
    } else if (to > from) {
        to += count;
        from += count;
        while (count-- != 0U) {
            *--to = *--from;
        }
    }
    return destination;
}

void *memset(void *destination, int value, size_t count)
{
    unsigned char *to = destination;
    while (count-- != 0U) {
        *to++ = (unsigned char)value;
    }
    return destination;
}

int memcmp(const void *left, const void *right, size_t count)
{
    const unsigned char *left_bytes = left;
    const unsigned char *right_bytes = right;
    while (count-- != 0U) {
        if (*left_bytes != *right_bytes) {
            return (int)*left_bytes - (int)*right_bytes;
        }
        ++left_bytes;
        ++right_bytes;
    }
    return 0;
}

size_t strlen(const char *string)
{
    const char *end = string;
    while (*end != '\0') {
        ++end;
    }
    return (size_t)(end - string);
}

void __aeabi_memcpy(void *destination, const void *source, size_t count)
{
    (void)memcpy(destination, source, count);
}

void __aeabi_memcpy4(void *destination, const void *source, size_t count)
{
    (void)memcpy(destination, source, count);
}

void __aeabi_memcpy8(void *destination, const void *source, size_t count)
{
    (void)memcpy(destination, source, count);
}

void __aeabi_memset(void *destination, size_t count, int value)
{
    (void)memset(destination, value, count);
}

void __aeabi_memset4(void *destination, size_t count, int value)
{
    (void)memset(destination, value, count);
}

void __aeabi_memclr(void *destination, size_t count)
{
    (void)memset(destination, 0, count);
}

void __aeabi_memclr4(void *destination, size_t count)
{
    (void)memset(destination, 0, count);
}

static void call_forward(init_function *begin, init_function *end)
{
    for (init_function *function = begin; function != end; ++function) {
        (*function)();
    }
}

void nrfkit_start(void)
{
    /* SystemInit selects the boot-time PLL frequency before entering here. */
    SystemCoreClockUpdate();
    call_forward(__preinit_array_start, __preinit_array_end);
    call_forward(__init_array_start, __init_array_end);
    (void)main();

    for (init_function *function = __fini_array_end;
         function != __fini_array_start;) {
        (*--function)();
    }

    for (;;) {
        __asm volatile ("wfe");
    }
}
