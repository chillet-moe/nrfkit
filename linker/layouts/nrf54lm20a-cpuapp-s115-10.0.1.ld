/* SPDX-License-Identifier: BSD-3-Clause */

ENTRY(Reset_Handler)

/*
 * S115 10.0.1 occupies 0x001e3800..0x001fcbff. The two 4 KiB pages below
 * it are reserved for settings. Keep the first implementation within SRAM
 * bank 0. The application boundary matches the version-locked official HIDS
 * build with its one-peripheral-link and 1408-byte attribute-table settings.
 */
MEMORY
{
  RRAM         (rx)  : ORIGIN = 0x00000000, LENGTH = 0x001E1800
  SETTINGS     (rw)  : ORIGIN = 0x001E1800, LENGTH = 0x00002000
  SOFTDEVICE   (rx)  : ORIGIN = 0x001E3800, LENGTH = 0x00019400
  RAM          (rwx) : ORIGIN = 0x20004400, LENGTH = 0x0003BC00
}

__settings_start = ORIGIN(SETTINGS);
__settings_end = ORIGIN(SETTINGS) + LENGTH(SETTINGS);
__softdevice_start = ORIGIN(SOFTDEVICE);
__softdevice_end = ORIGIN(SOFTDEVICE) + LENGTH(SOFTDEVICE);
__softdevice_ram_end = ORIGIN(RAM);

SECTIONS
{
  .isr_vector ORIGIN(RRAM) : ALIGN(4)
  {
    __vector_start = .;
    KEEP(*(.isr_vector))
    __vector_end = .;
  } > RRAM

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

  nrfkit_nrf_sdh_stack_evt_observers : ALIGN(4)
  {
    __start_nrfkit_nrf_sdh_stack_evt_observers = .;
    KEEP(*(SORT_BY_NAME(nrfkit_nrf_sdh_stack_evt_observers.*)))
    __stop_nrfkit_nrf_sdh_stack_evt_observers = .;
  } > RRAM
  nrfkit_nrf_sdh_soc_evt_observers : ALIGN(4)
  {
    __start_nrfkit_nrf_sdh_soc_evt_observers = .;
    KEEP(*(SORT_BY_NAME(nrfkit_nrf_sdh_soc_evt_observers.*)))
    __stop_nrfkit_nrf_sdh_soc_evt_observers = .;
  } > RRAM
  nrfkit_nrf_sdh_ble_evt_observers : ALIGN(4)
  {
    __start_nrfkit_nrf_sdh_ble_evt_observers = .;
    KEEP(*(SORT_BY_NAME(nrfkit_nrf_sdh_ble_evt_observers.*)))
    __stop_nrfkit_nrf_sdh_ble_evt_observers = .;
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
    . = ALIGN(4);
    __start_nrfkit_nrf_sdh_state_evt_observers = .;
    KEEP(*(SORT_BY_NAME(nrfkit_nrf_sdh_state_evt_observers.*)))
    __stop_nrfkit_nrf_sdh_state_evt_observers = .;
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

ASSERT(ADDR(.isr_vector) == 0, "application vector table must start at zero")
ASSERT(SIZEOF(.isr_vector) == 0x4C8, "unexpected nRF54LM20A vector table size")
ASSERT(LOADADDR(.data) + SIZEOF(.data) <= ORIGIN(RRAM) + LENGTH(RRAM), "application RRAM overflow")
ASSERT(__noinit_end <= __StackLimit, "application RAM overlaps stack")
ASSERT(__HeapLimit <= __StackLimit, "heap overlaps stack")
ASSERT(ORIGIN(SETTINGS) + LENGTH(SETTINGS) == ORIGIN(SOFTDEVICE), "settings/SoftDevice gap")
ASSERT(ORIGIN(SOFTDEVICE) == 0x001E3800, "unexpected S115 base")
ASSERT(LENGTH(SOFTDEVICE) == 0x00019400, "unexpected S115 size")
ASSERT(ORIGIN(RAM) == 0x20004400, "unexpected S115 HIDS application RAM start")
