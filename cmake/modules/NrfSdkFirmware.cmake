# SPDX-License-Identifier: BSD-3-Clause

include_guard(GLOBAL)

function(nrf_sdk_configure_target target)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "nrf_sdk_configure_target: unknown target '${target}'")
  endif()

  cmake_parse_arguments(PARSE_ARGV 1 ARG "" "SOC;CORE;BOARD;RUNTIME" "")
  if(ARG_UNPARSED_ARGUMENTS)
    message(FATAL_ERROR "nrf_sdk_configure_target: unknown arguments: ${ARG_UNPARSED_ARGUMENTS}")
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

  set(sdk_root "${NrfCMakeSdk_ROOT}")
  set(mdk "${sdk_root}/third_party/nrfx/mdk")
  set(linker_script "${sdk_root}/linker/layouts/nrf54lm20a-cpuapp-standalone.ld")
  foreach(required IN ITEMS
      "${mdk}/nrf54l/nrf54lm20a/gcc_startup_nrf54lm20a_application.S"
      "${mdk}/nrf54l/system_nrf54l.c"
      "${linker_script}")
    if(NOT EXISTS "${required}")
      message(FATAL_ERROR "NrfCMakeSdk package is incomplete: ${required}")
    endif()
  endforeach()

  target_sources("${target}" PRIVATE
    "${mdk}/nrf54l/nrf54lm20a/gcc_startup_nrf54lm20a_application.S"
    "${mdk}/nrf54l/system_nrf54l.c"
    "${sdk_root}/runtime/common/freestanding.c"
    "${sdk_root}/runtime/cortex-m/fault.c"
  )
  target_include_directories("${target}" PRIVATE
    "${sdk_root}/include"
    "${sdk_root}/third_party/cmsis/CMSIS/Core/Include"
    "${mdk}"
  )
  if(ARG_BOARD)
    target_include_directories("${target}" PRIVATE
      "${sdk_root}/boards/${ARG_BOARD}/include"
    )
  endif()
  target_compile_definitions("${target}" PRIVATE
    NRF54LM20A_XXAA
    NRF_APPLICATION
    __STARTUP_CLEAR_BSS
    __START=nrf_sdk_start
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
  endif()
  set_target_properties("${target}" PROPERTIES
    SUFFIX ".elf"
    NRF_CMAKE_SDK_CONFIGURED TRUE
    NRF_CMAKE_SDK_SOC "nrf54lm20a"
    NRF_CMAKE_SDK_CORE "cpuapp"
    NRF_CMAKE_SDK_BOARD "${ARG_BOARD}"
    LINK_DEPENDS "${linker_script}"
  )
endfunction()

function(nrf_sdk_finalize_target target)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "nrf_sdk_finalize_target: unknown target '${target}'")
  endif()
  get_target_property(configured "${target}" NRF_CMAKE_SDK_CONFIGURED)
  if(NOT configured)
    message(FATAL_ERROR "nrf_sdk_finalize_target: configure '${target}' first")
  endif()
  if(NOT CMAKE_OBJCOPY)
    message(FATAL_ERROR "CMAKE_OBJCOPY is required to finalize firmware")
  endif()

  set(hex "$<TARGET_FILE_DIR:${target}>/$<TARGET_FILE_BASE_NAME:${target}>.hex")
  set(bin "$<TARGET_FILE_DIR:${target}>/$<TARGET_FILE_BASE_NAME:${target}>.bin")
  add_custom_command(TARGET "${target}" POST_BUILD
    COMMAND "${CMAKE_OBJCOPY}" -O ihex "$<TARGET_FILE:${target}>" "${hex}"
    COMMAND "${CMAKE_OBJCOPY}" -O binary "$<TARGET_FILE:${target}>" "${bin}"
    VERBATIM
  )

  file(GENERATE
    OUTPUT "$<TARGET_FILE_DIR:${target}>/$<TARGET_FILE_BASE_NAME:${target}>.image-layout.json"
    CONTENT "{\n  \"schema\": \"nrf-cmake-sdk-image-layout/v1\",\n  \"target\": \"${target}\",\n  \"soc\": \"nrf54lm20a\",\n  \"core\": \"cpuapp\",\n  \"rram\": {\"origin\": 0, \"length\": 2084864},\n  \"ram\": {\"origin\": 536870912, \"length\": 262144},\n  \"configuration_regions_allowed\": false\n}\n"
  )
endfunction()
