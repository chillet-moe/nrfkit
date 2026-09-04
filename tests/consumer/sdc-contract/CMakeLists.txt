# SPDX-License-Identifier: BSD-3-Clause

cmake_minimum_required(VERSION 3.25)
project(sdc_contract C ASM)

find_package(NrfKit CONFIG REQUIRED)

add_executable(contract main.c)
nrfkit_configure_target(contract
  SOC nrf54lm20a CORE cpuapp BOARD nrf54lm20dk RUNTIME freestanding
)

if(CONTRACT_CASE STREQUAL "conflict")
  nrfkit_claim_resources(contract OWNER application RESOURCES timer20)
  nrfkit_enable_sdc(contract VARIANT multirole)
elseif(CONTRACT_CASE STREQUAL "invalid-variant")
  nrfkit_enable_sdc(contract VARIANT observer)
else()
  nrfkit_enable_sdc(contract VARIANT multirole)
  nrfkit_finalize_target(contract)
endif()
