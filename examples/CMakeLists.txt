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

add_executable(linker_overlap EXCLUDE_FROM_ALL linker-overlap/main.c)
nrf_sdk_configure_target(linker_overlap
  SOC nrf54lm20a
  CORE cpuapp
  BOARD nrf54lm20dk
  RUNTIME freestanding
)
