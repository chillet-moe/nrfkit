# SPDX-License-Identifier: BSD-3-Clause

cmake_minimum_required(VERSION 3.25)
project(nrfkit_linked_targets C CXX ASM)

find_package(NrfKit CONFIG REQUIRED)
include("${NrfKit_ROOT}/examples/common/usb/reference.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/../platform.cmake")

set(LINKED_CASE "direct" CACHE STRING "link-target contract case")

add_executable(linked_firmware main.cpp)
target_compile_features(linked_firmware PRIVATE cxx_std_23)
nrfkit_test_firmware(linked_firmware)

if(LINKED_CASE STREQUAL "missing-sdc-rram")
  target_link_libraries(linked_firmware PRIVATE NrfKit::rram)
elseif(LINKED_CASE STREQUAL "conflict-sdc-variants")
  target_link_libraries(linked_firmware PRIVATE
    NrfKit::sdc_multirole NrfKit::sdc_peripheral)
elseif(LINKED_CASE STREQUAL "conflict-direct-radio")
  target_link_libraries(linked_firmware PRIVATE
    NrfKit::sdc_multirole NrfKit::radio_direct)
elseif(LINKED_CASE STREQUAL "conflict-clock")
  target_link_libraries(linked_firmware PRIVATE
    NrfKit::sdc_multirole NrfKit::nrfx_clock)
endif()

# The fixture deliberately consumes capabilities as ordinary CMake targets.
# The transitive path catches missing INTERFACE_LINK_LIBRARIES and include
# propagation that a target-name-only configure test would not observe.
add_library(linked_bundle INTERFACE)
if(LINKED_CASE STREQUAL "missing-sdc-rram" OR
   LINKED_CASE STREQUAL "conflict-sdc-variants" OR
   LINKED_CASE STREQUAL "conflict-direct-radio" OR
   LINKED_CASE STREQUAL "conflict-clock")
  # The case has already executed its expected failing operation above.
elseif(LINKED_CASE STREQUAL "native-conditional")
  target_link_libraries(linked_bundle INTERFACE
    "$<$<CONFIG:Debug>:NrfKit::sdc_peripheral>"
    "$<$<NOT:$<CONFIG:Debug>>:NrfKit::radio_direct>")
  target_link_libraries(linked_firmware PRIVATE linked_bundle)
elseif(LINKED_CASE STREQUAL "resource-masks")
  target_sources(linked_firmware PRIVATE reservation_contract.c)
  nrfkit_claim_resources(linked_firmware OWNER app RESOURCES dppi20.channel.3)
  nrfkit_claim_resources(linked_firmware OWNER app RESOURCES
    dppi20.group.2 gpiote20.channel.5)
  target_link_libraries(linked_firmware PRIVATE NrfKit::sdc_peripheral NrfKit::nrfx_dppi)
  target_compile_definitions(linked_firmware PRIVATE
    EXPECTED_CHANNELS=9 EXPECTED_GROUPS=4 EXPECTED_GPIOTE=32 EXPECTED_PRIORITY=6
    NRFX_DEFAULT_IRQ_PRIORITY=6)
  add_executable(independent_firmware main.cpp reservation_contract.c)
  nrfkit_test_firmware(independent_firmware)
  nrfkit_claim_resources(independent_firmware OWNER app RESOURCES dppi20.channel.4)
  target_link_libraries(independent_firmware PRIVATE NrfKit::nrfx_dppi)
  target_compile_definitions(independent_firmware PRIVATE
    EXPECTED_CHANNELS=16 EXPECTED_GROUPS=0 EXPECTED_GPIOTE=0 EXPECTED_PRIORITY=7)
elseif(LINKED_CASE STREQUAL "transitive-serial")
  target_link_libraries(linked_bundle INTERFACE NrfKit::nrfx_uarte)
  add_library(linked_alias ALIAS linked_bundle)
  add_library(linked_top INTERFACE)
  target_link_libraries(linked_top INTERFACE linked_alias NrfKit::nrfx_timer)
  target_link_libraries(linked_firmware PRIVATE linked_top)
elseif(LINKED_CASE STREQUAL "sdc-multirole" OR
       LINKED_CASE STREQUAL "sdc-peripheral" OR
       LINKED_CASE STREQUAL "sdc-central")
  string(REPLACE "sdc-" "" _variant "${LINKED_CASE}")
  target_link_libraries(linked_firmware PRIVATE "NrfKit::sdc_${_variant}")
elseif(LINKED_CASE STREQUAL "radio-direct")
  target_link_libraries(linked_firmware PRIVATE NrfKit::radio_direct)
elseif(LINKED_CASE STREQUAL "radio-timeslot")
  target_link_libraries(linked_firmware PRIVATE NrfKit::sdc_multirole NrfKit::radio_timeslot)
elseif(LINKED_CASE STREQUAL "rram")
  target_link_libraries(linked_firmware PRIVATE NrfKit::sdc_multirole NrfKit::rram)
elseif(LINKED_CASE STREQUAL "usb-port")
  nrfkit_example_usb(linked_firmware PORT_ONLY CLASSES hid
    IN_ENDPOINT_MAX_PACKET_SIZES 64 128)
  target_sources(linked_firmware PRIVATE
    "${NrfKit_ROOT}/external/cherryusb/core/usbd_core.c"
    "${NrfKit_ROOT}/external/cherryusb/class/hid/usbd_hid.c")
elseif(LINKED_CASE STREQUAL "usb-default")
  # A real consumer owns stack/configuration inputs even when using the SDK port.
  # This case intentionally does not call the example convenience helper.
  add_library(consumer_cherryusb INTERFACE)
  target_sources(consumer_cherryusb INTERFACE
    "${NrfKit_ROOT}/external/cherryusb/core/usbd_core.c")
  target_include_directories(consumer_cherryusb INTERFACE
    "${CMAKE_CURRENT_LIST_DIR}/usb-config"
    "${NrfKit_ROOT}/external/cherryusb/common"
    "${NrfKit_ROOT}/external/cherryusb/core"
    "${NrfKit_ROOT}/external/cherryusb/port/dwc2")
  target_link_libraries(linked_firmware PRIVATE NrfKit::usb_port consumer_cherryusb)
elseif(LINKED_CASE STREQUAL "custom-port")
  add_library(custom_port INTERFACE)
  target_sources(custom_port INTERFACE "${CMAKE_CURRENT_LIST_DIR}/custom_usb.c")
  target_link_libraries(linked_firmware PRIVATE custom_port)
elseif(LINKED_CASE STREQUAL "usb-dual")
  nrfkit_example_usb(linked_firmware CLASSES hid
    IN_ENDPOINT_MAX_PACKET_SIZES 64 128)
  add_executable(linked_usb_alt main.cpp)
  nrfkit_test_firmware(linked_usb_alt)
  nrfkit_example_usb(linked_usb_alt CLASSES hid
    IN_ENDPOINT_MAX_PACKET_SIZES 256 512)
  target_compile_definitions(linked_usb_alt PRIVATE LINKED_USB=1)
elseif(LINKED_CASE STREQUAL "multiple")
  add_executable(linked_radio main.cpp)
  nrfkit_test_firmware(linked_radio)
  target_link_libraries(linked_firmware PRIVATE
    NrfKit::nrfx_gpio NrfKit::nrfx_uarte NrfKit::nrfx_timer)
  target_link_libraries(linked_radio PRIVATE NrfKit::radio_direct)
  target_compile_definitions(linked_firmware PRIVATE LINKED_SERIAL=1)
  target_compile_definitions(linked_radio PRIVATE LINKED_RADIO=1)
else()
  target_link_libraries(linked_firmware PRIVATE
    NrfKit::nrfx_gpio NrfKit::nrfx_uarte NrfKit::nrfx_timer)
endif()

if(LINKED_CASE STREQUAL "direct" OR LINKED_CASE STREQUAL "transitive-serial")
  target_compile_definitions(linked_firmware PRIVATE LINKED_SERIAL=1)
elseif(LINKED_CASE MATCHES "^sdc-")
  target_compile_definitions(linked_firmware PRIVATE LINKED_SDC=1)
elseif(LINKED_CASE STREQUAL "radio-direct")
  target_compile_definitions(linked_firmware PRIVATE LINKED_RADIO=1)
elseif(LINKED_CASE STREQUAL "radio-timeslot")
  target_compile_definitions(linked_firmware PRIVATE LINKED_TIMESLOT=1)
elseif(LINKED_CASE STREQUAL "rram")
  target_compile_definitions(linked_firmware PRIVATE LINKED_RRAM=1)
elseif(LINKED_CASE MATCHES "^usb-")
  target_compile_definitions(linked_firmware PRIVATE LINKED_USB=1)
endif()
