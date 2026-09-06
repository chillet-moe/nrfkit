/* SPDX-License-Identifier: BSD-3-Clause */
/* Startup ABI and conservative LM20 physical bounds. Consumer MEMORY regions
 * and assertions enforce its narrower application/boot/settings boundaries. */
ASSERT(SIZEOF(.isr_vector) == 0x4c8, "nrfkit: vector size")
ASSERT((ADDR(.isr_vector) & 0x7ff) == 0, "nrfkit: vector alignment")
ASSERT(__vector_start == ADDR(.isr_vector), "nrfkit: vector symbol")
ASSERT(((ADDR(.isr_vector) < 0x001FD000 && ADDR(.isr_vector) + SIZEOF(.isr_vector) <= 0x001FD000) || (ADDR(.isr_vector) >= 0x20000000 && ADDR(.isr_vector) + SIZEOF(.isr_vector) <= 0x20040000)), "nrfkit: vector outside physical memory")
ASSERT(((ADDR(.text) < 0x001FD000 && ADDR(.text) + SIZEOF(.text) <= 0x001FD000) || (ADDR(.text) >= 0x20000000 && ADDR(.text) + SIZEOF(.text) <= 0x20040000)), "nrfkit: text outside physical memory")
ASSERT(__data_load_start == LOADADDR(.data), "nrfkit: data copy source")
ASSERT(__data_start == ADDR(.data) && __data_end >= __data_start + SIZEOF(.data), "nrfkit: data copy destination")
ASSERT(((LOADADDR(.data) < 0x001FD000 && LOADADDR(.data) + SIZEOF(.data) <= 0x001FD000) || (LOADADDR(.data) >= 0x20000000 && LOADADDR(.data) + SIZEOF(.data) <= 0x20040000)), "nrfkit: data load outside physical memory")
ASSERT(__data_start >= 0x20000000 && __data_end <= 0x20040000, "nrfkit: data outside physical RAM")
ASSERT(__bss_start__ == ADDR(.bss) && __bss_end__ >= __bss_start__ + SIZEOF(.bss), "nrfkit: BSS zero range")
ASSERT(__bss_start__ >= 0x20000000 && __bss_end__ <= 0x20040000, "nrfkit: BSS outside physical RAM")
ASSERT(__noinit_start >= 0x20000000 && __noinit_end <= 0x20040000, "nrfkit: noinit outside physical RAM")
ASSERT(__StackLimit >= 0x20000000 && __StackTop <= 0x20040000 && __StackTop > __StackLimit && (__StackTop & 7) == 0, "nrfkit: stack bounds/alignment")
ASSERT(__HeapLimit <= __StackLimit && __noinit_end <= __StackLimit && __bss_end__ <= __StackLimit && __data_end <= __StackLimit, "nrfkit: RAM overlaps stack")
