# SPDX-License-Identifier: BSD-3-Clause

cmake_minimum_required(VERSION 3.25)
project(nrfkit_custom_layout_consumer LANGUAGES C ASM)

find_package(NrfKit CONFIG REQUIRED)

add_executable(custom_layout main.c)
nrfkit_configure_target(custom_layout
  SOC nrf54lm20a
  CORE cpuapp
  RUNTIME freestanding
  LINKER_SCRIPT "${NrfKit_ROOT}/linker/layouts/nrf54lm20a-cpuapp-standalone.ld"
  IMAGE_LAYOUT "${CMAKE_CURRENT_SOURCE_DIR}/image-layout.json"
)
nrfkit_finalize_target(custom_layout)
