# SPDX-License-Identifier: BSD-3-Clause

cmake_minimum_required(VERSION 3.25)
project(sdc_contract C ASM)

find_package(NrfKit CONFIG REQUIRED)
include("${CMAKE_CURRENT_LIST_DIR}/../platform.cmake")

add_executable(contract main.c)
nrfkit_test_firmware(contract)

if(CONTRACT_CASE STREQUAL "conflict")
  nrfkit_claim_resources(contract OWNER application RESOURCES timer20)
  target_link_libraries(contract PRIVATE NrfKit::sdc_multirole)
elseif(CONTRACT_CASE STREQUAL "invalid-variant")
  target_link_libraries(contract PRIVATE NrfKit::sdc_observer)
else()
  if(NOT CONTRACT_VARIANT)
    set(CONTRACT_VARIANT multirole)
  endif()
  target_link_libraries(contract PRIVATE "NrfKit::sdc_${CONTRACT_VARIANT}")
endif()
