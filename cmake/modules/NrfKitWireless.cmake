# SPDX-License-Identifier: BSD-3-Clause

include_guard(GLOBAL)

set(_NRFKIT_SDC_RESOURCES
  grtc.channel.7 grtc.channel.8 grtc.channel.9 grtc.channel.10 grtc.channel.11
  timer10 timer20 ecb00 radio0 clock temp
  dppi10.channel.0 dppi10.channel.1 dppi10.channel.2 dppi10.channel.3
  dppi10.channel.4 dppi10.channel.5 dppi10.channel.6 dppi10.channel.7
  dppi10.channel.8 dppi10.channel.9 dppi10.channel.10 dppi10.channel.11
  dppi20.channel.0 dppi00.channel.1 dppi00.channel.3
  ppib11.channel.0 ppib21.channel.0
  ppib00.channel.0 ppib00.channel.1 ppib00.channel.2 ppib00.channel.3
  ppib10.channel.0 ppib10.channel.1 ppib10.channel.2 ppib10.channel.3
  ccm00 aar00 rramc
)

function(_nrfkit_define_nrfxlib_targets)
  _nrfkit_validate_nrfxlib(root)
  if(TARGET _nrfkit_mpsl)
    return()
  endif()
  _nrfkit_prepare_nrfx(nrfx)
  set(paths
    mpsl/lib/nrf54lm/hard-float/libmpsl.a
    mpsl/fem/common/lib/nrf54lm/hard-float/libmpsl_fem_common.a
    softdevice_controller/lib/nrf54lm/hard-float/libsoftdevice_controller_multirole.a
    softdevice_controller/lib/nrf54lm/hard-float/libsoftdevice_controller_peripheral.a
    softdevice_controller/lib/nrf54lm/hard-float/libsoftdevice_controller_central.a
  )
  add_library(_nrfkit_mpsl STATIC IMPORTED GLOBAL)
  set_target_properties(_nrfkit_mpsl PROPERTIES
    NRFKIT_NRFXLIB_ROOT "${root}"
    INTERFACE_INCLUDE_DIRECTORIES
      "${root}/mpsl/include;${nrfx};${nrfx}/bsp/stable"
  )
  list(GET paths 0 mpsl_path)
  set_target_properties(_nrfkit_mpsl PROPERTIES IMPORTED_LOCATION "${root}/${mpsl_path}")
  add_library(_nrfkit_mpsl_fem_common STATIC IMPORTED GLOBAL)
  list(GET paths 1 mpsl_fem_path)
  set_target_properties(_nrfkit_mpsl_fem_common PROPERTIES
    IMPORTED_LOCATION "${root}/${mpsl_fem_path}"
    INTERFACE_INCLUDE_DIRECTORIES
      "${root}/mpsl/fem/include;${root}/mpsl/fem/include/protocol"
  )
  foreach(variant IN ITEMS multirole peripheral central)
    if(variant STREQUAL "multirole")
      set(index 2)
    elseif(variant STREQUAL "peripheral")
      set(index 3)
    else()
      set(index 4)
    endif()
    list(GET paths ${index} sdc_path)
    add_library("_nrfkit_sdc_binary_${variant}" STATIC IMPORTED GLOBAL)
    target_link_libraries("_nrfkit_sdc_binary_${variant}" INTERFACE _nrfkit_mpsl_fem_common _nrfkit_mpsl)
    set_target_properties("_nrfkit_sdc_binary_${variant}" PROPERTIES
      IMPORTED_LOCATION "${root}/${sdc_path}"
      INTERFACE_INCLUDE_DIRECTORIES
        "${root}/softdevice_controller/include;${root}/mpsl/include;${nrfx};${nrfx}/bsp/stable"
    )
  endforeach()
endfunction()

# Validate and expose the immutable archives at package import time.  Each
# public target below is complete by itself; consumers only link the variant
# they need.
_nrfkit_define_nrfxlib_targets()

# Source capabilities compile in each consuming firmware's own context.
foreach(variant IN ITEMS multirole peripheral central)
  add_library("NrfKit::sdc_${variant}" INTERFACE IMPORTED GLOBAL)
  string(TOUPPER "${variant}" variant_upper)
  set_target_properties("NrfKit::sdc_${variant}" PROPERTIES
    SYSTEM FALSE)
  target_sources("NrfKit::sdc_${variant}" INTERFACE
    "${NrfKit_ROOT}/src/wireless/sdc/nrf54l/platform.c"
    "${NrfKit_ROOT}/src/wireless/sdc/nrf54l/hci.c")
  target_include_directories("NrfKit::sdc_${variant}" INTERFACE
    "${NrfKit_ROOT}/src/wireless/include")
  target_compile_definitions("NrfKit::sdc_${variant}" INTERFACE
    "NRFKIT_SDC_VARIANT_${variant_upper}=1" NRFKIT_SDC_ENABLED=1)
  set_property(TARGET "NrfKit::sdc_${variant}" APPEND PROPERTY
    COMPATIBLE_INTERFACE_STRING NRFKIT_SDC_VARIANT NRFKIT_RADIO_MODE)
  set_property(TARGET "NrfKit::sdc_${variant}" PROPERTY
    INTERFACE_NRFKIT_SDC_VARIANT "${variant}")
  set_property(TARGET "NrfKit::sdc_${variant}" PROPERTY
    INTERFACE_NRFKIT_RADIO_MODE sdc)
  target_link_libraries("NrfKit::sdc_${variant}" INTERFACE
    "_nrfkit_sdc_binary_${variant}" NrfKit::nrfx_cracen)
  foreach(resource IN LISTS _NRFKIT_SDC_RESOURCES)
    string(MAKE_C_IDENTIFIER "${resource}" id)
    set_property(TARGET "NrfKit::sdc_${variant}" APPEND PROPERTY
      COMPATIBLE_INTERFACE_STRING "NRFKIT_RESOURCE_${id}")
    set_property(TARGET "NrfKit::sdc_${variant}" PROPERTY
      "INTERFACE_NRFKIT_RESOURCE_${id}" sdc_mpsl)
  endforeach()
  set_property(TARGET "NrfKit::sdc_${variant}" APPEND PROPERTY COMPATIBLE_INTERFACE_STRING NRFKIT_CLOCK_OWNER)
  set_property(TARGET "NrfKit::sdc_${variant}" PROPERTY INTERFACE_NRFKIT_CLOCK_OWNER sdc)
endforeach()

foreach(name IN ITEMS radio_direct radio_timeslot rram)
  add_library("NrfKit::${name}" INTERFACE IMPORTED GLOBAL)
  set_target_properties("NrfKit::${name}" PROPERTIES SYSTEM FALSE)
  set_property(TARGET "NrfKit::${name}" APPEND PROPERTY COMPATIBLE_INTERFACE_STRING NRFKIT_RADIO_MODE)
endforeach()
target_sources(NrfKit::rram INTERFACE "${NrfKit_ROOT}/src/runtime/nrfx/rram.c")
foreach(name IN ITEMS radio_direct radio_timeslot)
  target_sources("NrfKit::${name}" INTERFACE
    "${NrfKit_ROOT}/src/wireless/radio/ownership.c"
    "${NrfKit_ROOT}/src/wireless/radio/nrf54l/radio.c")
endforeach()
target_link_libraries(NrfKit::radio_direct INTERFACE NrfKit::nrfx_clock)
set_property(TARGET NrfKit::radio_direct PROPERTY INTERFACE_NRFKIT_RADIO_MODE direct)
target_sources(NrfKit::radio_timeslot INTERFACE
  "${NrfKit_ROOT}/src/wireless/timeslot/nrf54l/timeslot.c")
set_property(TARGET NrfKit::radio_timeslot PROPERTY INTERFACE_NRFKIT_RADIO_MODE sdc)
# Neither service chooses a Controller variant on the application's behalf.
# A tiny compile-time contract gives a direct error if no SDC target is linked.
foreach(name IN ITEMS radio_timeslot rram)
  target_sources("NrfKit::${name}" INTERFACE
    "${NrfKit_ROOT}/src/wireless/sdc/nrf54l/require_sdc.c")
  target_link_libraries("NrfKit::${name}" INTERFACE _nrfkit_nrfx_headers)
  target_include_directories("NrfKit::${name}" INTERFACE "${NrfKit_ROOT}/src/wireless/include")
endforeach()
