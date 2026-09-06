# SPDX-License-Identifier: BSD-3-Clause

cmake_minimum_required(VERSION 3.25)
project(nrfkit_custom_layout_consumer LANGUAGES C ASM)

find_package(NrfKit CONFIG REQUIRED)

add_executable(custom_layout main.c)
target_link_libraries(custom_layout PRIVATE
  NrfKit::soc_nrf54lm20a NrfKit::startup NrfKit::runtime_freestanding
)
set(CUSTOM_LINKER "${NrfKit_ROOT}/linker/layouts/nrf54lm20a-cpuapp-standalone.ld"
  CACHE FILEPATH "Consumer-owned linker script")
target_link_options(custom_layout PRIVATE
  "-T${CUSTOM_LINKER}"
  "-Wl,-Map=${CMAKE_CURRENT_BINARY_DIR}/custom_layout.map")
set_target_properties(custom_layout PROPERTIES SUFFIX ".elf")
