/* SPDX-License-Identifier: BSD-3-Clause */

#include <stdint.h>

volatile uint32_t initialized_word = UINT32_C(0x12345678);
volatile uint32_t zeroed_word;
volatile uint32_t retained_word __attribute__((section(".noinit.example")));

int main(void)
{
    retained_word = initialized_word + zeroed_word;
    for (;;) {
        __asm volatile ("wfe");
    }
}
