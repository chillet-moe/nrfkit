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
  set(usb_target NrfKit::usb_port)
  target_sources(contract PRIVATE
    "${NrfKit_ROOT}/external/cherryusb/core/usbd_core.c"
    "${NrfKit_ROOT}/external/cherryusb/class/hid/usbd_hid.c")
else()
  set(usb_target NrfKit::usb_device)
endif()

nrfkit_configure_usb(contract CLASSES hid)

# Exercise both link orders: finalization must select the same shared-clock
# integration after all target capabilities have been declared.
if(COMBINED_SDC_LAST OR COMBINED_NO_SDC)
  target_link_libraries(contract PRIVATE NrfKit::rram)
  target_link_libraries(contract PRIVATE NrfKit::radio_timeslot)
  target_link_libraries(contract PRIVATE ${usb_target})
  if(NOT COMBINED_NO_SDC)
    target_link_libraries(contract PRIVATE NrfKit::sdc_multirole)
  endif()
elseif(COMBINED_USB_FIRST)
  target_link_libraries(contract PRIVATE ${usb_target})
  target_link_libraries(contract PRIVATE NrfKit::sdc_multirole)
else()
  target_link_libraries(contract PRIVATE NrfKit::sdc_multirole)
  target_link_libraries(contract PRIVATE ${usb_target})
endif()
if(NOT COMBINED_SDC_LAST AND NOT COMBINED_NO_SDC)
  target_link_libraries(contract PRIVATE NrfKit::radio_timeslot)
  target_link_libraries(contract PRIVATE NrfKit::rram)
endif()
target_link_libraries(contract PRIVATE NrfKit::nrfx_rramc)
if(COMBINED_NRFX_CLOCK)
  target_link_libraries(contract PRIVATE NrfKit::nrfx_clock)
endif()
nrfkit_finalize_target(contract)
