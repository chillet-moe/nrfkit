# SPDX-License-Identifier: BSD-3-Clause

include_guard(GLOBAL)

set(_NRFKIT_NRFX_DRIVERS
  clock gpio gpiote grtc timer dppi uarte spim twim pwm saadc rramc watchdog
  reset retention
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
  target_sources("${target}" PRIVATE "${NrfKit_ROOT}/radio/nrf54l/radio.c")
  nrfkit_enable_nrfx("${target}" DRIVERS clock)
  set_target_properties("${target}" PROPERTIES NRFKIT_RADIO_ENABLED TRUE)
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
  nrfkit_enable_nrfx("${target}" DRIVERS clock)
  set_target_properties("${target}" PROPERTIES
    NRFKIT_USB_DEVICE_STACK cherryusb
    NRFKIT_USB_DEVICE_SOURCE "${cherryusb}"
    NRFKIT_USB_DEVICE_CLASSES "${ARG_CLASSES}"
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
        "^(dppi(00|10|20|30)\\.(channel\\.([0-9]+)|group\\.([0-9]+))|gpiote(20|30)\\.channel\\.([0-9]+)|timer(00|10|20|21|22|23|24))$")
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
  if(NOT drivers)
    return()
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

  string(CONCAT config_content
    "/* Generated by nrfkit; target-local and not for source control. */\n"
    "#ifndef NRFKIT_GENERATED_NRFX_CONFIG_H\n"
    "#define NRFKIT_GENERATED_NRFX_CONFIG_H\n"
    "#define NRFX_CONFIG_H__\n"
    "${config_definitions}"
    "#include <templates/nrfx_config_common.h>\n"
    "#include <bsp/stable/templates/nrfx_config_nrf54lm20a_application.h>\n"
    "#include <soc/nrfx_irqs.h>\n"
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
  set(drivers_json "\"${drivers_json}\"")
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

  file(GENERATE
    OUTPUT "$<TARGET_FILE_DIR:${target}>/$<TARGET_FILE_BASE_NAME:${target}>.image-layout.json"
    CONTENT "{\n  \"schema\": \"nrfkit-image-layout/v1\",\n  \"target\": \"${target}\",\n  \"soc\": \"nrf54lm20a\",\n  \"core\": \"cpuapp\",\n  \"rram\": {\"origin\": 0, \"length\": 2084608},\n  \"rram_scratch\": {\"origin\": 2084608, \"length\": 256, \"write_unit\": 16},\n  \"ram\": {\"origin\": 536870912, \"length\": 262144},\n  \"configuration_regions_allowed\": false\n}\n"
  )
  set_target_properties("${target}" PROPERTIES NRFKIT_FINALIZED TRUE)
endfunction()
