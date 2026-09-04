# SPDX-License-Identifier: BSD-3-Clause

include_guard(GLOBAL)

if(TARGET NrfKit::core)
  return()
endif()

get_filename_component(_nrfkit_root "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
if(NOT EXISTS "${_nrfkit_root}/include/nrfkit/version.h")
  message(FATAL_ERROR "NrfKit source-tree package is incomplete")
endif()

add_library(NrfKit::core INTERFACE IMPORTED)
set_target_properties(NrfKit::core PROPERTIES
  INTERFACE_INCLUDE_DIRECTORIES "${_nrfkit_root}/include"
)
set(NrfKit_VERSION "0.0.0")
set(NrfKit_ROOT "${_nrfkit_root}")

include("${CMAKE_CURRENT_LIST_DIR}/modules/NrfKitFirmware.cmake")

unset(_nrfkit_root)
