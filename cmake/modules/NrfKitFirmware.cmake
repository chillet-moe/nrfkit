# SPDX-License-Identifier: BSD-3-Clause

include_guard(GLOBAL)

# Shared preconditions apply to a firmware target, not to global build state.
function(_nrfkit_require_open_target target caller)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "${caller}: unknown target '${target}'")
  endif()
  get_target_property(configured "${target}" NRFKIT_CONFIGURED)
  if(NOT configured)
    message(FATAL_ERROR "${caller}: configure '${target}' first")
  endif()
  get_target_property(finalized "${target}" NRFKIT_FINALIZED)
  if(finalized)
    message(FATAL_ERROR "${caller}: '${target}' is already finalized")
  endif()
endfunction()

include("${CMAKE_CURRENT_LIST_DIR}/NrfKitNrfxlib.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/NrfKitNrfx.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/NrfKitWireless.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/NrfKitUsb.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/NrfKitImage.cmake")

# Follow compile usage requirements, rather than private implementation links of
# intermediate libraries. Capability selection is configuration-independent;
# generator expressions still belong to CMake, not a second evaluator here.
function(_nrfkit_collect_capabilities root out_var)
  set(queue "${root}|plain")
  set(seen "")
  set(found "")
  while(queue)
    list(POP_FRONT queue entry)
    if(entry IN_LIST seen)
      continue()
    endif()
    list(APPEND seen "${entry}")
    string(REPLACE "|" ";" parts "${entry}")
    list(GET parts 0 node)
    list(GET parts 1 mode)
    get_target_property(kind "${node}" NRFKIT_CAPABILITY)
    if(kind)
      if(mode STREQUAL "conditional")
        message(FATAL_ERROR
          "nrfkit_finalize_target: conditional capability '${node}' is unsupported; select firmware capabilities with ordinary CMake if() and links")
      elseif(mode STREQUAL "compiled")
        message(FATAL_ERROR
          "nrfkit_finalize_target: capability '${node}' must propagate through INTERFACE libraries so its sources use the firmware configuration")
      endif()
      list(APPEND found "${node}")
    endif()
    if(node STREQUAL root)
      get_target_property(edges "${node}" LINK_LIBRARIES)
    else()
      get_target_property(edges "${node}" INTERFACE_LINK_LIBRARIES)
      get_target_property(type "${node}" TYPE)
      if(NOT type STREQUAL "INTERFACE_LIBRARY" AND mode STREQUAL "plain")
        set(mode compiled)
      endif()
    endif()
    foreach(edge IN LISTS edges)
      set(edge_mode "${mode}")
      # These wrappers have unambiguous compile-usage meaning in a consumer build.
      while(edge MATCHES "^\\$<(BUILD_INTERFACE|TARGET_NAME_IF_EXISTS|1):(.*)>$")
        set(edge "${CMAKE_MATCH_2}")
      endwhile()
      if(edge MATCHES "^\\$<LINK_ONLY:(.*)>$")
        set(edge "${CMAKE_MATCH_1}")
        set(edge_mode compiled)
      endif()
      if(edge MATCHES "^\\$<(INSTALL_INTERFACE|0):")
        continue()
      endif()
      if(edge MATCHES "\\$<")
        # Inspect only target references for the purpose of detecting a hidden
        # capability. Do not guess the truth value of arbitrary expressions.
        string(REGEX MATCHALL "[A-Za-z_][A-Za-z0-9_:.-]*" candidates "${edge}")
        set(edge_mode conditional)
      else()
        set(candidates "${edge}")
      endif()
      foreach(candidate IN LISTS candidates)
        if(TARGET "${candidate}")
          list(APPEND queue "${candidate}|${edge_mode}")
        endif()
      endforeach()
    endforeach()
  endwhile()
  list(REMOVE_DUPLICATES found)
  set(${out_var} "${found}" PARENT_SCOPE)
endfunction()

function(nrfkit_configure_target target)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "nrfkit_configure_target: unknown target '${target}'")
  endif()

  get_target_property(configured "${target}" NRFKIT_CONFIGURED)
  if(configured)
    message(FATAL_ERROR "nrfkit_configure_target: '${target}' is already configured")
  endif()
  get_target_property(type "${target}" TYPE)
  get_target_property(alias "${target}" ALIASED_TARGET)
  get_target_property(imported "${target}" IMPORTED)
  if(NOT type STREQUAL "EXECUTABLE" OR alias OR imported)
    message(FATAL_ERROR "nrfkit_configure_target: requires a local executable")
  endif()
  cmake_parse_arguments(PARSE_ARGV 1 ARG ""
    "SOC;CORE;BOARD;RUNTIME;LINKER_SCRIPT;IMAGE_LAYOUT" "")
  if(ARG_UNPARSED_ARGUMENTS)
    message(FATAL_ERROR "nrfkit_configure_target: unknown arguments: ${ARG_UNPARSED_ARGUMENTS}")
  endif()
  if(NOT ARG_SOC STREQUAL "nrf54lm20a")
    message(FATAL_ERROR "M1 supports SOC nrf54lm20a only")
  endif()
  if(NOT ARG_CORE)
    set(ARG_CORE cpuapp)
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

  if((ARG_LINKER_SCRIPT AND NOT ARG_IMAGE_LAYOUT) OR
      (ARG_IMAGE_LAYOUT AND NOT ARG_LINKER_SCRIPT))
    message(FATAL_ERROR
      "nrfkit_configure_target: LINKER_SCRIPT and IMAGE_LAYOUT must be supplied together"
    )
  endif()

  set(sdk_root "${NrfKit_ROOT}")
  set(mdk "${sdk_root}/external/nrfx/bsp/stable/mdk")
  _nrfkit_configure_image_layout("${target}" "${ARG_LINKER_SCRIPT}" "${ARG_IMAGE_LAYOUT}"
    linker_script image_layout)
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
    "${sdk_root}/src/runtime/common/freestanding.c"
    "${sdk_root}/src/runtime/cortex-m/fault.c"
    "${sdk_root}/src/runtime/cortex-m/reset.c"
  )
  target_include_directories("${target}" PRIVATE
    "${sdk_root}/include"
    "${sdk_root}/src/runtime/freestanding/include"
    "${sdk_root}/external/cmsis/CMSIS/Core/Include"
    "${mdk}"
  )
  if(ARG_BOARD)
    target_include_directories("${target}" PRIVATE
      "${sdk_root}/src/boards/${ARG_BOARD}/include"
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
    NRFKIT_IMAGE_LAYOUT "${image_layout}"
  )
  set_property(TARGET "${target}" APPEND PROPERTY LINK_DEPENDS "${linker_script}")
endfunction()

function(nrfkit_finalize_target target)
  _nrfkit_require_open_target("${target}" nrfkit_finalize_target)
  _nrfkit_collect_capabilities("${target}" capabilities)
  foreach(capability IN LISTS capabilities)
    get_target_property(kind "${capability}" NRFKIT_CAPABILITY)
    if(kind STREQUAL "nrfx")
      get_target_property(driver "${capability}" NRFKIT_NRFX_DRIVER)
      get_target_property(drivers "${target}" NRFKIT_NRFX_DRIVERS)
      if(NOT drivers)
        set(drivers "")
      endif()
      list(APPEND drivers "${driver}")
      list(REMOVE_DUPLICATES drivers)
      set_target_properties("${target}" PROPERTIES NRFKIT_NRFX_DRIVERS "${drivers}")
    elseif(kind STREQUAL "sdc")
      get_target_property(variant "${capability}" NRFKIT_SDC_VARIANT)
      get_target_property(existing "${target}" NRFKIT_SDC_VARIANT)
      if(existing AND NOT existing STREQUAL variant)
        message(FATAL_ERROR "nrfkit_finalize_target: multiple SDC variants selected for '${target}'")
      endif()
      set_target_properties("${target}" PROPERTIES NRFKIT_SDC_VARIANT "${variant}")

    elseif(kind MATCHES "^usb_(port|device)$")
      get_target_property(configured "${target}" NRFKIT_USB_CONFIGURED)
      if(NOT configured)
        nrfkit_configure_usb("${target}")
      endif()
      set_target_properties("${target}" PROPERTIES
        NRFKIT_USB_DEVICE_STACK cherryusb NRFKIT_NRFX_HEADERS_REQUIRED TRUE)
    elseif(kind STREQUAL "rram")
      set_target_properties("${target}" PROPERTIES NRFKIT_RRAM_ENABLED TRUE)
    elseif(kind STREQUAL "radio_timeslot")
      set_target_properties("${target}" PROPERTIES NRFKIT_MPSL_TIMESLOT_ENABLED TRUE)
    elseif(kind STREQUAL "radio_direct")
      set_target_properties("${target}" PROPERTIES NRFKIT_RADIO_ENABLED TRUE)
    endif()
  endforeach()
  _nrfkit_finalize_sdc("${target}")
  _nrfkit_validate_wireless("${target}")
  _nrfkit_finalize_nrfx("${target}")
  _nrfkit_add_image_artifacts("${target}")
  set_target_properties("${target}" PROPERTIES NRFKIT_FINALIZED TRUE)
endfunction()
