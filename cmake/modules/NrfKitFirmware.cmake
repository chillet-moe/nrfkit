# SPDX-License-Identifier: BSD-3-Clause

include_guard(GLOBAL)
include("${CMAKE_CURRENT_LIST_DIR}/NrfKitNrfxlib.cmake")

set(_NRFKIT_NRFX_DRIVERS
  clock power gpio gpiote grtc timer dppi uarte spim twim pwm saadc rramc watchdog
  reset retention cracen
)

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
    set_target_properties("NrfKit::sdc_${variant}" PROPERTIES
      IMPORTED_LOCATION "${root}/${sdc_path}"
      INTERFACE_INCLUDE_DIRECTORIES
        "${root}/softdevice_controller/include;${root}/mpsl/include;${nrfx};${nrfx}/bsp/stable"
    )
  endforeach()
endfunction()

function(nrfkit_enable_sdc target)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "nrfkit_enable_sdc: unknown target '${target}'")
  endif()
  get_target_property(configured "${target}" NRFKIT_CONFIGURED)
  if(NOT configured)
    message(FATAL_ERROR "nrfkit_enable_sdc: configure '${target}' first")
  endif()
  get_target_property(finalized "${target}" NRFKIT_FINALIZED)
  if(finalized)
    message(FATAL_ERROR "nrfkit_enable_sdc: '${target}' is already finalized")
  endif()
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
    "${NrfKit_ROOT}/softdevice/sdc/nrf54l/platform.c"
    "${NrfKit_ROOT}/softdevice/sdc/nrf54l/hci.c"
  )
  string(TOUPPER "${ARG_VARIANT}" variant_upper)
  target_compile_definitions("${target}" PRIVATE
    "NRFKIT_SDC_VARIANT_${variant_upper}=1"
  )
  target_link_libraries("${target}" PRIVATE
    "NrfKit::sdc_${ARG_VARIANT}" NrfKit::mpsl_fem_common NrfKit::mpsl)

  string(MAKE_C_IDENTIFIER "${target}" target_id)
  set(config_dir "${CMAKE_CURRENT_BINARY_DIR}/nrfkit/${target_id}")
  file(MAKE_DIRECTORY "${config_dir}")
  string(REPLACE ";" "\", \"" resources_json "${_NRFKIT_SDC_RESOURCES}")
  get_target_property(root NrfKit::mpsl NRFKIT_NRFXLIB_ROOT)
  string(CONCAT sdc_target_content
    "{\n"
    "  \"schema\": \"nrfkit-sdc-target/v1\",\n"
    "  \"target\": \"${target}\",\n"
    "  \"variant\": \"${ARG_VARIANT}\",\n"
    "  \"security_domain\": \"secure\",\n"
    "  \"float_abi\": \"hard-float\",\n"
    "  \"timeslot\": $<IF:$<BOOL:$<TARGET_PROPERTY:${target},NRFKIT_MPSL_TIMESLOT_ENABLED>>,true,false>,\n"
    "  \"archives\": [\"${root}/mpsl/lib/nrf54lm/hard-float/libmpsl.a\", \"${root}/mpsl/fem/common/lib/nrf54lm/hard-float/libmpsl_fem_common.a\", \"${root}/softdevice_controller/lib/nrf54lm/hard-float/libsoftdevice_controller_${ARG_VARIANT}.a\"],\n"
    "  \"resources\": [\"${resources_json}\"]\n"
    "}\n"
  )
  file(GENERATE OUTPUT "${config_dir}/sdc-target.json" CONTENT "${sdc_target_content}")
  set_target_properties("${target}" PROPERTIES NRFKIT_SDC_VARIANT "${ARG_VARIANT}")
endfunction()

function(nrfkit_enable_mpsl_timeslot target)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "nrfkit_enable_mpsl_timeslot: unknown target '${target}'")
  endif()
  get_target_property(variant "${target}" NRFKIT_SDC_VARIANT)
  if(NOT variant)
    message(FATAL_ERROR
      "nrfkit_enable_mpsl_timeslot: enable SDC on '${target}' first"
    )
  endif()
  get_target_property(finalized "${target}" NRFKIT_FINALIZED)
  if(finalized)
    message(FATAL_ERROR
      "nrfkit_enable_mpsl_timeslot: '${target}' is already finalized"
    )
  endif()
  get_target_property(enabled "${target}" NRFKIT_MPSL_TIMESLOT_ENABLED)
  if(enabled)
    message(FATAL_ERROR
      "nrfkit_enable_mpsl_timeslot: '${target}' is already enabled"
    )
  endif()
  target_sources("${target}" PRIVATE
    "${NrfKit_ROOT}/radio/ownership.c"
    "${NrfKit_ROOT}/radio/nrf54l/radio.c"
    "${NrfKit_ROOT}/radio/timeslot/nrf54l/timeslot.c"
  )
  set_target_properties("${target}" PROPERTIES NRFKIT_MPSL_TIMESLOT_ENABLED TRUE)
endfunction()

function(_nrfkit_prepare_nrfx out_var)
  set(nrfx_commit "1b7bedb5c7f379a3ec3ece851796e94d7e5d0b2c")
  set(nrfx_source "${NrfKit_ROOT}/external/nrfx")
  if(NOT EXISTS "${nrfx_source}/nrfx.h" OR
      NOT EXISTS "${nrfx_source}/bsp/stable/mdk/nrf54l/system_nrf54l.c")
    message(FATAL_ERROR
      "NrfKit requires the nrfx ${nrfx_commit} submodule. "
      "Initialize external/nrfx before configuring; NrfKit never downloads it during configure."
    )
  endif()

  if(NOT DEFINED NRFKIT_VENDOR_CACHE_ROOT)
    set(NRFKIT_VENDOR_CACHE_ROOT
      "${CMAKE_BINARY_DIR}/_shared/nrfkit"
      CACHE PATH "Shared cache for immutable vendor-library views"
    )
  endif()
  get_filename_component(cache_root "${NRFKIT_VENDOR_CACHE_ROOT}" ABSOLUTE
    BASE_DIR "${CMAKE_BINARY_DIR}")
  set(prepared "${cache_root}/nrfx-${nrfx_commit}")
  set(marker "${prepared}/.nrfkit-prepared")
  set(patch_dir "${NrfKit_ROOT}/patches/nrfx")
  file(GLOB patches CONFIGURE_DEPENDS "${patch_dir}/*.patch")
  list(SORT patches)
  set(state "nrfx=${nrfx_commit}\n")
  foreach(patch IN LISTS patches)
    file(SHA256 "${patch}" patch_sha256)
    get_filename_component(patch_name "${patch}" NAME)
    string(APPEND state "patch=${patch_name}:${patch_sha256}\n")
  endforeach()
  string(SHA256 state_hash "${state}")

  file(MAKE_DIRECTORY "${cache_root}")
  file(LOCK "${cache_root}/.prepare-nrfx.lock" GUARD FUNCTION TIMEOUT 600
    RESULT_VARIABLE lock_result)
  if(lock_result)
    message(FATAL_ERROR "Could not lock nrfx preparation: ${lock_result}")
  endif()
  set(rebuild TRUE)
  if(EXISTS "${marker}")
    file(READ "${marker}" current_state)
    if(current_state STREQUAL "${state_hash}\n")
      set(rebuild FALSE)
    endif()
  endif()
  if(rebuild)
    set(staging "${prepared}.staging")
    file(REMOVE_RECURSE "${staging}")
    file(MAKE_DIRECTORY "${staging}")
    file(COPY "${nrfx_source}/" DESTINATION "${staging}" PATTERN ".git" EXCLUDE)
    if(patches)
      find_program(NRFKIT_GIT_EXECUTABLE git REQUIRED)
      foreach(patch IN LISTS patches)
        execute_process(
          COMMAND "${NRFKIT_GIT_EXECUTABLE}" apply --whitespace=nowarn "${patch}"
          WORKING_DIRECTORY "${staging}"
          RESULT_VARIABLE patch_result
          OUTPUT_VARIABLE patch_stdout
          ERROR_VARIABLE patch_stderr
        )
        if(NOT patch_result EQUAL 0)
          message(FATAL_ERROR
            "Could not apply nrfx patch ${patch}:\n${patch_stdout}${patch_stderr}"
          )
        endif()
      endforeach()
    endif()
    file(WRITE "${staging}/.nrfkit-prepared" "${state_hash}\n")
    file(REMOVE_RECURSE "${prepared}")
    file(RENAME "${staging}" "${prepared}")
  endif()
  set(${out_var} "${prepared}" PARENT_SCOPE)
endfunction()

function(nrfkit_enable_nrfx target)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "nrfkit_enable_nrfx: unknown target '${target}'")
  endif()
  get_target_property(configured "${target}" NRFKIT_CONFIGURED)
  if(NOT configured)
    message(FATAL_ERROR "nrfkit_enable_nrfx: configure '${target}' first")
  endif()
  get_target_property(finalized "${target}" NRFKIT_FINALIZED)
  if(finalized)
    message(FATAL_ERROR "nrfkit_enable_nrfx: '${target}' is already finalized")
  endif()

  cmake_parse_arguments(PARSE_ARGV 1 ARG "" "" "DRIVERS")
  if(ARG_UNPARSED_ARGUMENTS)
    message(FATAL_ERROR "nrfkit_enable_nrfx: unknown arguments: ${ARG_UNPARSED_ARGUMENTS}")
  endif()
  if(NOT ARG_DRIVERS)
    message(FATAL_ERROR "nrfkit_enable_nrfx: DRIVERS must not be empty")
  endif()
  foreach(driver IN LISTS ARG_DRIVERS)
    if(NOT driver IN_LIST _NRFKIT_NRFX_DRIVERS)
      message(FATAL_ERROR
        "nrfkit_enable_nrfx: unsupported driver '${driver}'; supported: ${_NRFKIT_NRFX_DRIVERS}"
      )
    endif()
  endforeach()
  get_target_property(drivers "${target}" NRFKIT_NRFX_DRIVERS)
  if(NOT drivers)
    set(drivers "")
  endif()
  list(APPEND drivers ${ARG_DRIVERS})
  list(REMOVE_DUPLICATES drivers)
  set_target_properties("${target}" PROPERTIES NRFKIT_NRFX_DRIVERS "${drivers}")
endfunction()

function(nrfkit_enable_radio target)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "nrfkit_enable_radio: unknown target '${target}'")
  endif()
  get_target_property(configured "${target}" NRFKIT_CONFIGURED)
  if(NOT configured)
    message(FATAL_ERROR "nrfkit_enable_radio: configure '${target}' first")
  endif()
  get_target_property(finalized "${target}" NRFKIT_FINALIZED)
  if(finalized)
    message(FATAL_ERROR "nrfkit_enable_radio: '${target}' is already finalized")
  endif()
  cmake_parse_arguments(PARSE_ARGV 1 ARG "" "" "")
  if(ARG_UNPARSED_ARGUMENTS)
    message(FATAL_ERROR "nrfkit_enable_radio: unknown arguments: ${ARG_UNPARSED_ARGUMENTS}")
  endif()
  get_target_property(soc "${target}" NRFKIT_SOC)
  if(NOT soc STREQUAL "nrf54lm20a")
    message(FATAL_ERROR "nrfkit_enable_radio: '${soc}' is not supported")
  endif()
  target_sources("${target}" PRIVATE
    "${NrfKit_ROOT}/radio/ownership.c"
    "${NrfKit_ROOT}/radio/nrf54l/radio.c"
  )
  nrfkit_enable_nrfx("${target}" DRIVERS clock)
  set_target_properties("${target}" PROPERTIES NRFKIT_RADIO_ENABLED TRUE)
endfunction()

function(_nrfkit_prepare_nrf_bm_hids nrf_bm_root out_var)
  set(source_files
    boards/nordic/bm_nrf54lm20dk/init.c
    boards/nordic/bm_nrf54lm20dk/include/board-config.h
    samples/bluetooth/ble_hids_mouse/src/main.c
    subsys/softdevice_handler/irq_connect.c
    subsys/softdevice_handler/irq_connect.h
    subsys/softdevice_handler/irq_forward.s
    subsys/softdevice_handler/nrf_sdh.c
    subsys/softdevice_handler/nrf_sdh_ble.c
    subsys/softdevice_handler/nrf_sdh_info.c
    subsys/softdevice_handler/nrf_sdh_soc.c
    subsys/softdevice_handler/rand_seed.c
    lib/bluetooth/ble_adv/ble_adv.c
    lib/bluetooth/ble_adv/ble_adv_data.c
    lib/bluetooth/ble_conn_params/att_mtu.c
    lib/bluetooth/ble_conn_params/conn_param.c
    lib/bluetooth/ble_conn_params/data_length.c
    lib/bluetooth/ble_conn_params/event.c
    lib/bluetooth/ble_conn_params/phy_mode.c
    lib/bluetooth/ble_qwr/ble_qwr.c
    lib/bluetooth/peer_manager/peer_manager.c
    lib/bluetooth/peer_manager/nrf_strerror.c
    lib/bluetooth/peer_manager/modules/conn_state.c
    lib/bluetooth/peer_manager/modules/gatt_cache_manager.c
    lib/bluetooth/peer_manager/modules/gatts_cache_manager.c
    lib/bluetooth/peer_manager/modules/id_manager.c
    lib/bluetooth/peer_manager/modules/nrf_ble_lesc.c
    lib/bluetooth/peer_manager/modules/peer_data_storage.c
    lib/bluetooth/peer_manager/modules/peer_database.c
    lib/bluetooth/peer_manager/modules/peer_id.c
    lib/bluetooth/peer_manager/modules/peer_manager_handler.c
    lib/bluetooth/peer_manager/modules/pm_buffer.c
    lib/bluetooth/peer_manager/modules/security_dispatcher.c
    lib/bluetooth/peer_manager/modules/security_manager.c
    lib/bm_buttons/bm_buttons.c
    lib/bm_gpiote/gpiote.c
    lib/bm_timer/bm_timer.c
    subsys/storage/bm_storage/bm_storage.c
    subsys/storage/bm_storage/sd/bm_storage_sd.c
    subsys/fs/bm_zms/bm_zms.c
    subsys/fs/bm_zms/bm_zms_priv.h
    subsys/bluetooth/services/ble_bas/bas.c
    subsys/bluetooth/services/ble_dis/dis.c
    subsys/bluetooth/services/ble_hids/hids.c
  )
  file(GLOB_RECURSE public_headers CONFIGURE_DEPENDS
    RELATIVE "${nrf_bm_root}" "${nrf_bm_root}/include/bm/*.h")
  file(GLOB_RECURSE peer_manager_headers CONFIGURE_DEPENDS
    RELATIVE "${nrf_bm_root}"
    "${nrf_bm_root}/lib/bluetooth/peer_manager/include/*.h")
  list(APPEND source_files ${public_headers} ${peer_manager_headers})
  list(REMOVE_DUPLICATES source_files)
  list(SORT source_files)

  set(state
    "nrf-bm=51484143c09199e19bccc16fa3b437f7a502a72b\nadapter=9\n")
  foreach(relative IN LISTS source_files)
    set(source "${nrf_bm_root}/${relative}")
    if(NOT EXISTS "${source}")
      message(FATAL_ERROR "Locked nRF-BM HIDS input is missing: ${source}")
    endif()
    file(SHA256 "${source}" source_sha256)
    string(APPEND state "${relative}:${source_sha256}\n")
  endforeach()
  string(SHA256 state_hash "${state}")

  if(NOT DEFINED NRFKIT_VENDOR_CACHE_ROOT)
    set(NRFKIT_VENDOR_CACHE_ROOT "${CMAKE_BINARY_DIR}/_shared/nrfkit"
      CACHE PATH "Shared cache for immutable vendor-library views")
  endif()
  get_filename_component(cache_root "${NRFKIT_VENDOR_CACHE_ROOT}" ABSOLUTE
    BASE_DIR "${CMAKE_BINARY_DIR}")
  set(prepared "${cache_root}/nrf-bm-hids-51484143-${state_hash}")
  set(marker "${prepared}/.nrfkit-prepared")
  file(MAKE_DIRECTORY "${cache_root}")
  file(LOCK "${cache_root}/.prepare-nrf-bm-hids.lock" GUARD FUNCTION TIMEOUT 600
    RESULT_VARIABLE lock_result)
  if(lock_result)
    message(FATAL_ERROR "Could not lock nRF-BM HIDS preparation: ${lock_result}")
  endif()
  set(rebuild TRUE)
  if(EXISTS "${marker}")
    file(READ "${marker}" current_state)
    if(current_state STREQUAL "${state_hash}\n")
      set(rebuild FALSE)
    endif()
  endif()
  if(rebuild)
    set(staging "${prepared}.staging")
    file(REMOVE_RECURSE "${staging}")
    foreach(relative IN LISTS source_files)
      set(source "${nrf_bm_root}/${relative}")
      set(destination "${staging}/${relative}")
      get_filename_component(destination_dir "${destination}" DIRECTORY)
      file(MAKE_DIRECTORY "${destination_dir}")
      file(READ "${source}" contents)
      string(REGEX REPLACE "#[ \t]*include[ \t]*<zephyr/[^>]+>"
        "#include <nrfkit/bm_port.h>" contents "${contents}")
      string(REPLACE "#include <psa/crypto.h>"
        "#include <nrfkit/bm_crypto.h>" contents "${contents}")
      string(REPLACE "#include <bm/bm_irq.h>"
        "#include <nrfkit/bm_port.h>" contents "${contents}")
      string(REPLACE "#include <bm/bm_scheduler.h>"
        "#include <nrfkit/bm_port.h>" contents "${contents}")
      string(REPLACE "PRIO_LEVEL_IS_VALID(_prio);" "" contents "${contents}")
      string(REPLACE "PRIO_LEVEL_ORD(_prio)" "NRFKIT_BM_PRIO(_prio)"
        contents "${contents}")
      if(relative STREQUAL "subsys/softdevice_handler/irq_forward.s")
        string(REPLACE ".balign\n" ".balign 4\n" contents "${contents}")
      elseif(relative STREQUAL "subsys/softdevice_handler/nrf_sdh.c")
        # The MDK vector points directly at SD_EVT_IRQHandler. Zephyr instead
        # points it at an IRQ_DIRECT_CONNECT wrapper carrying Clang's Cortex-M
        # interrupt calling convention. Preserve that ABI at our static vector
        # boundary without importing Zephyr's dynamic interrupt table.
        string(REPLACE "void SD_EVT_IRQHandler(void)"
          "static void nrfkit_sd_evt_dispatch(void)"
          contents "${contents}")
        string(REPLACE "ISR_DIRECT_DECLARE(sd_direct_isr)"
          "__attribute__((interrupt(\"IRQ\"))) void SD_EVT_IRQHandler(void)"
          contents "${contents}")
        string(REPLACE "SD_EVT_IRQHandler();\n\treturn 0;"
          "nrfkit_sd_evt_dispatch();" contents "${contents}")
        string(REPLACE "\t\t\t      sd_direct_isr, 0);"
          "\t\t\t      SD_EVT_IRQHandler, 0);" contents "${contents}")
      elseif(relative STREQUAL "samples/bluetooth/ble_hids_mouse/src/main.c")
        # The official GCC build accepts this enum-compatible callback with a
        # warning.  Clang correctly rejects the mismatched function-pointer
        # type, so make only the parameter type explicit; handler logic and
        # registration remain the official implementation.
        string(REPLACE
          "static void button_handler(uint8_t pin, uint8_t action)"
          "static void button_handler(uint8_t pin, enum bm_buttons_evt_type action)"
          contents "${contents}")
      endif()
      if(relative MATCHES "\\.c$")
        string(PREPEND contents "#include <nrfkit/bm_port.h>\n")
      endif()
      file(WRITE "${destination}" "${contents}")
    endforeach()
    file(WRITE "${staging}/.nrfkit-prepared" "${state_hash}\n")
    file(REMOVE_RECURSE "${prepared}")
    file(RENAME "${staging}" "${prepared}")
  endif()
  set(${out_var} "${prepared}" PARENT_SCOPE)
endfunction()

function(_nrfkit_enable_s115_baseline target)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "nrfkit_enable_s115: unknown target '${target}'")
  endif()
  get_target_property(configured "${target}" NRFKIT_CONFIGURED)
  if(NOT configured)
    message(FATAL_ERROR "nrfkit_enable_s115: configure '${target}' first")
  endif()
  get_target_property(finalized "${target}" NRFKIT_FINALIZED)
  if(finalized)
    message(FATAL_ERROR "nrfkit_enable_s115: '${target}' is already finalized")
  endif()
  cmake_parse_arguments(PARSE_ARGV 1 ARG ""
    "VERSION;SOURCE_DIR;OBERON_DIR;NRF_BM_DIR" "")
  if(ARG_UNPARSED_ARGUMENTS)
    message(FATAL_ERROR "nrfkit_enable_s115: unknown arguments: ${ARG_UNPARSED_ARGUMENTS}")
  endif()
  if(NOT ARG_VERSION STREQUAL "10.0.1")
    message(FATAL_ERROR "nrfkit_enable_s115: supported VERSION is 10.0.1")
  endif()
  if(NOT ARG_SOURCE_DIR)
    if(NRF_SOFTDEVICE_ROOT)
      set(ARG_SOURCE_DIR "${NRF_SOFTDEVICE_ROOT}")
    else()
      message(FATAL_ERROR
        "nrfkit_enable_s115 requires SOURCE_DIR or NRF_SOFTDEVICE_ROOT pointing to "
        "the official nrf54lm/s115 directory from NCS Bare Metal v2.0.1"
      )
    endif()
  endif()
  if(NOT ARG_OBERON_DIR)
    if(NRF_OBERON_ROOT)
      set(ARG_OBERON_DIR "${NRF_OBERON_ROOT}")
    else()
      message(FATAL_ERROR
        "nrfkit_enable_s115 requires OBERON_DIR or NRF_OBERON_ROOT pointing to "
        "the official nrf_oberon 3.0.19 directory from NCS Bare Metal v2.0.1"
      )
    endif()
  endif()
  get_filename_component(s115 "${ARG_SOURCE_DIR}" ABSOLUTE
    BASE_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
  get_filename_component(oberon "${ARG_OBERON_DIR}" ABSOLUTE
    BASE_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
  set(api "${s115}/s115_API/include")
  set(hex "${s115}/s115_nrf54lm20_10.0.1_softdevice.hex")
  get_filename_component(nrf_bm_root "${s115}/../../../.." ABSOLUTE)
  if(ARG_NRF_BM_DIR)
    get_filename_component(nrf_bm_root "${ARG_NRF_BM_DIR}" ABSOLUTE
      BASE_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
  endif()
  set(sdh_dir "${nrf_bm_root}/subsys/softdevice_handler")
  set(oberon_archive
    "${oberon}/lib/cortex-m33/soft-float/liboberon_3.0.19.a")
  set(required_files
    "${hex}|c2b5bcf2b436e11daa9a85e9dca12060052244c2eec50032bf54d87a4a77c3a2"
    "${s115}/s115_10.0.1_license-agreement.txt|7954ebb6167400e1b4232a513ed7cf8a9e3dcddf68297ca5f2d979f48afed382"
    "${s115}/s115_10.0.1_license-attribution.txt|7f1899283abee89a08981a079782eefe7de928cca4df743f6731d818bfdca614"
    "${s115}/s115_10.0.1_release-notes.pdf|f55e74be9c8255199139135f2c4bf25d762b4be2ff366a0e94522914814ccdb9"
    "${s115}/manifest.yaml|e58570a17eb1fb33403350d33eb4cd6ffc90597f63b5e2ba81ea32e2eda5f7a6"
    "${api}/ble.h|b25e1e7640fc7b8c8d4245a213c3dc86721a9cd604e907c069f07a765f56fb60"
    "${api}/ble_gap.h|5293162db0e25711a0ea2a6b9cdfb198931778c2a7b4d16b6d746a3cc5df6239"
    "${api}/ble_gatts.h|8e180f22ed53f0723a7731b6100d89bbfc111ba4dbcb00c80ddd252394a82d72"
    "${api}/nrf_sdm.h|1e051c429caf1673132c61570976c30b832bce98170b4dd610f39e4929320e0e"
    "${api}/nrf_soc.h|e4439569af7a2245e04d00f05d0c7b06565b078f25f946494d8fdae20f6f64ec"
    "${sdh_dir}/irq_forward.s|5f35d0be21aaf18f3bb4645e2bac28550d9ddfa94c11e50898ff16f3a31af2a1"
    "${oberon}/license.txt|a5ec38d8e20eaee2cbcf5f5dc97211a401fd5ac22af0bc550979528dfb78dcf0"
    "${oberon}/include/ocrypto_ecdh_p256.h|8874869b5d40fa6840fde1e4ea959c338fa49a7a9de50fd8086f9a4785c6f3d1"
    "${oberon}/include/ocrypto_types_p256.h|d9364820557d2a4b8b924d3633bccee270cfb5888cb8a33096ae898b3663036b"
    "${oberon_archive}|d37fac18acbc55313c4a5bd6323f513ce907418cb0a71a6a7ed28d3d9285f194"
  )
  foreach(entry IN LISTS required_files)
    string(REPLACE "|" ";" fields "${entry}")
    list(GET fields 0 path)
    list(GET fields 1 expected_sha256)
    if(NOT EXISTS "${path}")
      message(FATAL_ERROR "nrfkit_enable_s115: official input is missing: ${path}")
    endif()
    file(SHA256 "${path}" actual_sha256)
    if(NOT actual_sha256 STREQUAL expected_sha256)
      message(FATAL_ERROR "nrfkit_enable_s115: hash mismatch for ${path}")
    endif()
  endforeach()

  get_target_property(soc "${target}" NRFKIT_SOC)
  if(NOT soc STREQUAL "nrf54lm20a")
    message(FATAL_ERROR "nrfkit_enable_s115: '${soc}' is not supported")
  endif()
  get_target_property(board "${target}" NRFKIT_BOARD)
  if(NOT board STREQUAL "nrf54lm20dk")
    message(FATAL_ERROR "nrfkit_enable_s115: '${board}' is not supported")
  endif()
  get_target_property(radio_enabled "${target}" NRFKIT_RADIO_ENABLED)
  if(radio_enabled)
    message(FATAL_ERROR
      "nrfkit_enable_s115: proprietary RADIO and S115 cannot be enabled concurrently"
    )
  endif()

  set(standalone_linker
    "-T${NrfKit_ROOT}/linker/layouts/nrf54lm20a-cpuapp-standalone.ld")
  get_target_property(link_options "${target}" LINK_OPTIONS)
  list(REMOVE_ITEM link_options "${standalone_linker}")
  set(s115_linker
    "${NrfKit_ROOT}/linker/layouts/nrf54lm20a-cpuapp-s115-10.0.1.ld")
  list(APPEND link_options "-T${s115_linker}")
  set_target_properties("${target}" PROPERTIES LINK_OPTIONS "${link_options}")
  set_property(TARGET "${target}" APPEND PROPERTY LINK_DEPENDS "${s115_linker};${hex}")
  target_include_directories("${target}" PRIVATE
    "${NrfKit_ROOT}/softdevice/nrf54l"
    "${api}"
    "${oberon}/include"
  )
  target_compile_options("${target}" PRIVATE
    $<$<COMPILE_LANGUAGE:C>:-include;${NrfKit_ROOT}/config/nrf-bm-hids-s115-autoconf.h>
  )
  # The locked official nRF-BM S115 oracle is built with CONFIG_FPU disabled.
  # Keep the complete S115 target on the same exception-frame and calling ABI.
  if(CMAKE_C_COMPILER_ID STREQUAL "GNU")
    target_compile_options("${target}" PRIVATE
      $<$<COMPILE_LANGUAGE:C,CXX,ASM>:-mfpu=auto;-mfloat-abi=soft>
    )
    target_link_options("${target}" PRIVATE -mfpu=auto -mfloat-abi=soft)
  else()
    target_compile_options("${target}" PRIVATE
      $<$<COMPILE_LANGUAGE:C,CXX,ASM>:-mfloat-abi=soft>
    )
    target_link_options("${target}" PRIVATE -mfloat-abi=soft)
  endif()
  target_link_libraries("${target}" PRIVATE "${oberon_archive}")
  target_sources("${target}" PRIVATE
    "${NrfKit_ROOT}/boards/nrf54lm20dk/init.c"
    "${NrfKit_ROOT}/radio/ownership.c")
  _nrfkit_prepare_nrf_bm_hids("${nrf_bm_root}" prepared_hids)
    set(official_sources
      boards/nordic/bm_nrf54lm20dk/init.c
      samples/bluetooth/ble_hids_mouse/src/main.c
      subsys/softdevice_handler/irq_connect.c
      subsys/softdevice_handler/nrf_sdh.c
      subsys/softdevice_handler/nrf_sdh_ble.c
      subsys/softdevice_handler/nrf_sdh_info.c
      subsys/softdevice_handler/nrf_sdh_soc.c
      subsys/softdevice_handler/rand_seed.c
      lib/bluetooth/ble_adv/ble_adv.c
      lib/bluetooth/ble_adv/ble_adv_data.c
      lib/bluetooth/ble_conn_params/att_mtu.c
      lib/bluetooth/ble_conn_params/conn_param.c
      lib/bluetooth/ble_conn_params/data_length.c
      lib/bluetooth/ble_conn_params/event.c
      lib/bluetooth/ble_conn_params/phy_mode.c
      lib/bluetooth/ble_qwr/ble_qwr.c
      lib/bluetooth/peer_manager/peer_manager.c
      lib/bluetooth/peer_manager/nrf_strerror.c
      lib/bluetooth/peer_manager/modules/conn_state.c
      lib/bluetooth/peer_manager/modules/gatt_cache_manager.c
      lib/bluetooth/peer_manager/modules/gatts_cache_manager.c
      lib/bluetooth/peer_manager/modules/id_manager.c
      lib/bluetooth/peer_manager/modules/nrf_ble_lesc.c
      lib/bluetooth/peer_manager/modules/peer_data_storage.c
      lib/bluetooth/peer_manager/modules/peer_database.c
      lib/bluetooth/peer_manager/modules/peer_id.c
      lib/bluetooth/peer_manager/modules/peer_manager_handler.c
      lib/bluetooth/peer_manager/modules/pm_buffer.c
      lib/bluetooth/peer_manager/modules/security_dispatcher.c
      lib/bluetooth/peer_manager/modules/security_manager.c
      lib/bm_buttons/bm_buttons.c
      lib/bm_gpiote/gpiote.c
      lib/bm_timer/bm_timer.c
      subsys/storage/bm_storage/bm_storage.c
      subsys/storage/bm_storage/sd/bm_storage_sd.c
      subsys/fs/bm_zms/bm_zms.c
      subsys/bluetooth/services/ble_bas/bas.c
      subsys/bluetooth/services/ble_dis/dis.c
      subsys/bluetooth/services/ble_hids/hids.c)
    list(TRANSFORM official_sources PREPEND "${prepared_hids}/")
    target_sources("${target}" PRIVATE ${official_sources}
      "${NrfKit_ROOT}/softdevice/nrf54l/bm_port.c"
      "${NrfKit_ROOT}/softdevice/nrf54l/bm_crypto.c"
      "${prepared_hids}/subsys/softdevice_handler/irq_forward.s")
    target_include_directories("${target}" PRIVATE
      "${prepared_hids}/include"
      "${prepared_hids}/boards/nordic/bm_nrf54lm20dk/include"
      "${prepared_hids}/lib/bluetooth/peer_manager/include"
      "${prepared_hids}/subsys/fs/bm_zms")
    # Every CONFIG_ value comes byte-for-byte from the official generated
    # autoconf header.  Do not add approximate hand-transcribed definitions.
  set(irq_forward "${prepared_hids}/subsys/softdevice_handler/irq_forward.s")
  set_property(SOURCE "${irq_forward}" TARGET_DIRECTORY "${target}"
    APPEND PROPERTY COMPILE_OPTIONS -x assembler-with-cpp)
  nrfkit_enable_nrfx("${target}" DRIVERS clock power cracen gpiote)
  target_compile_definitions("${target}" PRIVATE
    NRFX_GPIOTE20_ENABLED=1 NRFX_GPIOTE30_ENABLED=1)
  target_compile_definitions("${target}" PRIVATE NRFKIT_S115_10_0_1=1)
  set_target_properties("${target}" PROPERTIES
    NRFKIT_SOFTDEVICE "s115"
    NRFKIT_SOFTDEVICE_VERSION "10.0.1"
    NRFKIT_SOFTDEVICE_HEX "${hex}"
    NRFKIT_LAYOUT "s115-10.0.1"
  )
  add_custom_command(TARGET "${target}" POST_BUILD
    COMMAND "${CMAKE_COMMAND}"
      "-DNRFKIT_MAP_FILE=$<TARGET_FILE_DIR:${target}>/$<TARGET_FILE_BASE_NAME:${target}>.map"
      -P "${NrfKit_ROOT}/cmake/VerifyNrfBmInitOrder.cmake"
    VERBATIM
  )
endfunction()

function(nrfkit_enable_usb_device target)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "nrfkit_enable_usb_device: unknown target '${target}'")
  endif()
  get_target_property(configured "${target}" NRFKIT_CONFIGURED)
  if(NOT configured)
    message(FATAL_ERROR "nrfkit_enable_usb_device: configure '${target}' first")
  endif()
  get_target_property(finalized "${target}" NRFKIT_FINALIZED)
  if(finalized)
    message(FATAL_ERROR "nrfkit_enable_usb_device: '${target}' is already finalized")
  endif()

  cmake_parse_arguments(PARSE_ARGV 1 ARG "" "STACK;SOURCE_DIR" "CLASSES")
  if(ARG_UNPARSED_ARGUMENTS)
    message(FATAL_ERROR
      "nrfkit_enable_usb_device: unknown arguments: ${ARG_UNPARSED_ARGUMENTS}"
    )
  endif()
  if(NOT ARG_STACK)
    set(ARG_STACK cherryusb)
  endif()
  if(NOT ARG_STACK STREQUAL "cherryusb")
    message(FATAL_ERROR
      "nrfkit_enable_usb_device: unsupported STACK '${ARG_STACK}'; supported: cherryusb"
    )
  endif()
  foreach(class IN LISTS ARG_CLASSES)
    if(NOT class STREQUAL "hid")
      message(FATAL_ERROR
        "nrfkit_enable_usb_device: unsupported CLASS '${class}'; supported: hid"
      )
    endif()
  endforeach()
  list(REMOVE_DUPLICATES ARG_CLASSES)
  get_target_property(soc "${target}" NRFKIT_SOC)
  if(NOT soc STREQUAL "nrf54lm20a")
    message(FATAL_ERROR
      "nrfkit_enable_usb_device: '${soc}' has no supported NrfKit USBHS port"
    )
  endif()
  if(ARG_SOURCE_DIR)
    get_filename_component(cherryusb "${ARG_SOURCE_DIR}" ABSOLUTE
      BASE_DIR "${CMAKE_CURRENT_SOURCE_DIR}"
    )
  else()
    set(cherryusb "${NrfKit_ROOT}/external/cherryusb")
  endif()
  foreach(required IN ITEMS
      "${cherryusb}/core/usbd_core.c"
      "${cherryusb}/port/dwc2/usb_dc_dwc2.c"
      "${cherryusb}/LICENSE")
    if(NOT EXISTS "${required}")
      message(FATAL_ERROR
        "nrfkit_enable_usb_device: CherryUSB source tree is incomplete: ${required}"
      )
    endif()
  endforeach()
  if("hid" IN_LIST ARG_CLASSES AND
      NOT EXISTS "${cherryusb}/class/hid/usbd_hid.c")
    message(FATAL_ERROR
      "nrfkit_enable_usb_device: CherryUSB HID class source is missing"
    )
  endif()

  string(MAKE_C_IDENTIFIER "${target}" target_id)
  set(config_dir "${CMAKE_CURRENT_BINARY_DIR}/nrfkit/${target_id}/usb")
  file(MAKE_DIRECTORY "${config_dir}")
  file(WRITE "${config_dir}/usb_config.h"
    "/* Generated by nrfkit; target-local and not for source control. */\n"
    "#ifndef NRFKIT_GENERATED_CHERRYUSB_CONFIG_H\n"
    "#define NRFKIT_GENERATED_CHERRYUSB_CONFIG_H\n"
    "#define CONFIG_USB_PRINTF(...) ((void)0)\n"
    "#define CONFIG_USB_DBG_LEVEL 0\n"
    "#define CONFIG_USB_ALIGN_SIZE 4\n"
    "#define USB_NOCACHE_RAM_SECTION\n"
    "#define CONFIG_USBDEV_MAX_BUS 1\n"
    "#define CONFIG_USBDEV_REQUEST_BUFFER_LEN 512\n"
    "#define CONFIG_USB_DWC2_DMA_ENABLE\n"
    "#define CONFIG_USB_HS\n"
    "#endif\n"
  )
  target_include_directories("${target}" PRIVATE
    "${config_dir}"
    "${cherryusb}/common"
    "${cherryusb}/core"
    "${cherryusb}/port/dwc2"
  )
  target_sources("${target}" PRIVATE
    "${cherryusb}/core/usbd_core.c"
    "${cherryusb}/port/dwc2/usb_dc_dwc2.c"
    "${NrfKit_ROOT}/usb/nrf54l/usb_glue_dwc2.c"
  )
  if("hid" IN_LIST ARG_CLASSES)
    target_include_directories("${target}" PRIVATE "${cherryusb}/class/hid")
    target_sources("${target}" PRIVATE "${cherryusb}/class/hid/usbd_hid.c")
  endif()
  set_target_properties("${target}" PROPERTIES
    NRFKIT_USB_DEVICE_STACK cherryusb
    NRFKIT_USB_DEVICE_SOURCE "${cherryusb}"
    NRFKIT_USB_DEVICE_CLASSES "${ARG_CLASSES}"
    NRFKIT_NRFX_HEADERS_REQUIRED TRUE
  )
endfunction()

function(nrfkit_claim_resources target)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "nrfkit_claim_resources: unknown target '${target}'")
  endif()
  get_target_property(configured "${target}" NRFKIT_CONFIGURED)
  if(NOT configured)
    message(FATAL_ERROR "nrfkit_claim_resources: configure '${target}' first")
  endif()
  get_target_property(finalized "${target}" NRFKIT_FINALIZED)
  if(finalized)
    message(FATAL_ERROR "nrfkit_claim_resources: '${target}' is already finalized")
  endif()
  cmake_parse_arguments(PARSE_ARGV 1 ARG "" "OWNER" "RESOURCES")
  if(ARG_UNPARSED_ARGUMENTS OR NOT ARG_OWNER OR NOT ARG_RESOURCES)
    message(FATAL_ERROR
      "nrfkit_claim_resources requires OWNER <name> RESOURCES <resource>..."
    )
  endif()

  get_target_property(resource_keys "${target}" NRFKIT_RESOURCE_KEYS)
  if(NOT resource_keys)
    set(resource_keys "")
  endif()
  foreach(resource IN LISTS ARG_RESOURCES)
    if(NOT resource MATCHES
        "^(dppi(00|10|20|30)\\.(channel\\.([0-9]+)|group\\.([0-9]+))|ppib(00|10|11|20|21)\\.channel\\.([0-9]+)|gpiote(20|30)\\.channel\\.([0-9]+)|grtc\\.channel\\.([0-9]+)|timer(00|10|20|21|22|23|24)|ecb00|radio0|clock|temp|ccm00|aar00|rramc)$")
      message(FATAL_ERROR "nrfkit_claim_resources: invalid resource '${resource}'")
    endif()
    if(resource MATCHES "^dppi(00|10|20|30)\\.channel\\.([0-9]+)$")
      set(instance "${CMAKE_MATCH_1}")
      set(index "${CMAKE_MATCH_2}")
      if(instance STREQUAL "10")
        set(limit 24)
      elseif(instance STREQUAL "30")
        set(limit 4)
      else()
        set(limit 16)
      endif()
      if(index GREATER_EQUAL limit)
        message(FATAL_ERROR "nrfkit_claim_resources: '${resource}' is out of range")
      endif()
    elseif(resource MATCHES "^dppi(00|10|20|30)\\.group\\.([0-9]+)$")
      set(instance "${CMAKE_MATCH_1}")
      set(index "${CMAKE_MATCH_2}")
      if(instance STREQUAL "10" OR instance STREQUAL "20")
        set(limit 6)
      else()
        set(limit 2)
      endif()
      if(index GREATER_EQUAL limit)
        message(FATAL_ERROR "nrfkit_claim_resources: '${resource}' is out of range")
      endif()
    elseif(resource MATCHES "^gpiote(20|30)\\.channel\\.([0-9]+)$")
      set(instance "${CMAKE_MATCH_1}")
      set(index "${CMAKE_MATCH_2}")
      if(instance STREQUAL "20")
        set(limit 8)
      else()
        set(limit 4)
      endif()
      if(index GREATER_EQUAL limit)
        message(FATAL_ERROR "nrfkit_claim_resources: '${resource}' is out of range")
      endif()
    elseif(resource MATCHES "^ppib(00|10|11|20|21)\\.channel\\.([0-9]+)$")
      set(index "${CMAKE_MATCH_2}")
      if(index GREATER_EQUAL 16)
        message(FATAL_ERROR "nrfkit_claim_resources: '${resource}' is out of range")
      endif()
    elseif(resource MATCHES "^grtc\\.channel\\.([0-9]+)$")
      set(index "${CMAKE_MATCH_1}")
      if(index GREATER_EQUAL 16)
        message(FATAL_ERROR "nrfkit_claim_resources: '${resource}' is out of range")
      endif()
    endif()
    string(MAKE_C_IDENTIFIER "${resource}" resource_id)
    get_target_property(existing_owner "${target}"
      "NRFKIT_RESOURCE_${resource_id}_OWNER"
    )
    if(existing_owner)
      message(FATAL_ERROR
        "nrfkit_claim_resources: '${resource}' is already owned by '${existing_owner}'"
      )
    endif()
    set_target_properties("${target}" PROPERTIES
      "NRFKIT_RESOURCE_${resource_id}_OWNER" "${ARG_OWNER}"
    )
    list(APPEND resource_keys "${resource}")
  endforeach()
  list(REMOVE_DUPLICATES resource_keys)
  set_target_properties("${target}" PROPERTIES
    NRFKIT_RESOURCE_KEYS "${resource_keys}"
  )
endfunction()

function(_nrfkit_finalize_nrfx target)
  get_target_property(drivers "${target}" NRFKIT_NRFX_DRIVERS)
  get_target_property(headers_required "${target}" NRFKIT_NRFX_HEADERS_REQUIRED)
  if(NOT drivers AND NOT headers_required)
    return()
  endif()
  if(NOT drivers)
    set(drivers "")
  endif()

  set(sdk_root "${NrfKit_ROOT}")
  _nrfkit_prepare_nrfx(nrfx)
  string(MAKE_C_IDENTIFIER "${target}" target_id)
  set(config_dir "${CMAKE_CURRENT_BINARY_DIR}/nrfkit/${target_id}")
  file(MAKE_DIRECTORY "${config_dir}")

  set(config_definitions
    "#define NRFX_DEFAULT_IRQ_PRIORITY 7\n#define NRFX_PRS_ENABLED 0\n"
  )

  foreach(instance IN ITEMS 00 10 20 30)
    set(dppi_${instance}_channels 0)
    set(dppi_${instance}_groups 0)
  endforeach()
  set(gpiote_20_channels 0)
  set(gpiote_30_channels 0)
  get_target_property(resource_keys "${target}" NRFKIT_RESOURCE_KEYS)
  if(NOT resource_keys)
    set(resource_keys "")
  endif()
  foreach(resource IN LISTS resource_keys)
    if(resource MATCHES "^dppi(00|10|20|30)\\.channel\\.([0-9]+)$")
      set(instance "${CMAKE_MATCH_1}")
      set(index "${CMAKE_MATCH_2}")
      math(EXPR dppi_${instance}_channels
        "${dppi_${instance}_channels} | (1 << ${index})" OUTPUT_FORMAT HEXADECIMAL
      )
    elseif(resource MATCHES "^dppi(00|10|20|30)\\.group\\.([0-9]+)$")
      set(instance "${CMAKE_MATCH_1}")
      set(index "${CMAKE_MATCH_2}")
      math(EXPR dppi_${instance}_groups
        "${dppi_${instance}_groups} | (1 << ${index})" OUTPUT_FORMAT HEXADECIMAL
      )
    elseif(resource MATCHES "^gpiote(20|30)\\.channel\\.([0-9]+)$")
      set(instance "${CMAKE_MATCH_1}")
      set(index "${CMAKE_MATCH_2}")
      math(EXPR gpiote_${instance}_channels
        "${gpiote_${instance}_channels} | (1 << ${index})" OUTPUT_FORMAT HEXADECIMAL
      )
    endif()
  endforeach()
  foreach(instance IN ITEMS 00 10 20 30)
    string(APPEND config_definitions
      "#define NRFKIT_DPPI${instance}_CHANNELS_RESERVED ${dppi_${instance}_channels}U\n"
      "#define NRFKIT_DPPI${instance}_GROUPS_RESERVED ${dppi_${instance}_groups}U\n"
    )
  endforeach()
  string(APPEND config_definitions
    "#define NRFX_GPIOTE20_CHANNELS_USED ${gpiote_20_channels}U\n"
    "#define NRFX_GPIOTE30_CHANNELS_USED ${gpiote_30_channels}U\n"
    "#ifdef CONFIG_NRFX_GPIOTE_NUM_OF_EVT_HANDLERS\n"
    "#define NRFX_GPIOTE_CONFIG_NUM_OF_EVT_HANDLERS CONFIG_NRFX_GPIOTE_NUM_OF_EVT_HANDLERS\n"
    "#endif\n"
  )
  foreach(driver IN LISTS drivers)
    if(driver STREQUAL "watchdog")
      set(config_name WDT)
    elseif(driver STREQUAL "dppi")
      set(config_name DPPI)
    elseif(driver MATCHES "^(gpio|reset|retention)$")
      continue()
    else()
      string(TOUPPER "${driver}" config_name)
    endif()
    string(APPEND config_definitions "#define NRFX_${config_name}_ENABLED 1\n")
  endforeach()

  set(serial_drivers spim twim uarte)
  set(has_serial_driver FALSE)
  foreach(serial_driver IN LISTS serial_drivers)
    if(serial_driver IN_LIST drivers)
      set(has_serial_driver TRUE)
    endif()
  endforeach()
  if(has_serial_driver)
    string(APPEND config_definitions "#undef NRFX_PRS_ENABLED\n#define NRFX_PRS_ENABLED 1\n")
    foreach(box RANGE 0 6)
      string(APPEND config_definitions "#define NRFX_PRS_BOX_${box}_ENABLED 1\n")
    endforeach()
  endif()
  if("dppi" IN_LIST drivers)
    string(APPEND config_definitions "#define NRFX_DPPI20_ENABLED 1\n")
  endif()

  get_target_property(softdevice "${target}" NRFKIT_SOFTDEVICE)
  if(softdevice STREQUAL "s115")
    # nRF-BM connects the shared IRQs itself.  The standalone nrfx IRQ alias
    # header would otherwise rename the callable nrfx handlers to vector names
    # and collide with the audited forwarding shim.
    set(nrfx_irqs_include "")
  else()
    set(nrfx_irqs_include "#include <soc/nrfx_irqs.h>\n")
  endif()

  string(CONCAT config_content
    "/* Generated by nrfkit; target-local and not for source control. */\n"
    "#ifndef NRFKIT_GENERATED_NRFX_CONFIG_H\n"
    "#define NRFKIT_GENERATED_NRFX_CONFIG_H\n"
    "#define NRFX_CONFIG_H__\n"
    "${config_definitions}"
    "#include <templates/nrfx_config_common.h>\n"
    "#include <bsp/stable/templates/nrfx_config_nrf54lm20a_application.h>\n"
    "${nrfx_irqs_include}"
    "#endif\n"
  )
  file(WRITE "${config_dir}/nrfx_config.h" "${config_content}")

  target_include_directories("${target}" PRIVATE
    "${config_dir}"
    "${nrfx}"
    "${nrfx}/bsp/stable"
    "${nrfx}/drivers/include"
    "${nrfx}/drivers/src"
    "${nrfx}/bsp/stable/soc/interconnect"
  )

  set(sources "")
  foreach(driver IN LISTS drivers)
    if(driver STREQUAL "clock")
      list(APPEND sources
        drivers/src/nrfx_clock.c
        drivers/src/nrfx_clock_hfclk.c
        drivers/src/nrfx_clock_hfclk192m.c
        drivers/src/nrfx_clock_hfclkaudio.c
        drivers/src/nrfx_clock_lfclk.c
        drivers/src/nrfx_clock_xo.c
        drivers/src/nrfx_clock_xo24m.c
      )
    elseif(driver STREQUAL "power")
      list(APPEND sources drivers/src/nrfx_power.c)
    elseif(driver STREQUAL "gpiote")
      list(APPEND sources drivers/src/nrfx_gpiote.c helpers/nrfx_flag32_allocator.c)
    elseif(driver STREQUAL "grtc")
      list(APPEND sources drivers/src/nrfx_grtc.c helpers/nrfx_flag32_allocator.c)
    elseif(driver STREQUAL "timer")
      list(APPEND sources drivers/src/nrfx_timer.c)
    elseif(driver STREQUAL "dppi")
      list(APPEND sources
        helpers/nrfx_gppi_dppi.c
        helpers/nrfx_flag32_allocator.c
        bsp/stable/soc/interconnect/nrfx_gppi_d2ppi.c
        sdk:runtime/nrfx/gppi.c
      )
    elseif(driver MATCHES "^(uarte|spim|twim|pwm|saadc|rramc)$")
      list(APPEND sources "drivers/src/nrfx_${driver}.c")
    elseif(driver STREQUAL "watchdog")
      list(APPEND sources drivers/src/nrfx_wdt.c)
    elseif(driver STREQUAL "cracen")
      list(APPEND sources drivers/src/nrfx_cracen.c)
    elseif(driver STREQUAL "retention")
      list(APPEND sources helpers/nrfx_ram_ctrl.c)
    endif()
  endforeach()
  if(has_serial_driver)
    list(APPEND sources drivers/src/prs/nrfx_prs.c)
  endif()
  list(REMOVE_DUPLICATES sources)
  foreach(source IN LISTS sources)
    if(source MATCHES "^sdk:(.+)$")
      target_sources("${target}" PRIVATE "${sdk_root}/${CMAKE_MATCH_1}")
    else()
      target_sources("${target}" PRIVATE "${nrfx}/${source}")
    endif()
  endforeach()

  string(REPLACE ";" "\", \"" drivers_json "${drivers}")
  string(REPLACE ";" "\", \"" sources_json "${sources}")
  string(REPLACE ";" "\", \"" resources_json "${resource_keys}")
  if(drivers_json)
    set(drivers_json "\"${drivers_json}\"")
  endif()
  if(sources_json)
    set(sources_json "\"${sources_json}\"")
  endif()
  if(resources_json)
    set(resources_json "\"${resources_json}\"")
  endif()
  file(WRITE "${config_dir}/nrfx-target.json"
    "{\n"
    "  \"schema\": \"nrfkit-nrfx-target/v1\",\n"
    "  \"target\": \"${target}\",\n"
    "  \"drivers\": [${drivers_json}],\n"
    "  \"sources\": [${sources_json}],\n"
    "  \"reserved_resources\": [${resources_json}]\n"
    "}\n"
  )
  set_target_properties("${target}" PROPERTIES
    NRFKIT_NRFX_CONFIG "${config_dir}/nrfx_config.h"
    NRFKIT_NRFX_SOURCES "${sources}"
  )
endfunction()

function(nrfkit_configure_target target)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "nrfkit_configure_target: unknown target '${target}'")
  endif()

  cmake_parse_arguments(PARSE_ARGV 1 ARG "" "SOC;CORE;BOARD;RUNTIME" "")
  if(ARG_UNPARSED_ARGUMENTS)
    message(FATAL_ERROR "nrfkit_configure_target: unknown arguments: ${ARG_UNPARSED_ARGUMENTS}")
  endif()
  if(NOT ARG_SOC STREQUAL "nrf54lm20a")
    message(FATAL_ERROR "M1 supports SOC nrf54lm20a only")
  endif()
  if(NOT ARG_CORE STREQUAL "cpuapp")
    message(FATAL_ERROR "nrf54lm20a supports CORE cpuapp only")
  endif()
  if(ARG_RUNTIME AND NOT ARG_RUNTIME STREQUAL "freestanding")
    message(FATAL_ERROR "M1 supports RUNTIME freestanding only")
  endif()
  if(ARG_BOARD AND NOT ARG_BOARD STREQUAL "nrf54lm20dk")
    message(FATAL_ERROR "M1 supports BOARD nrf54lm20dk only")
  endif()

  set(sdk_root "${NrfKit_ROOT}")
  set(mdk "${sdk_root}/third_party/nrfx/mdk")
  set(linker_script "${sdk_root}/linker/layouts/nrf54lm20a-cpuapp-standalone.ld")
  foreach(required IN ITEMS
      "${mdk}/nrf54l/nrf54lm20a/gcc_startup_nrf54lm20a_application.S"
      "${mdk}/nrf54l/system_nrf54l.c"
      "${linker_script}")
    if(NOT EXISTS "${required}")
      message(FATAL_ERROR "NrfKit package is incomplete: ${required}")
    endif()
  endforeach()

  target_sources("${target}" PRIVATE
    "${mdk}/nrf54l/nrf54lm20a/gcc_startup_nrf54lm20a_application.S"
    "${mdk}/nrf54l/system_nrf54l.c"
    "${sdk_root}/runtime/common/freestanding.c"
    "${sdk_root}/runtime/cortex-m/fault.c"
  )
  target_include_directories("${target}" PRIVATE
    "${sdk_root}/include"
    "${sdk_root}/runtime/freestanding/include"
    "${sdk_root}/third_party/cmsis/CMSIS/Core/Include"
    "${mdk}"
  )
  if(ARG_BOARD)
    target_include_directories("${target}" PRIVATE
      "${sdk_root}/boards/${ARG_BOARD}/include"
    )
  endif()
  target_compile_definitions("${target}" PRIVATE
    NRF54LM20A_XXAA
    NRF_APPLICATION
    __STARTUP_CLEAR_BSS
    __START=nrfkit_start
    __STACK_SIZE=0x4000
    __HEAP_SIZE=0
  )
  target_compile_options("${target}" PRIVATE
    $<$<COMPILE_LANGUAGE:C,CXX,ASM>:-mcpu=cortex-m33;-mthumb;-mfloat-abi=hard;-mfpu=fpv5-sp-d16>
    $<$<COMPILE_LANGUAGE:C,CXX>:-ffreestanding;-ffunction-sections;-fdata-sections;-fno-common>
    $<$<COMPILE_LANGUAGE:CXX>:-fno-exceptions;-fno-rtti;-fno-threadsafe-statics;-fno-use-cxa-atexit>
  )

  target_link_options("${target}" PRIVATE
    -mcpu=cortex-m33 -mthumb -mfloat-abi=hard -mfpu=fpv5-sp-d16
    -nostdlib
    -Wl,--gc-sections
    -Wl,--build-id=none
    "-Wl,-Map,$<TARGET_FILE_DIR:${target}>/$<TARGET_FILE_BASE_NAME:${target}>.map"
    "-T${linker_script}"
  )
  if(CMAKE_C_COMPILER_ID MATCHES "Clang")
    target_link_options("${target}" PRIVATE -fuse-ld=lld)
  elseif(CMAKE_C_COMPILER_ID STREQUAL "GNU")
    # -nostdlib intentionally omits the C library and startup files, but GCC may
    # still lower ordinary C operations such as 64-bit division to libgcc.
    target_link_libraries("${target}" PRIVATE gcc)
  endif()
  set_target_properties("${target}" PROPERTIES
    SUFFIX ".elf"
    NRFKIT_CONFIGURED TRUE
    NRFKIT_SOC "nrf54lm20a"
    NRFKIT_CORE "cpuapp"
    NRFKIT_BOARD "${ARG_BOARD}"
    LINK_DEPENDS "${linker_script}"
  )
endfunction()

function(nrfkit_finalize_target target)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "nrfkit_finalize_target: unknown target '${target}'")
  endif()
  get_target_property(configured "${target}" NRFKIT_CONFIGURED)
  if(NOT configured)
    message(FATAL_ERROR "nrfkit_finalize_target: configure '${target}' first")
  endif()
  get_target_property(finalized "${target}" NRFKIT_FINALIZED)
  if(finalized)
    message(FATAL_ERROR "nrfkit_finalize_target: '${target}' is already finalized")
  endif()
  get_target_property(usb_stack "${target}" NRFKIT_USB_DEVICE_STACK)
  get_target_property(sdc_variant "${target}" NRFKIT_SDC_VARIANT)
  get_target_property(nrfx_drivers "${target}" NRFKIT_NRFX_DRIVERS)
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
  _nrfkit_finalize_nrfx("${target}")
  if(NOT CMAKE_OBJCOPY)
    message(FATAL_ERROR "CMAKE_OBJCOPY is required to finalize firmware")
  endif()

  set(hex "$<TARGET_FILE_DIR:${target}>/$<TARGET_FILE_BASE_NAME:${target}>.hex")
  set(bin "$<TARGET_FILE_DIR:${target}>/$<TARGET_FILE_BASE_NAME:${target}>.bin")
  add_custom_command(TARGET "${target}" POST_BUILD
    COMMAND "${CMAKE_OBJCOPY}" -O ihex "$<TARGET_FILE:${target}>" "${hex}"
    COMMAND "${CMAKE_OBJCOPY}" -O binary "$<TARGET_FILE:${target}>" "${bin}"
    VERBATIM
  )

  get_target_property(layout "${target}" NRFKIT_LAYOUT)
  if(layout STREQUAL "s115-10.0.1")
    get_target_property(softdevice_hex "${target}" NRFKIT_SOFTDEVICE_HEX)
    set(layout_content
      "{\n  \"schema\": \"nrfkit-image-layout/v1\",\n  \"target\": \"${target}\",\n  \"soc\": \"nrf54lm20a\",\n  \"core\": \"cpuapp\",\n  \"rram\": {\"origin\": 0, \"length\": 1972224},\n  \"settings\": {\"origin\": 1972224, \"length\": 8192},\n  \"softdevice\": {\"name\": \"s115\", \"version\": \"10.0.1\", \"origin\": 1980416, \"length\": 103424},\n  \"ram\": {\"origin\": 536879400, \"length\": 253656},\n  \"configuration_regions_allowed\": false\n}\n"
    )
    file(GENERATE
      OUTPUT "$<TARGET_FILE_DIR:${target}>/$<TARGET_FILE_BASE_NAME:${target}>.softdevice-input.json"
      CONTENT "{\n  \"schema\": \"nrfkit-softdevice-input/v1\",\n  \"name\": \"s115\",\n  \"version\": \"10.0.1\",\n  \"hex\": \"${softdevice_hex}\"\n}\n"
    )
  else()
    set(layout_content
      "{\n  \"schema\": \"nrfkit-image-layout/v1\",\n  \"target\": \"${target}\",\n  \"soc\": \"nrf54lm20a\",\n  \"core\": \"cpuapp\",\n  \"rram\": {\"origin\": 0, \"length\": 2084608},\n  \"rram_scratch\": {\"origin\": 2084608, \"length\": 256, \"write_unit\": 16},\n  \"ram\": {\"origin\": 536870912, \"length\": 262144},\n  \"configuration_regions_allowed\": false\n}\n"
    )
  endif()
  file(GENERATE
    OUTPUT "$<TARGET_FILE_DIR:${target}>/$<TARGET_FILE_BASE_NAME:${target}>.image-layout.json"
    CONTENT "${layout_content}"
  )
  set_target_properties("${target}" PROPERTIES NRFKIT_FINALIZED TRUE)
endfunction()
