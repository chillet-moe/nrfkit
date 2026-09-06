# SPDX-License-Identifier: BSD-3-Clause

include_guard(GLOBAL)

# Chip facts are usage requirements; image policy belongs to the consumer.
add_library(NrfKit::soc_nrf54lm20a INTERFACE IMPORTED GLOBAL)
set_target_properties(NrfKit::soc_nrf54lm20a PROPERTIES SYSTEM FALSE)
set(_nrfkit_mdk "${NrfKit_ROOT}/external/nrfx/bsp/stable/mdk")
target_link_libraries(NrfKit::soc_nrf54lm20a INTERFACE NrfKit::core)
target_sources(NrfKit::soc_nrf54lm20a INTERFACE
  "${_nrfkit_mdk}/nrf54l/system_nrf54l.c")
target_include_directories(NrfKit::soc_nrf54lm20a INTERFACE
  "${NrfKit_ROOT}/external/cmsis/CMSIS/Core/Include" "${_nrfkit_mdk}")
target_compile_definitions(NrfKit::soc_nrf54lm20a INTERFACE
  NRF54LM20A_XXAA NRF_APPLICATION)
target_compile_options(NrfKit::soc_nrf54lm20a INTERFACE
  $<$<COMPILE_LANGUAGE:C,CXX,ASM>:-mcpu=cortex-m33;-mthumb;-mfloat-abi=hard;-mfpu=fpv5-sp-d16>)
target_link_options(NrfKit::soc_nrf54lm20a INTERFACE
  -mcpu=cortex-m33 -mthumb -mfloat-abi=hard -mfpu=fpv5-sp-d16)

add_library(NrfKit::startup INTERFACE IMPORTED GLOBAL)
target_link_libraries(NrfKit::startup INTERFACE NrfKit::soc_nrf54lm20a)
target_sources(NrfKit::startup INTERFACE
  "${_nrfkit_mdk}/nrf54l/nrf54lm20a/gcc_startup_nrf54lm20a_application.S")

# The optional runtime supplies its own entry point and minimal C library.
# Stack/heap sizes, language policy, and MEMORY/SECTIONS remain application-owned.
add_library(NrfKit::runtime_freestanding INTERFACE IMPORTED GLOBAL)
set_target_properties(NrfKit::runtime_freestanding PROPERTIES SYSTEM FALSE)
target_link_libraries(NrfKit::runtime_freestanding INTERFACE NrfKit::startup)
target_sources(NrfKit::runtime_freestanding INTERFACE
  "${NrfKit_ROOT}/src/runtime/common/freestanding.c"
  "${NrfKit_ROOT}/src/runtime/cortex-m/fault.c"
  "${NrfKit_ROOT}/src/runtime/cortex-m/reset.c")
target_include_directories(NrfKit::runtime_freestanding INTERFACE
  "${NrfKit_ROOT}/src/runtime/freestanding/include")
target_compile_definitions(NrfKit::runtime_freestanding INTERFACE
  __STARTUP_CLEAR_BSS __START=nrfkit_start)
target_compile_options(NrfKit::runtime_freestanding INTERFACE
  $<$<COMPILE_LANGUAGE:C,CXX>:-ffreestanding;-fno-common>)
target_link_options(NrfKit::runtime_freestanding INTERFACE -nostdlib
  "LINKER:-T,${NrfKit_ROOT}/linker/common/nrf54lm20a-startup-contract.ld")
set_property(TARGET NrfKit::runtime_freestanding APPEND PROPERTY
  INTERFACE_LINK_DEPENDS "${NrfKit_ROOT}/linker/common/nrf54lm20a-startup-contract.ld")
if(CMAKE_C_COMPILER_ID MATCHES "Clang")
  target_link_options(NrfKit::runtime_freestanding INTERFACE -fuse-ld=lld)
elseif(CMAKE_C_COMPILER_ID STREQUAL "GNU")
  # GCC can lower ordinary arithmetic to libgcc even in a freestanding program.
  target_link_libraries(NrfKit::runtime_freestanding INTERFACE gcc)
endif()

add_library(NrfKit::board_nrf54lm20dk INTERFACE IMPORTED GLOBAL)
set_target_properties(NrfKit::board_nrf54lm20dk PROPERTIES SYSTEM FALSE)
target_link_libraries(NrfKit::board_nrf54lm20dk INTERFACE NrfKit::soc_nrf54lm20a)
target_include_directories(NrfKit::board_nrf54lm20dk INTERFACE
  "${NrfKit_ROOT}/src/boards/nrf54lm20dk/include")
unset(_nrfkit_mdk)

include("${CMAKE_CURRENT_LIST_DIR}/NrfKitNrfxlib.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/NrfKitNrfx.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/NrfKitWireless.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/NrfKitUsb.cmake")
