# SPDX-License-Identifier: BSD-3-Clause

cmake_minimum_required(VERSION 3.25)
project(nrfkit_linked_targets C CXX ASM)

find_package(NrfKit CONFIG REQUIRED)
include("${NrfKit_ROOT}/examples/common/usb/reference.cmake")

set(LINKED_CASE "direct" CACHE STRING "link-target contract case")

add_executable(linked_firmware main.cpp)
target_compile_features(linked_firmware PRIVATE cxx_std_23)
nrfkit_configure_target(linked_firmware
  SOC nrf54lm20a CORE cpuapp BOARD nrf54lm20dk RUNTIME freestanding
)

if(LINKED_CASE STREQUAL "duplicate-configure")
  nrfkit_configure_target(linked_firmware
    SOC nrf54lm20a CORE cpuapp BOARD nrf54lm20dk RUNTIME freestanding
  )
elseif(LINKED_CASE STREQUAL "duplicate-finalize")
  nrfkit_finalize_target(linked_firmware)
  nrfkit_finalize_target(linked_firmware)
elseif(LINKED_CASE STREQUAL "missing-sdc-rram")
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
elseif(LINKED_CASE STREQUAL "config-genex")
  target_link_libraries(linked_firmware PRIVATE
    "$<$<CONFIG:Debug>:NrfKit::nrfx_timer>")
elseif(LINKED_CASE STREQUAL "compiled-public")
  add_library(compiled_cap STATIC compiled.c)
  target_link_libraries(compiled_cap PUBLIC NrfKit::nrfx_timer)
  target_link_libraries(linked_firmware PRIVATE compiled_cap)
endif()

# The fixture deliberately consumes capabilities as ordinary CMake targets.
# The transitive path catches missing INTERFACE_LINK_LIBRARIES and include
# propagation that a target-name-only configure test would not observe.
add_library(linked_bundle INTERFACE)
if(LINKED_CASE STREQUAL "duplicate-configure" OR
   LINKED_CASE STREQUAL "duplicate-finalize" OR
   LINKED_CASE STREQUAL "missing-sdc-rram" OR
   LINKED_CASE STREQUAL "conflict-sdc-variants" OR
   LINKED_CASE STREQUAL "conflict-direct-radio" OR
   LINKED_CASE STREQUAL "conflict-clock" OR
   LINKED_CASE STREQUAL "config-genex" OR
   LINKED_CASE STREQUAL "compiled-public")
  # The case has already executed its expected failing operation above.
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
  nrfkit_configure_target(linked_usb_alt
    SOC nrf54lm20a CORE cpuapp BOARD nrf54lm20dk RUNTIME freestanding)
  nrfkit_example_usb(linked_usb_alt CLASSES hid
    IN_ENDPOINT_MAX_PACKET_SIZES 256 512)
  target_compile_definitions(linked_usb_alt PRIVATE LINKED_USB=1)
  nrfkit_finalize_target(linked_usb_alt)
elseif(LINKED_CASE STREQUAL "multiple")
  add_executable(linked_radio main.cpp)
  nrfkit_configure_target(linked_radio
    SOC nrf54lm20a CORE cpuapp BOARD nrf54lm20dk RUNTIME freestanding
  )
  target_link_libraries(linked_firmware PRIVATE
    NrfKit::nrfx_gpio NrfKit::nrfx_uarte NrfKit::nrfx_timer)
  target_link_libraries(linked_radio PRIVATE NrfKit::radio_direct)
  target_compile_definitions(linked_firmware PRIVATE LINKED_SERIAL=1)
  target_compile_definitions(linked_radio PRIVATE LINKED_RADIO=1)
  nrfkit_finalize_target(linked_radio)
  nrfkit_finalize_target(linked_firmware)
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

if(NOT LINKED_CASE STREQUAL "multiple")
  nrfkit_finalize_target(linked_firmware)
endif()
