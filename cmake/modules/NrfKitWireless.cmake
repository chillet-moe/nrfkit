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

# Source capabilities compile in each consuming firmware's own context.
foreach(variant IN ITEMS multirole peripheral central)
  add_library("NrfKit::sdc_${variant}" INTERFACE IMPORTED GLOBAL)
  string(TOUPPER "${variant}" variant_upper)
  set_target_properties("NrfKit::sdc_${variant}" PROPERTIES
    SYSTEM FALSE NRFKIT_CAPABILITY sdc NRFKIT_SDC_VARIANT "${variant}")
  target_sources("NrfKit::sdc_${variant}" INTERFACE
    "${NrfKit_ROOT}/src/wireless/sdc/nrf54l/platform.c"
    "${NrfKit_ROOT}/src/wireless/sdc/nrf54l/hci.c")
  target_include_directories("NrfKit::sdc_${variant}" INTERFACE
    "${NrfKit_ROOT}/src/wireless/include")
  target_compile_definitions("NrfKit::sdc_${variant}" INTERFACE
    "NRFKIT_SDC_VARIANT_${variant_upper}=1")
  target_link_libraries("NrfKit::sdc_${variant}" INTERFACE
    "_nrfkit_sdc_binary_${variant}" NrfKit::nrfx_cracen)
endforeach()

foreach(name IN ITEMS radio_direct radio_timeslot rram)
  add_library("NrfKit::${name}" INTERFACE IMPORTED GLOBAL)
  set_target_properties("NrfKit::${name}" PROPERTIES SYSTEM FALSE NRFKIT_CAPABILITY "${name}")
endforeach()
target_sources(NrfKit::rram INTERFACE "${NrfKit_ROOT}/src/runtime/nrfx/rram.c")
foreach(name IN ITEMS radio_direct radio_timeslot)
  target_sources("NrfKit::${name}" INTERFACE
    "${NrfKit_ROOT}/src/wireless/radio/ownership.c"
    "${NrfKit_ROOT}/src/wireless/radio/nrf54l/radio.c")
endforeach()
target_link_libraries(NrfKit::radio_direct INTERFACE NrfKit::nrfx_clock)
target_sources(NrfKit::radio_timeslot INTERFACE
  "${NrfKit_ROOT}/src/wireless/timeslot/nrf54l/timeslot.c")

function(_nrfkit_finalize_sdc target)
  get_target_property(ARG_VARIANT "${target}" NRFKIT_SDC_VARIANT)
  if(NOT ARG_VARIANT)
    return()
  endif()
  _nrfkit_define_nrfxlib_targets()
  nrfkit_claim_resources("${target}" OWNER sdc_mpsl RESOURCES ${_NRFKIT_SDC_RESOURCES})
  string(MAKE_C_IDENTIFIER "${target}" target_id)
  set(config_dir "${CMAKE_CURRENT_BINARY_DIR}/nrfkit/${target_id}")
  file(MAKE_DIRECTORY "${config_dir}")
  string(REPLACE ";" "\", \"" resources_json "${_NRFKIT_SDC_RESOURCES}")
  get_target_property(root _nrfkit_mpsl NRFKIT_NRFXLIB_ROOT)
  _nrfkit_generate_template(sdc-target.json.in "${config_dir}/sdc-target.json")
endfunction()

function(_nrfkit_validate_wireless target)
  get_target_property(usb_stack "${target}" NRFKIT_USB_DEVICE_STACK)
  get_target_property(sdc_variant "${target}" NRFKIT_SDC_VARIANT)
  get_target_property(nrfx_drivers "${target}" NRFKIT_NRFX_DRIVERS)
  get_target_property(timeslot "${target}" NRFKIT_MPSL_TIMESLOT_ENABLED)
  get_target_property(rram "${target}" NRFKIT_RRAM_ENABLED)
  if((timeslot OR rram) AND NOT sdc_variant)
    message(FATAL_ERROR "nrfkit_finalize_target: Timeslot/RRAM requires SDC on '${target}'")
  endif()
  get_target_property(direct "${target}" NRFKIT_RADIO_ENABLED)
  if(direct AND (sdc_variant OR timeslot))
    message(FATAL_ERROR "nrfkit_finalize_target: direct RADIO cannot coexist with SDC/Timeslot")
  endif()
  if(sdc_variant AND "clock" IN_LIST nrfx_drivers)
    message(FATAL_ERROR
      "nrfkit_finalize_target: '${target}' cannot link the nrfx CLOCK driver "
      "while SDC/MPSL owns CLOCK"
    )
  endif()
  if(usb_stack AND sdc_variant)
    # MPSL owns CLOCK while initialized. Its public clock arbitration API is
    # therefore the only safe way for USBHS to hold HFCLK24M on this target.
    target_compile_definitions("${target}" PRIVATE NRFKIT_USBHS_MPSL_CLOCK=1)
  endif()
endfunction()
