# SPDX-License-Identifier: BSD-3-Clause

include_guard(GLOBAL)

# Shared preconditions apply to a firmware target, not to global build state.
function(_nrfkit_require_open_target target caller)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "${caller}: unknown target '${target}'")
  endif()
  get_target_property(configured "${target}" NRFKIT_CONFIGURED)
  if(NOT configured)
    message(FATAL_ERROR "${caller}: configure '${target}' first")
  endif()
  get_target_property(finalized "${target}" NRFKIT_FINALIZED)
  if(finalized)
    message(FATAL_ERROR "${caller}: '${target}' is already finalized")
  endif()
endfunction()

include("${CMAKE_CURRENT_LIST_DIR}/NrfKitNrfxlib.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/NrfKitNrfx.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/NrfKitWireless.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/NrfKitUsb.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/NrfKitImage.cmake")

function(nrfkit_configure_target target)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "nrfkit_configure_target: unknown target '${target}'")
  endif()

  cmake_parse_arguments(PARSE_ARGV 1 ARG ""
    "SOC;CORE;BOARD;RUNTIME;LINKER_SCRIPT;IMAGE_LAYOUT" "")
  if(ARG_UNPARSED_ARGUMENTS)
    message(FATAL_ERROR "nrfkit_configure_target: unknown arguments: ${ARG_UNPARSED_ARGUMENTS}")
  endif()
  if(NOT ARG_SOC STREQUAL "nrf54lm20a")
    message(FATAL_ERROR "M1 supports SOC nrf54lm20a only")
  endif()
  if(NOT ARG_CORE STREQUAL "cpuapp")
    message(FATAL_ERROR "nrf54lm20a supports CORE cpuapp only")
  endif()
  if(ARG_RUNTIME AND NOT ARG_RUNTIME STREQUAL "freestanding")
    message(FATAL_ERROR "M1 supports RUNTIME freestanding only")
  endif()
  if(ARG_BOARD AND NOT ARG_BOARD STREQUAL "nrf54lm20dk")
    message(FATAL_ERROR "M1 supports BOARD nrf54lm20dk only")
  endif()

  if((ARG_LINKER_SCRIPT AND NOT ARG_IMAGE_LAYOUT) OR
      (ARG_IMAGE_LAYOUT AND NOT ARG_LINKER_SCRIPT))
    message(FATAL_ERROR
      "nrfkit_configure_target: LINKER_SCRIPT and IMAGE_LAYOUT must be supplied together"
    )
  endif()

  set(sdk_root "${NrfKit_ROOT}")
  set(mdk "${sdk_root}/external/nrfx/bsp/stable/mdk")
  _nrfkit_configure_image_layout("${target}" "${ARG_LINKER_SCRIPT}" "${ARG_IMAGE_LAYOUT}"
    linker_script image_layout)
  foreach(required IN ITEMS
      "${mdk}/nrf54l/nrf54lm20a/gcc_startup_nrf54lm20a_application.S"
      "${mdk}/nrf54l/system_nrf54l.c"
      "${linker_script}")
    if(NOT EXISTS "${required}")
      message(FATAL_ERROR "NrfKit package is incomplete: ${required}")
    endif()
  endforeach()

  target_sources("${target}" PRIVATE
    "${mdk}/nrf54l/nrf54lm20a/gcc_startup_nrf54lm20a_application.S"
    "${mdk}/nrf54l/system_nrf54l.c"
    "${sdk_root}/src/runtime/common/freestanding.c"
    "${sdk_root}/src/runtime/cortex-m/fault.c"
    "${sdk_root}/src/runtime/cortex-m/reset.c"
  )
  target_include_directories("${target}" PRIVATE
    "${sdk_root}/include"
    "${sdk_root}/src/runtime/freestanding/include"
    "${sdk_root}/external/cmsis/CMSIS/Core/Include"
    "${mdk}"
  )
  if(ARG_BOARD)
    target_include_directories("${target}" PRIVATE
      "${sdk_root}/src/boards/${ARG_BOARD}/include"
    )
  endif()
  target_compile_definitions("${target}" PRIVATE
    NRF54LM20A_XXAA
    NRF_APPLICATION
    __STARTUP_CLEAR_BSS
    __START=nrfkit_start
    __STACK_SIZE=0x4000
    __HEAP_SIZE=0
  )
  target_compile_options("${target}" PRIVATE
    $<$<COMPILE_LANGUAGE:C,CXX,ASM>:-mcpu=cortex-m33;-mthumb;-mfloat-abi=hard;-mfpu=fpv5-sp-d16>
    $<$<COMPILE_LANGUAGE:C,CXX>:-ffreestanding;-ffunction-sections;-fdata-sections;-fno-common>
    $<$<COMPILE_LANGUAGE:CXX>:-fno-exceptions;-fno-rtti;-fno-threadsafe-statics;-fno-use-cxa-atexit>
  )

  target_link_options("${target}" PRIVATE
    -mcpu=cortex-m33 -mthumb -mfloat-abi=hard -mfpu=fpv5-sp-d16
    -nostdlib
    -Wl,--gc-sections
    -Wl,--build-id=none
    "-Wl,-Map,$<TARGET_FILE_DIR:${target}>/$<TARGET_FILE_BASE_NAME:${target}>.map"
    "-T${linker_script}"
  )
  if(CMAKE_C_COMPILER_ID MATCHES "Clang")
    target_link_options("${target}" PRIVATE -fuse-ld=lld)
  elseif(CMAKE_C_COMPILER_ID STREQUAL "GNU")
    # -nostdlib intentionally omits the C library and startup files, but GCC may
    # still lower ordinary C operations such as 64-bit division to libgcc.
    target_link_libraries("${target}" PRIVATE gcc)
  endif()
  set_target_properties("${target}" PROPERTIES
    SUFFIX ".elf"
    NRFKIT_CONFIGURED TRUE
    NRFKIT_SOC "nrf54lm20a"
    NRFKIT_CORE "cpuapp"
    NRFKIT_BOARD "${ARG_BOARD}"
    NRFKIT_IMAGE_LAYOUT "${image_layout}"
  )
  set_property(TARGET "${target}" APPEND PROPERTY LINK_DEPENDS "${linker_script}")
endfunction()

function(nrfkit_finalize_target target)
  _nrfkit_require_open_target("${target}" nrfkit_finalize_target)
  _nrfkit_validate_wireless("${target}")
  _nrfkit_finalize_nrfx("${target}")
  _nrfkit_add_image_artifacts("${target}")
  set_target_properties("${target}" PROPERTIES NRFKIT_FINALIZED TRUE)
endfunction()
