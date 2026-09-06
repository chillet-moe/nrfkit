# SPDX-License-Identifier: BSD-3-Clause

include_guard(GLOBAL)

if(TARGET NrfKit::core)
  return()
endif()

get_filename_component(_nrfkit_root "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
if(NOT EXISTS "${_nrfkit_root}/include/nrfkit/version.h")
  message(FATAL_ERROR "NrfKit source-tree package is incomplete")
endif()

add_library(NrfKit::core INTERFACE IMPORTED GLOBAL)
set_target_properties(NrfKit::core PROPERTIES
  SYSTEM FALSE
  INTERFACE_INCLUDE_DIRECTORIES "${_nrfkit_root}/include"
)
include("${CMAKE_CURRENT_LIST_DIR}/modules/NrfKitVersion.cmake")
_nrfkit_read_version("${_nrfkit_root}/include/nrfkit/version.h")
set(NrfKit_ROOT "${_nrfkit_root}")

include("${CMAKE_CURRENT_LIST_DIR}/modules/NrfKitPlatform.cmake")

unset(_nrfkit_root)
