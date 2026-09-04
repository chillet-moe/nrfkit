# SPDX-License-Identifier: BSD-3-Clause

cmake_minimum_required(VERSION 3.25)
project(nrf_cmake_sdk_m1_examples LANGUAGES C CXX ASM)

find_package(NrfCMakeSdk CONFIG REQUIRED)

function(add_m1_example name source)
  add_executable("${name}" "${source}")
  nrf_sdk_configure_target("${name}"
    SOC nrf54lm20a
    CORE cpuapp
    BOARD nrf54lm20dk
    RUNTIME freestanding
  )
  nrf_sdk_finalize_target("${name}")
endfunction()

add_m1_example(empty empty/main.c)
add_m1_example(blinky blinky/main.c)
add_m1_example(fault fault/main.c)
add_m1_example(constructors constructors/main.cpp)
target_compile_features(constructors PRIVATE cxx_std_23)

set(NRF_CMAKE_SDK_BUILD_ID "development" CACHE STRING
  "Build identifier emitted by the hardware-validation firmware"
)
if(NOT NRF_CMAKE_SDK_BUILD_ID MATCHES "^[A-Za-z0-9._-]+$")
  message(FATAL_ERROR "NRF_CMAKE_SDK_BUILD_ID contains an unsafe character")
endif()
add_m1_example(hardware_validation hardware-validation/main.c)
target_compile_definitions(hardware_validation PRIVATE
  NRF_CMAKE_SDK_BUILD_ID="${NRF_CMAKE_SDK_BUILD_ID}"
)

add_executable(linker_overlap EXCLUDE_FROM_ALL linker-overlap/main.c)
nrf_sdk_configure_target(linker_overlap
  SOC nrf54lm20a
  CORE cpuapp
  BOARD nrf54lm20dk
  RUNTIME freestanding
)

option(NRF_CMAKE_SDK_ENABLE_HARDWARE_TESTS
  "Register the destructive-to-application-RRAM M2 hardware gate" OFF
)
if(NRF_CMAKE_SDK_ENABLE_HARDWARE_TESTS)
  if(NOT NRF_CMAKE_SDK_TOOL)
    get_filename_component(NRF_CMAKE_SDK_TOOL
      "${CMAKE_CURRENT_LIST_DIR}/../tools/nrf-cmake-sdk" ABSOLUTE
    )
  endif()
  if(NOT NRF_CMAKE_SDK_GDB)
    message(FATAL_ERROR "NRF_CMAKE_SDK_GDB is required for hardware tests")
  endif()
  set(normal_token "NRF_CMAKE_SDK_BOOT ${NRF_CMAKE_SDK_BUILD_ID}")
  add_custom_command(TARGET hardware_validation POST_BUILD
    COMMAND "${NRF_CMAKE_SDK_TOOL}" sdk manifest
      --build-dir "$<TARGET_FILE_DIR:hardware_validation>"
      --target hardware_validation
      --expected-token "${normal_token}"
    VERBATIM
  )
  add_custom_command(TARGET fault POST_BUILD
    COMMAND "${NRF_CMAKE_SDK_TOOL}" sdk manifest
      --build-dir "$<TARGET_FILE_DIR:fault>"
      --target fault
      --expected-token NRF_CMAKE_SDK_FAULT
    VERBATIM
  )
  enable_testing()
  add_test(NAME m2_hardware_gate
    COMMAND "${NRF_CMAKE_SDK_TOOL}" m2-gate
      --normal-manifest "$<TARGET_FILE_DIR:hardware_validation>/hardware_validation.device-manifest.json"
      --fault-manifest "$<TARGET_FILE_DIR:fault>/fault.device-manifest.json"
      --gdb "${NRF_CMAKE_SDK_GDB}"
  )
  set_tests_properties(m2_hardware_gate PROPERTIES
    LABELS hardware
    RESOURCE_LOCK nrf54lm20dk
    TIMEOUT 2400
  )
endif()
