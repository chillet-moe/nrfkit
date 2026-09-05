# SPDX-License-Identifier: BSD-3-Clause

include_guard(GLOBAL)

set(_NRFKIT_NRFX_DRIVERS
  clock power gpio gpiote grtc timer dppi uarte spim twim pwm saadc rramc watchdog
  reset retention cracen
)

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
  _nrfkit_require_open_target("${target}" nrfkit_enable_nrfx)

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

function(nrfkit_claim_resources target)
  _nrfkit_require_open_target("${target}" nrfkit_claim_resources)
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

function(_nrfkit_define_nrfx_targets nrfx)
  if(TARGET _nrfkit_nrfx_headers)
    return()
  endif()
  add_library(_nrfkit_nrfx_headers INTERFACE IMPORTED GLOBAL)
  set_target_properties(_nrfkit_nrfx_headers PROPERTIES SYSTEM FALSE)
  target_include_directories(_nrfkit_nrfx_headers INTERFACE
    "${nrfx}" "${nrfx}/bsp/stable" "${nrfx}/drivers/include"
    "${nrfx}/drivers/src" "${nrfx}/bsp/stable/soc/interconnect")

  # Most drivers are one source file; list only the multi-source/renamed cases.
  set(clock_sources
    drivers/src/nrfx_clock.c
    drivers/src/nrfx_clock_hfclk.c
    drivers/src/nrfx_clock_hfclk192m.c
    drivers/src/nrfx_clock_hfclkaudio.c
    drivers/src/nrfx_clock_lfclk.c
    drivers/src/nrfx_clock_xo.c
    drivers/src/nrfx_clock_xo24m.c)
  set(gpiote_sources drivers/src/nrfx_gpiote.c helpers/nrfx_flag32_allocator.c)
  set(grtc_sources drivers/src/nrfx_grtc.c helpers/nrfx_flag32_allocator.c)
  set(dppi_sources
    helpers/nrfx_gppi_dppi.c helpers/nrfx_flag32_allocator.c
    bsp/stable/soc/interconnect/nrfx_gppi_d2ppi.c)
  set(watchdog_sources drivers/src/nrfx_wdt.c)
  set(retention_sources helpers/nrfx_ram_ctrl.c)
  set(gpio_sources "")
  set(reset_sources "")
  set(prs_sources drivers/src/prs/nrfx_prs.c)
  foreach(driver IN LISTS _NRFKIT_NRFX_DRIVERS ITEMS prs)
    if(DEFINED ${driver}_sources)
      set(sources "${${driver}_sources}")
    else()
      set(sources "drivers/src/nrfx_${driver}.c")
    endif()
    list(TRANSFORM sources PREPEND "${nrfx}/")
    add_library("_nrfkit_nrfx_${driver}" INTERFACE IMPORTED GLOBAL)
    target_sources("_nrfkit_nrfx_${driver}" INTERFACE ${sources})
    target_link_libraries("_nrfkit_nrfx_${driver}" INTERFACE _nrfkit_nrfx_headers)
  endforeach()
  target_sources(_nrfkit_nrfx_dppi INTERFACE "${NrfKit_ROOT}/runtime/nrfx/gppi.c")
  foreach(driver IN ITEMS uarte spim twim)
    target_link_libraries("_nrfkit_nrfx_${driver}" INTERFACE _nrfkit_nrfx_prs)
  endforeach()
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

  configure_file("${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../templates/nrfx_config.h.in"
    "${config_dir}/nrfx_config.h" @ONLY)

  _nrfkit_define_nrfx_targets("${nrfx}")
  target_include_directories("${target}" PRIVATE "${config_dir}")
  target_link_libraries("${target}" PRIVATE _nrfkit_nrfx_headers)
  set(sources "")
  foreach(driver IN LISTS drivers)
    target_link_libraries("${target}" PRIVATE "_nrfkit_nrfx_${driver}")
    get_target_property(driver_sources "_nrfkit_nrfx_${driver}" INTERFACE_SOURCES)
    if(driver_sources)
      list(APPEND sources ${driver_sources})
    endif()
  endforeach()
  if(has_serial_driver)
    get_target_property(prs_sources _nrfkit_nrfx_prs INTERFACE_SOURCES)
    list(APPEND sources ${prs_sources})
  endif()
  list(REMOVE_DUPLICATES sources)
  # Reports retain stable SDK-relative names, independently of native target names.
  set(relative_sources "")
  foreach(source IN LISTS sources)
    cmake_path(IS_PREFIX nrfx "${source}" NORMALIZE upstream_source)
    if(upstream_source)
      file(RELATIVE_PATH relative "${nrfx}" "${source}")
    else()
      file(RELATIVE_PATH relative "${sdk_root}" "${source}")
      string(PREPEND relative "sdk:")
    endif()
    list(APPEND relative_sources "${relative}")
  endforeach()
  set(sources "${relative_sources}")

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
  configure_file("${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../templates/nrfx-target.json.in"
    "${config_dir}/nrfx-target.json" @ONLY)
  set_target_properties("${target}" PROPERTIES
    NRFKIT_NRFX_CONFIG "${config_dir}/nrfx_config.h"
    NRFKIT_NRFX_SOURCES "${sources}"
  )
endfunction()
