# SPDX-License-Identifier: BSD-3-Clause

cmake_minimum_required(VERSION 3.25)
project(nrfkit_combined_contract C CXX ASM)

find_package(NrfKit CONFIG REQUIRED)
include("${NrfKit_ROOT}/examples/common/usb/reference.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/../platform.cmake")

add_executable(contract main.cpp)
target_compile_features(contract PRIVATE cxx_std_23)
nrfkit_test_firmware(contract)

set(usb_args CLASSES hid)
if(COMBINED_PORT_ONLY)
  list(PREPEND usb_args PORT_ONLY)
endif()
if(NOT COMBINED_NO_SDC)
  list(PREPEND usb_args MPSL)
endif()
nrfkit_example_usb(contract ${usb_args})
if(COMBINED_PORT_ONLY)
  target_sources(contract PRIVATE
    "${NrfKit_ROOT}/external/cherryusb/core/usbd_core.c"
    "${NrfKit_ROOT}/external/cherryusb/class/hid/usbd_hid.c")
endif()

# Keep the SDC-last and missing-SDC compositions covered. The helper's MPSL
# option records the explicit shared-clock integration independently of link order.
if(COMBINED_SDC_LAST OR COMBINED_NO_SDC)
  target_link_libraries(contract PRIVATE NrfKit::rram)
  target_link_libraries(contract PRIVATE NrfKit::radio_timeslot)
  if(NOT COMBINED_NO_SDC)
    target_link_libraries(contract PRIVATE NrfKit::sdc_multirole)
  endif()
else()
  target_link_libraries(contract PRIVATE NrfKit::sdc_multirole)
endif()
if(NOT COMBINED_SDC_LAST AND NOT COMBINED_NO_SDC)
  target_link_libraries(contract PRIVATE NrfKit::radio_timeslot)
  target_link_libraries(contract PRIVATE NrfKit::rram)
endif()
target_link_libraries(contract PRIVATE NrfKit::nrfx_rramc)
if(COMBINED_NRFX_CLOCK)
  target_link_libraries(contract PRIVATE NrfKit::nrfx_clock)
endif()
