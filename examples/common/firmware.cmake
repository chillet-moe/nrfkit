# SPDX-License-Identifier: BSD-3-Clause

include_guard(GLOBAL)

# Policy for this repository's validation programs, not a public SDK API.
function(nrfkit_example_firmware target)
  target_link_libraries("${target}" PRIVATE
    NrfKit::runtime_freestanding NrfKit::board_nrf54lm20dk)
  target_compile_definitions("${target}" PRIVATE __STACK_SIZE=0x4000 __HEAP_SIZE=0)
  target_compile_options("${target}" PRIVATE
    $<$<COMPILE_LANGUAGE:C,CXX>:-ffunction-sections;-fdata-sections>
    $<$<COMPILE_LANGUAGE:CXX>:-fno-exceptions;-fno-rtti;-fno-threadsafe-statics;-fno-use-cxa-atexit>)
  set(linker_script "${NrfKit_ROOT}/linker/layouts/nrf54lm20a-cpuapp-standalone.ld")
  target_link_options("${target}" PRIVATE
    "LINKER:-T,${linker_script}" LINKER:--gc-sections LINKER:--build-id=none
    "LINKER:-Map,$<TARGET_FILE_DIR:${target}>/$<TARGET_FILE_BASE_NAME:${target}>.map")
  set_property(TARGET "${target}" APPEND PROPERTY LINK_DEPENDS "${linker_script}")
  set_target_properties("${target}" PROPERTIES SUFFIX ".elf")
  add_custom_command(TARGET "${target}" POST_BUILD
    COMMAND "${CMAKE_OBJCOPY}" -O ihex "$<TARGET_FILE:${target}>"
      "$<TARGET_FILE_DIR:${target}>/$<TARGET_FILE_BASE_NAME:${target}>.hex"
    COMMAND "${CMAKE_OBJCOPY}" -O binary "$<TARGET_FILE:${target}>"
      "$<TARGET_FILE_DIR:${target}>/$<TARGET_FILE_BASE_NAME:${target}>.bin"
    VERBATIM)
endfunction()
