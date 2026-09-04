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

static void call_forward(init_function *begin, init_function *end)
{
    for (init_function *function = begin; function != end; ++function) {
        (*function)();
    }
}

void nrf_sdk_start(void)
{
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
