# SPDX-License-Identifier: BSD-3-Clause

include_guard(GLOBAL)

function(_nrfkit_validate_nrfxlib out_var)
  if(DEFINED NRFKIT_NRFXLIB_ROOT)
    if(NRFKIT_NRFXLIB_ROOT STREQUAL "")
      message(FATAL_ERROR "NRFKIT_NRFXLIB_ROOT must not be empty")
    endif()
    get_filename_component(root "${NRFKIT_NRFXLIB_ROOT}" ABSOLUTE
      BASE_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
  else()
    set(root "${NrfKit_ROOT}/external/sdk-nrfxlib")
  endif()
  if(NOT IS_DIRECTORY "${root}")
    message(FATAL_ERROR "NrfKit sdk-nrfxlib input directory is missing: ${root}")
  endif()
  file(REAL_PATH "${root}" root)
  if(TARGET NrfKit::mpsl)
    get_target_property(previous_root NrfKit::mpsl NRFKIT_NRFXLIB_ROOT)
    if(NOT root STREQUAL previous_root)
      message(FATAL_ERROR "NrfKit sdk-nrfxlib input cannot change within a build tree")
    endif()
  endif()

  # The same public lock ships in source checkouts and installed packages.
  # No Python, network, or installed NCS workspace is needed for validation.
  set(lock_path "${NrfKit_ROOT}/docs/provenance/sources.lock")
  file(READ "${lock_path}" lock)
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${lock_path}")
  string(JSON source GET "${lock}" audited_sources sdk-nrfxlib-3.4.0)
  string(JSON commit GET "${source}" commit)
  string(JSON tag GET "${source}" tag)
  # An exported/installed tree has no Git metadata; its identity is established
  # by the complete selected-file hashes. Check both refs when metadata exists.
  if(EXISTS "${root}/.git")
    find_program(NRFKIT_GIT_EXECUTABLE git REQUIRED)
    foreach(ref IN ITEMS HEAD "refs/tags/${tag}^{}")
      execute_process(
        COMMAND "${NRFKIT_GIT_EXECUTABLE}" -C "${root}" rev-parse --verify "${ref}"
        RESULT_VARIABLE result OUTPUT_VARIABLE actual ERROR_VARIABLE error
        OUTPUT_STRIP_TRAILING_WHITESPACE TIMEOUT 10
      )
      if(NOT result EQUAL 0 OR NOT actual STREQUAL commit)
        message(FATAL_ERROR "NrfKit sdk-nrfxlib identity mismatch: ${ref}")
      endif()
    endforeach()
  endif()

  string(JSON count LENGTH "${source}" files)
  math(EXPR last "${count} - 1")
  set(expected_headers "")
  foreach(index RANGE 0 ${last})
    string(JSON relative MEMBER "${source}" files ${index})
    string(JSON expected_hash GET "${source}" files "${relative}" sha256)
    set(path "${root}/${relative}")
    if(NOT EXISTS "${path}")
      message(FATAL_ERROR "NrfKit sdk-nrfxlib input is missing: ${relative}")
    endif()
    file(SHA256 "${path}" actual_hash)
    if(NOT actual_hash STREQUAL expected_hash)
      message(FATAL_ERROR "NrfKit sdk-nrfxlib input hash mismatch: ${relative}")
    endif()
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${path}")
    if(relative MATCHES "^(mpsl/include|mpsl/fem/include|softdevice_controller/include)/.*\\.h$")
      list(APPEND expected_headers "${relative}")
    endif()
  endforeach()
  file(GLOB_RECURSE actual_headers CONFIGURE_DEPENDS RELATIVE "${root}"
    "${root}/mpsl/include/*.h"
    "${root}/mpsl/fem/include/*.h"
    "${root}/softdevice_controller/include/*.h"
  )
  list(SORT expected_headers)
  list(SORT actual_headers)
  if(NOT actual_headers STREQUAL expected_headers)
    message(FATAL_ERROR "NrfKit sdk-nrfxlib public header set mismatch")
  endif()
  set(${out_var} "${root}" PARENT_SCOPE)
endfunction()
