/* SPDX-License-Identifier: BSD-3-Clause */

int main(void)
{
    __asm volatile ("udf #0");
    __builtin_unreachable();
}
