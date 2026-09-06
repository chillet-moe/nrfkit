# SPDX-License-Identifier: BSD-3-Clause

include_guard(GLOBAL)

# This manifest is deliberately a fixed list.  It is the reviewed nrfx
# driver/header closure consumed by NrfKit; configure never copies the whole
# upstream checkout (which also contains unrelated devices and tooling).
set(_NRFKIT_NRFX_SELECTION_FILE
  "${NrfKit_ROOT}/cmake/nrfx-selection.txt")
set(_NRFKIT_CMSIS_SELECTION_FILE
  "${NrfKit_ROOT}/cmake/cmsis-selection.txt")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
  "${_NRFKIT_NRFX_SELECTION_FILE}" "${_NRFKIT_CMSIS_SELECTION_FILE}")

function(_nrfkit_read_file_selection manifest out_var)
  if(NOT EXISTS "${manifest}")
    message(FATAL_ERROR "NrfKit dependency selection manifest is missing: ${manifest}")
  endif()
  file(STRINGS "${manifest}" selected
    REGEX "^[^#][^\r\n]+$")
  list(REMOVE_DUPLICATES selected)
  foreach(relative IN LISTS selected)
    if(IS_ABSOLUTE "${relative}" OR relative MATCHES "(^|/)\.\.(/|$)"
        OR relative MATCHES "\\\\" OR relative MATCHES "^[A-Za-z]:")
      message(FATAL_ERROR "NrfKit dependency selection contains an unsafe path: ${relative}")
    endif()
  endforeach()
  set(${out_var} "${selected}" PARENT_SCOPE)
endfunction()

function(_nrfkit_read_selection out_var)
  _nrfkit_read_file_selection("${_NRFKIT_NRFX_SELECTION_FILE}" selected)
  set(${out_var} "${selected}" PARENT_SCOPE)
endfunction()

function(_nrfkit_read_cmsis_selection out_var)
  _nrfkit_read_file_selection("${_NRFKIT_CMSIS_SELECTION_FILE}" selected)
  set(${out_var} "${selected}" PARENT_SCOPE)
endfunction()

function(_nrfkit_validate_selection root selected)
  foreach(relative IN LISTS selected)
    if(NOT EXISTS "${root}/${relative}" OR IS_DIRECTORY "${root}/${relative}")
      message(FATAL_ERROR "NrfKit dependency selection input is missing: ${relative}")
    endif()
  endforeach()
endfunction()

function(_nrfkit_copy_selection source destination selected)
  foreach(relative IN LISTS selected)
    get_filename_component(directory "${destination}/${relative}" DIRECTORY)
    file(MAKE_DIRECTORY "${directory}")
    file(COPY_FILE "${source}/${relative}" "${destination}/${relative}"
      ONLY_IF_DIFFERENT)
  endforeach()
endfunction()
