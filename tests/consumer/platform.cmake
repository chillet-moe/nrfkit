# SPDX-License-Identifier: BSD-3-Clause

# This fixture deliberately assembles a firmware target from the public
# platform targets. The consumer owns the linker script and image policy.
function(nrfkit_test_firmware target)
  target_link_libraries("${target}" PRIVATE
    NrfKit::soc_nrf54lm20a
    NrfKit::startup
    NrfKit::runtime_freestanding
    NrfKit::board_nrf54lm20dk
  )
  target_compile_definitions("${target}" PRIVATE __STACK_SIZE=0x4000 __HEAP_SIZE=0)
  target_compile_options("${target}" PRIVATE
    $<$<COMPILE_LANGUAGE:C,CXX>:-ffunction-sections;-fdata-sections>
    $<$<COMPILE_LANGUAGE:CXX>:-fno-exceptions;-fno-rtti;-fno-threadsafe-statics;-fno-use-cxa-atexit>)
  target_link_options("${target}" PRIVATE
    "-T${NrfKit_ROOT}/linker/layouts/nrf54lm20a-cpuapp-standalone.ld"
    LINKER:--gc-sections LINKER:--build-id=none
    "LINKER:-Map,${CMAKE_CURRENT_BINARY_DIR}/${target}.map"
  )
  set_target_properties("${target}" PROPERTIES SUFFIX ".elf")
endfunction()
