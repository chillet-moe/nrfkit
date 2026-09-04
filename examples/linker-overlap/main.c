/* SPDX-License-Identifier: BSD-3-Clause */

#include <stdint.h>

volatile uint8_t oversized_bss[0x3C004];

int main(void)
{
    return oversized_bss[0];
}
