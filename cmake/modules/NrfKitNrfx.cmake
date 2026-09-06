# SPDX-License-Identifier: BSD-3-Clause

include_guard(GLOBAL)
include("${CMAKE_CURRENT_LIST_DIR}/NrfKitDependencies.cmake")

set(_NRFKIT_NRFX_DRIVERS
  clock power gpio gpiote grtc timer dppi uarte spim twim pwm saadc rramc watchdog
  reset retention cracen prs
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
  _nrfkit_read_selection(selected_files)
  _nrfkit_validate_selection("${nrfx_source}" "${selected_files}")

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
  file(SHA256 "${_NRFKIT_NRFX_SELECTION_FILE}" selection_hash)
  set(state "nrfx=${nrfx_commit}\nselection_manifest=${selection_hash}\n")
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
    _nrfkit_copy_selection("${nrfx_source}" "${staging}" "${selected_files}")
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

function(nrfkit_claim_resources target)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "nrfkit_claim_resources: unknown target '${target}'")
  endif()
  get_target_property(type "${target}" TYPE)
  if(NOT type STREQUAL "EXECUTABLE")
    message(FATAL_ERROR "nrfkit_claim_resources requires an executable target")
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
      "NRFKIT_RESOURCE_${resource_id}"
    )
    if(existing_owner)
      message(FATAL_ERROR
        "nrfkit_claim_resources: '${resource}' is already owned by '${existing_owner}'"
      )
    endif()
    # Native compatible interfaces compare application ownership with the
    # requirements of linked libraries, including transitive/conditional links.
    set_property(TARGET "${target}" PROPERTY "NRFKIT_RESOURCE_${resource_id}" "${ARG_OWNER}")
    list(APPEND resource_keys "${resource}")
  endforeach()
  list(REMOVE_DUPLICATES resource_keys)
  set_target_properties("${target}" PROPERTIES
    NRFKIT_RESOURCE_KEYS "${resource_keys}"
  )
  foreach(instance IN ITEMS 00 10 20 30)
    set(dppi_${instance}_channels 0)
    set(dppi_${instance}_groups 0)
  endforeach()
  set(gpiote_20_channels 0)
  set(gpiote_30_channels 0)
  foreach(resource IN LISTS resource_keys)
    if(resource MATCHES "^dppi(00|10|20|30)\\.channel\\.([0-9]+)$")
      set(instance "${CMAKE_MATCH_1}")
      set(index "${CMAKE_MATCH_2}")
      math(EXPR dppi_${instance}_channels "${dppi_${instance}_channels} | (1 << ${index})")
    elseif(resource MATCHES "^dppi(00|10|20|30)\\.group\\.([0-9]+)$")
      set(instance "${CMAKE_MATCH_1}")
      set(index "${CMAKE_MATCH_2}")
      math(EXPR dppi_${instance}_groups "${dppi_${instance}_groups} | (1 << ${index})")
    elseif(resource MATCHES "^gpiote(20|30)\\.channel\\.([0-9]+)$")
      set(instance "${CMAKE_MATCH_1}")
      set(index "${CMAKE_MATCH_2}")
      math(EXPR gpiote_${instance}_channels "${gpiote_${instance}_channels} | (1 << ${index})")
    endif()
  endforeach()
  set(masks "")
  foreach(instance IN ITEMS 00 10 20 30)
    foreach(kind IN ITEMS channels groups)
      string(TOUPPER "${kind}" upper)
      set(key "NRFKIT_APP_DPPI${instance}_${upper}_RESERVED")
      set_property(TARGET "${target}" PROPERTY "${key}" "${dppi_${instance}_${kind}}")
      list(APPEND masks "${key}")
    endforeach()
  endforeach()
  foreach(instance IN ITEMS 20 30)
    set(key "NRFKIT_APP_GPIOTE${instance}_CHANNELS_RESERVED")
    set_property(TARGET "${target}" PROPERTY "${key}" "${gpiote_${instance}_channels}")
    list(APPEND masks "${key}")
  endforeach()
  get_target_property(registered "${target}" NRFKIT_RESOURCE_MASKS_REGISTERED)
  if(NOT registered)
    foreach(key IN LISTS masks)
      # Evaluate the final accumulated value without a finalize call.
      target_compile_definitions("${target}" PRIVATE "${key}=$<TARGET_PROPERTY:${target},${key}>U")
    endforeach()
    set_property(TARGET "${target}" PROPERTY NRFKIT_RESOURCE_MASKS_REGISTERED TRUE)
  endif()
endfunction()

_nrfkit_prepare_nrfx(_nrfkit_nrfx_root)
add_library(_nrfkit_nrfx_headers INTERFACE IMPORTED GLOBAL)
target_include_directories(_nrfkit_nrfx_headers INTERFACE
  "${_nrfkit_nrfx_root}" "${_nrfkit_nrfx_root}/bsp/stable" "${_nrfkit_nrfx_root}/drivers/include"
  "${_nrfkit_nrfx_root}/drivers/src"
  "${_nrfkit_nrfx_root}/bsp/stable/soc/interconnect"
  "${NrfKit_ROOT}/src/runtime/nrfx/include" "${NrfKit_ROOT}/include")
set_target_properties(_nrfkit_nrfx_headers PROPERTIES SYSTEM FALSE)
target_link_libraries(_nrfkit_nrfx_headers INTERFACE NrfKit::soc_nrf54lm20a)

# Most drivers use one source; keep renamed and multi-source components explicit.
set(_nrfkit_clock_sources
  drivers/src/nrfx_clock.c drivers/src/nrfx_clock_hfclk.c
  drivers/src/nrfx_clock_hfclk192m.c drivers/src/nrfx_clock_hfclkaudio.c
  drivers/src/nrfx_clock_lfclk.c drivers/src/nrfx_clock_xo.c
  drivers/src/nrfx_clock_xo24m.c)
set(_nrfkit_gpiote_sources drivers/src/nrfx_gpiote.c helpers/nrfx_flag32_allocator.c)
set(_nrfkit_grtc_sources drivers/src/nrfx_grtc.c helpers/nrfx_flag32_allocator.c)
set(_nrfkit_dppi_sources
  helpers/nrfx_gppi_dppi.c helpers/nrfx_flag32_allocator.c
  bsp/stable/soc/interconnect/nrfx_gppi_d2ppi.c)
set(_nrfkit_watchdog_sources drivers/src/nrfx_wdt.c)
set(_nrfkit_retention_sources helpers/nrfx_ram_ctrl.c)
set(_nrfkit_prs_sources drivers/src/prs/nrfx_prs.c)
foreach(driver IN LISTS _NRFKIT_NRFX_DRIVERS)
  add_library("NrfKit::nrfx_${driver}" INTERFACE IMPORTED GLOBAL)
  set_target_properties("NrfKit::nrfx_${driver}" PROPERTIES SYSTEM FALSE)
  if(DEFINED _nrfkit_${driver}_sources)
    set(sources "${_nrfkit_${driver}_sources}")
  elseif(driver STREQUAL "gpio" OR driver STREQUAL "reset")
    set(sources "")
  else()
    set(sources "drivers/src/nrfx_${driver}.c")
  endif()
  list(TRANSFORM sources PREPEND "${_nrfkit_nrfx_root}/")
  if(sources)
    target_sources("NrfKit::nrfx_${driver}" INTERFACE ${sources})
  endif()
  target_link_libraries("NrfKit::nrfx_${driver}" INTERFACE _nrfkit_nrfx_headers)
  string(TOUPPER "${driver}" upper)
  if(driver STREQUAL "watchdog")
    set(upper WDT)
  endif()
  if(NOT driver MATCHES "^(gpio|reset|retention)$")
    target_compile_definitions("NrfKit::nrfx_${driver}" INTERFACE "NRFX_${upper}_ENABLED=1")
  endif()
endforeach()
set_property(TARGET NrfKit::nrfx_prs APPEND PROPERTY INTERFACE_COMPILE_DEFINITIONS
  NRFX_PRS_BOX_0_ENABLED=1 NRFX_PRS_BOX_1_ENABLED=1 NRFX_PRS_BOX_2_ENABLED=1
  NRFX_PRS_BOX_3_ENABLED=1 NRFX_PRS_BOX_4_ENABLED=1 NRFX_PRS_BOX_5_ENABLED=1
  NRFX_PRS_BOX_6_ENABLED=1)
set_property(TARGET NrfKit::nrfx_dppi APPEND PROPERTY INTERFACE_COMPILE_DEFINITIONS
  NRFX_DPPI20_ENABLED=1)
foreach(driver IN ITEMS uarte spim twim)
  target_link_libraries("NrfKit::nrfx_${driver}" INTERFACE NrfKit::nrfx_prs)
endforeach()
target_sources(NrfKit::nrfx_dppi INTERFACE "${NrfKit_ROOT}/src/runtime/nrfx/gppi.c")
set_property(TARGET NrfKit::nrfx_clock APPEND PROPERTY COMPATIBLE_INTERFACE_STRING NRFKIT_CLOCK_OWNER)
set_property(TARGET NrfKit::nrfx_clock PROPERTY INTERFACE_NRFKIT_CLOCK_OWNER nrfx)

unset(_nrfkit_nrfx_root)
