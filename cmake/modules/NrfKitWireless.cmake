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
  if(TARGET NrfKit::mpsl)
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
  add_library(NrfKit::mpsl STATIC IMPORTED GLOBAL)
  set_target_properties(NrfKit::mpsl PROPERTIES
    NRFKIT_NRFXLIB_ROOT "${root}"
    INTERFACE_INCLUDE_DIRECTORIES
      "${root}/mpsl/include;${nrfx};${nrfx}/bsp/stable"
  )
  list(GET paths 0 mpsl_path)
  set_target_properties(NrfKit::mpsl PROPERTIES IMPORTED_LOCATION "${root}/${mpsl_path}")
  add_library(NrfKit::mpsl_fem_common STATIC IMPORTED GLOBAL)
  list(GET paths 1 mpsl_fem_path)
  set_target_properties(NrfKit::mpsl_fem_common PROPERTIES
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
    add_library("NrfKit::sdc_${variant}" STATIC IMPORTED GLOBAL)
    target_link_libraries("NrfKit::sdc_${variant}" INTERFACE NrfKit::mpsl_fem_common NrfKit::mpsl)
    set_target_properties("NrfKit::sdc_${variant}" PROPERTIES
      IMPORTED_LOCATION "${root}/${sdc_path}"
      INTERFACE_INCLUDE_DIRECTORIES
        "${root}/softdevice_controller/include;${root}/mpsl/include;${nrfx};${nrfx}/bsp/stable"
    )
  endforeach()
endfunction()

function(nrfkit_enable_sdc target)
  _nrfkit_require_open_target("${target}" nrfkit_enable_sdc)
  cmake_parse_arguments(PARSE_ARGV 1 ARG "" "VARIANT" "")
  if(ARG_UNPARSED_ARGUMENTS OR NOT ARG_VARIANT)
    message(FATAL_ERROR "nrfkit_enable_sdc requires VARIANT <variant>")
  endif()
  if(NOT ARG_VARIANT MATCHES "^(multirole|peripheral|central)$")
    message(FATAL_ERROR "nrfkit_enable_sdc: unsupported VARIANT '${ARG_VARIANT}'")
  endif()
  get_target_property(existing "${target}" NRFKIT_SDC_VARIANT)
  if(existing)
    message(FATAL_ERROR "nrfkit_enable_sdc: '${target}' already uses '${existing}'")
  endif()
  get_target_property(soc "${target}" NRFKIT_SOC)
  if(NOT soc STREQUAL "nrf54lm20a")
    message(FATAL_ERROR "nrfkit_enable_sdc: '${soc}' is not supported")
  endif()

  nrfkit_claim_resources("${target}" OWNER sdc_mpsl RESOURCES ${_NRFKIT_SDC_RESOURCES})
  _nrfkit_define_nrfxlib_targets()
  nrfkit_enable_nrfx("${target}" DRIVERS cracen)
  target_sources("${target}" PRIVATE
    "${NrfKit_ROOT}/src/wireless/sdc/nrf54l/platform.c"
    "${NrfKit_ROOT}/src/wireless/sdc/nrf54l/hci.c"
  )
  target_include_directories("${target}" PRIVATE
    "${NrfKit_ROOT}/src/wireless/include"
  )
  string(TOUPPER "${ARG_VARIANT}" variant_upper)
  target_compile_definitions("${target}" PRIVATE
    "NRFKIT_SDC_VARIANT_${variant_upper}=1"
  )
  target_link_libraries("${target}" PRIVATE
    "NrfKit::sdc_${ARG_VARIANT}")

  string(MAKE_C_IDENTIFIER "${target}" target_id)
  set(config_dir "${CMAKE_CURRENT_BINARY_DIR}/nrfkit/${target_id}")
  file(MAKE_DIRECTORY "${config_dir}")
  string(REPLACE ";" "\", \"" resources_json "${_NRFKIT_SDC_RESOURCES}")
  get_target_property(root NrfKit::mpsl NRFKIT_NRFXLIB_ROOT)

  _nrfkit_generate_template(sdc-target.json.in "${config_dir}/sdc-target.json")
  set_target_properties("${target}" PROPERTIES NRFKIT_SDC_VARIANT "${ARG_VARIANT}")
endfunction()

function(nrfkit_enable_rram target)
  _nrfkit_require_open_target("${target}" nrfkit_enable_rram)
  get_target_property(enabled "${target}" NRFKIT_RRAM_ENABLED)
  if(enabled OR ARGN)
    message(FATAL_ERROR "nrfkit_enable_rram: enable once without extra arguments")
  endif()
  target_sources("${target}" PRIVATE "${NrfKit_ROOT}/src/runtime/nrfx/rram.c")
  set_target_properties("${target}" PROPERTIES NRFKIT_RRAM_ENABLED TRUE)
endfunction()

function(nrfkit_enable_mpsl_timeslot target)
  _nrfkit_require_open_target("${target}" nrfkit_enable_mpsl_timeslot)
  if(ARGN)
    message(FATAL_ERROR "nrfkit_enable_mpsl_timeslot: unexpected arguments: ${ARGN}")
  endif()
  get_target_property(enabled "${target}" NRFKIT_MPSL_TIMESLOT_ENABLED)
  if(enabled)
    message(FATAL_ERROR
      "nrfkit_enable_mpsl_timeslot: '${target}' is already enabled"
    )
  endif()
  target_sources("${target}" PRIVATE
    "${NrfKit_ROOT}/src/wireless/radio/ownership.c"
    "${NrfKit_ROOT}/src/wireless/radio/nrf54l/radio.c"
    "${NrfKit_ROOT}/src/wireless/timeslot/nrf54l/timeslot.c"
  )
  set_target_properties("${target}" PROPERTIES NRFKIT_MPSL_TIMESLOT_ENABLED TRUE)
endfunction()

function(nrfkit_enable_radio target)
  _nrfkit_require_open_target("${target}" nrfkit_enable_radio)
  cmake_parse_arguments(PARSE_ARGV 1 ARG "" "" "")
  if(ARG_UNPARSED_ARGUMENTS)
    message(FATAL_ERROR "nrfkit_enable_radio: unknown arguments: ${ARG_UNPARSED_ARGUMENTS}")
  endif()
  get_target_property(soc "${target}" NRFKIT_SOC)
  if(NOT soc STREQUAL "nrf54lm20a")
    message(FATAL_ERROR "nrfkit_enable_radio: '${soc}' is not supported")
  endif()
  target_sources("${target}" PRIVATE
    "${NrfKit_ROOT}/src/wireless/radio/ownership.c"
    "${NrfKit_ROOT}/src/wireless/radio/nrf54l/radio.c"
  )
  nrfkit_enable_nrfx("${target}" DRIVERS clock)
  set_target_properties("${target}" PROPERTIES NRFKIT_RADIO_ENABLED TRUE)
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
