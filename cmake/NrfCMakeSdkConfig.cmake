# SPDX-License-Identifier: BSD-3-Clause

include_guard(GLOBAL)

if(TARGET NrfCMakeSdk::core)
  return()
endif()

get_filename_component(_nrf_cmake_sdk_root "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
if(NOT EXISTS "${_nrf_cmake_sdk_root}/include/nrf_cmake_sdk/version.h")
  message(FATAL_ERROR "NrfCMakeSdk source-tree package is incomplete")
endif()

add_library(NrfCMakeSdk::core INTERFACE IMPORTED)
set_target_properties(NrfCMakeSdk::core PROPERTIES
  INTERFACE_INCLUDE_DIRECTORIES "${_nrf_cmake_sdk_root}/include"
)
set(NrfCMakeSdk_VERSION "0.0.0")

unset(_nrf_cmake_sdk_root)
