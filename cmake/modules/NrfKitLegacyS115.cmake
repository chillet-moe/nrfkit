# SPDX-License-Identifier: BSD-3-Clause

include_guard(GLOBAL)

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

function(_nrfkit_configure_s115_baseline target)
  _nrfkit_require_open_target("${target}" nrfkit_enable_s115)
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
