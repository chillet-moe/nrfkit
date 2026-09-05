# SPDX-License-Identifier: BSD-3-Clause

cmake_minimum_required(VERSION 3.25)
project(nrfkit_combined_contract C CXX ASM)

find_package(NrfKit CONFIG REQUIRED)

add_executable(contract main.cpp)
target_compile_features(contract PRIVATE cxx_std_23)
nrfkit_configure_target(contract
  SOC nrf54lm20a CORE cpuapp BOARD nrf54lm20dk RUNTIME freestanding
)

if(COMBINED_PORT_ONLY)
  set(usb_function nrfkit_enable_usb_port)
  target_sources(contract PRIVATE
    "${NrfKit_ROOT}/external/cherryusb/core/usbd_core.c"
    "${NrfKit_ROOT}/external/cherryusb/class/hid/usbd_hid.c")
else()
  set(usb_function nrfkit_enable_usb_device)
endif()

# Exercise both call orders: finalization must select the same shared-clock
# integration after all target capabilities have been declared.
if(COMBINED_USB_FIRST)
  cmake_language(CALL ${usb_function} contract STACK cherryusb CLASSES hid)
  nrfkit_enable_sdc(contract VARIANT multirole)
else()
  nrfkit_enable_sdc(contract VARIANT multirole)
  cmake_language(CALL ${usb_function} contract STACK cherryusb CLASSES hid)
endif()
nrfkit_enable_mpsl_timeslot(contract)
nrfkit_enable_rram(contract)
nrfkit_enable_nrfx(contract DRIVERS rramc)
if(COMBINED_NRFX_CLOCK)
  nrfkit_enable_nrfx(contract DRIVERS clock)
endif()
nrfkit_finalize_target(contract)
