# SPDX-License-Identifier: BSD-3-Clause

cmake_minimum_required(VERSION 3.25)

project(nrfkit_minimal_consumer LANGUAGES C)

find_package(NrfKit CONFIG REQUIRED)

if(NRFKIT_EXPECTED_VERSION AND
    (NOT NrfKit_VERSION STREQUAL NRFKIT_EXPECTED_VERSION OR
     NOT NrfKit_VERSION_STRING STREQUAL NRFKIT_EXPECTED_VERSION_STRING))
  message(FATAL_ERROR
    "NrfKit package version mismatch: numeric='${NrfKit_VERSION}', "
    "full='${NrfKit_VERSION_STRING}'"
  )
endif()

add_executable(minimal_consumer main.c)
target_link_libraries(minimal_consumer PRIVATE NrfKit::core)
