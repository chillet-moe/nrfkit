# SPDX-License-Identifier: BSD-3-Clause

cmake_minimum_required(VERSION 3.25)
project(nrfx_contract C ASM)

find_package(NrfKit CONFIG REQUIRED)
include("${CMAKE_CURRENT_LIST_DIR}/../platform.cmake")

add_executable(contract main.c)
nrfkit_test_firmware(contract)

if(CONTRACT_CASE STREQUAL "conflict")
  nrfkit_claim_resources(contract OWNER first RESOURCES dppi20.channel.3)
  nrfkit_claim_resources(contract OWNER second RESOURCES dppi20.channel.3)
elseif(CONTRACT_CASE STREQUAL "out-of-range")
  nrfkit_claim_resources(contract OWNER invalid RESOURCES gpiote30.channel.4)
else()
  nrfkit_claim_resources(contract OWNER application RESOURCES
    dppi20.channel.3 dppi20.group.2 gpiote20.channel.5 timer21
  )
endif()

target_link_libraries(contract PRIVATE
  NrfKit::nrfx_gpiote NrfKit::nrfx_dppi NrfKit::nrfx_timer)
