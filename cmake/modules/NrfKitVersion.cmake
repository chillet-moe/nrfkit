# SPDX-License-Identifier: BSD-3-Clause

include_guard(GLOBAL)

function(nrfkit_read_version header)
  if(NOT EXISTS "${header}")
    message(FATAL_ERROR "NrfKit version header is missing: ${header}")
  endif()
  file(READ "${header}" content)
  foreach(component IN ITEMS MAJOR MINOR PATCH)
    string(REGEX MATCH
      "#define[ \t]+NRFKIT_VERSION_${component}[ \t]+([0-9]+)"
      match "${content}"
    )
    if(NOT match)
      message(FATAL_ERROR "NrfKit version header has no ${component} component")
    endif()
    set(value_${component} "${CMAKE_MATCH_1}")
  endforeach()
  string(REGEX MATCH
    "#define[ \t]+NRFKIT_VERSION_STRING[ \t]+\"([^\"]+)\""
    string_match "${content}"
  )
  if(NOT string_match)
    message(FATAL_ERROR "NrfKit version header has no version string")
  endif()
  set(numeric
    "${value_MAJOR}.${value_MINOR}.${value_PATCH}"
  )
  set(full "${CMAKE_MATCH_1}")
  if(NOT full MATCHES "^${numeric}(-[0-9A-Za-z.-]+)?$")
    message(FATAL_ERROR
      "NrfKit version string '${full}' does not match numeric version '${numeric}'"
    )
  endif()
  set(NrfKit_VERSION "${numeric}" PARENT_SCOPE)
  set(NrfKit_VERSION_STRING "${full}" PARENT_SCOPE)
endfunction()
