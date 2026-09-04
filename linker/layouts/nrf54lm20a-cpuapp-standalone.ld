/* SPDX-License-Identifier: BSD-3-Clause */

ENTRY(Reset_Handler)

MEMORY
{
  RRAM         (rx)  : ORIGIN = 0x00000000, LENGTH = 0x001FCF00
  RRAM_SCRATCH (rw)  : ORIGIN = 0x001FCF00, LENGTH = 0x00000100
  RAM          (rwx) : ORIGIN = 0x20000000, LENGTH = 0x00040000
}

__rram_scratch_start = ORIGIN(RRAM_SCRATCH);
__rram_scratch_end = ORIGIN(RRAM_SCRATCH) + LENGTH(RRAM_SCRATCH);

SECTIONS
{
  .isr_vector ORIGIN(RRAM) : ALIGN(4)
  {
    __vector_start = .;
    KEEP(*(.isr_vector))
    __vector_end = .;
  } > RRAM

  /* Keep the load image contiguous when a compiler emits 16-byte-aligned code. */
  .vector_padding : ALIGN(4)
  {
    FILL(0xFF)
    BYTE(0xFF)
    . = ALIGN(16);
  } > RRAM

  .text : ALIGN(4)
  {
    *(.text .text.*)
    *(.rodata .rodata.*)
    *(.glue_7t) *(.glue_7)
    KEEP(*(.init))
    KEEP(*(.fini))
    FILL(0xFF)
    . = ALIGN(4);
  } > RRAM

  .ARM.extab : ALIGN(4) { *(.ARM.extab* .gnu.linkonce.armextab.*) } > RRAM
  .ARM.exidx : ALIGN(4)
  {
    __exidx_start = .;
    *(.ARM.exidx* .gnu.linkonce.armexidx.*)
    __exidx_end = .;
  } > RRAM

  .preinit_array : ALIGN(4)
  {
    PROVIDE_HIDDEN(__preinit_array_start = .);
    KEEP(*(.preinit_array))
    PROVIDE_HIDDEN(__preinit_array_end = .);
  } > RRAM
  .init_array : ALIGN(4)
  {
    PROVIDE_HIDDEN(__init_array_start = .);
    KEEP(*(SORT_BY_INIT_PRIORITY(.init_array.*)))
    KEEP(*(.init_array))
    PROVIDE_HIDDEN(__init_array_end = .);
  } > RRAM
  .fini_array : ALIGN(4)
  {
    PROVIDE_HIDDEN(__fini_array_start = .);
    KEEP(*(SORT_BY_INIT_PRIORITY(.fini_array.*)))
    KEEP(*(.fini_array))
    PROVIDE_HIDDEN(__fini_array_end = .);
  } > RRAM

  .data : ALIGN(4)
  {
    __data_start = .;
    *(.data .data.*)
    __data_end = ALIGN(4);
  } > RAM AT > RRAM
  __data_load_start = LOADADDR(.data);
  __sdata_start = __data_end;
  __sdata_end = __data_end;
  __sdata_load_start = __data_load_start + SIZEOF(.data);
  __tdata_start = __data_end;
  __tdata_end = __data_end;
  __tdata_load_start = __sdata_load_start;
  __fast_start = __data_end;
  __fast_end = __data_end;
  __fast_load_start = __sdata_load_start;

  .bss (NOLOAD) : ALIGN(4)
  {
    __bss_start__ = .;
    *(.bss .bss.* COMMON)
    __bss_end__ = ALIGN(4);
  } > RAM
  __sbss_start__ = __bss_end__;
  __sbss_end__ = __bss_end__;
  __tbss_start__ = __bss_end__;
  __tbss_end__ = __bss_end__;

  .noinit (NOLOAD) : ALIGN(4)
  {
    __noinit_start = .;
    *(.noinit .noinit.*)
    __noinit_end = ALIGN(4);
  } > RAM

  __HeapBase = ALIGN(__noinit_end, 8);
  __HeapLimit = __HeapBase;
  __StackLimit = ORIGIN(RAM) + LENGTH(RAM) - 0x4000;
  __StackTop = ORIGIN(RAM) + LENGTH(RAM);

  /DISCARD/ : { *(.heap) *(.stack) *(.note.gnu.build-id) *(.comment) }
}

ASSERT(ADDR(.isr_vector) == ORIGIN(RRAM), "vector table must start at RRAM origin")
ASSERT(SIZEOF(.isr_vector) == 0x4C8, "unexpected nRF54LM20A vector table size")
ASSERT(__data_end <= __StackLimit, "initialized RAM overlaps stack")
ASSERT(__bss_end__ <= __StackLimit, "zeroed RAM overlaps stack")
ASSERT(__noinit_end <= __StackLimit, "noinit RAM overlaps stack")
ASSERT(__HeapLimit <= __StackLimit, "heap overlaps stack")
ASSERT(__StackTop == ORIGIN(RAM) + LENGTH(RAM), "stack must end at conservative RAM boundary")
ASSERT(LOADADDR(.data) + SIZEOF(.data) <= ORIGIN(RRAM) + LENGTH(RRAM), "RRAM image overflow")
ASSERT(ORIGIN(RRAM) + LENGTH(RRAM) == ORIGIN(RRAM_SCRATCH), "RRAM image overlaps scratch")
ASSERT(ORIGIN(RRAM_SCRATCH) + LENGTH(RRAM_SCRATCH) == 0x001FD000, "unexpected RRAM scratch boundary")
