# SPDX-License-Identifier: BSD-3-Clause

cmake_minimum_required(VERSION 3.25)
project(nrfkit_m1_examples LANGUAGES C CXX ASM)

find_package(NrfKit CONFIG REQUIRED)
include("${CMAKE_CURRENT_LIST_DIR}/common/usb/reference.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/common/firmware.cmake")

function(add_m1_example name source)
  add_executable("${name}" "${source}")
  nrfkit_example_firmware("${name}")
  if(ARGN)
    foreach(driver IN LISTS ARGN)
      target_link_libraries("${name}" PRIVATE "NrfKit::nrfx_${driver}")
    endforeach()
  endif()

endfunction()

add_m1_example(empty empty/main.c)
add_m1_example(power_idle power-measurement/idle.c)
add_m1_example(power_system_off power-measurement/system-off.c clock grtc reset retention)
foreach(phy IN ITEMS 1 2 4)
  set(target "power_radio_${phy}m")
  add_m1_example("${target}" power-measurement/radio.c clock grtc)
  target_link_libraries("${target}" PRIVATE NrfKit::radio_direct)
  target_compile_definitions("${target}" PRIVATE "NRFKIT_POWER_PHY=${phy}")
endforeach()
add_m1_example(blinky blinky/main.c)
add_m1_example(fault fault/main.c)
add_m1_example(constructors constructors/main.cpp)
target_compile_features(constructors PRIVATE cxx_std_23)

add_m1_example(nrfx_minimal nrfx-minimal/main.c gpio reset)

add_m1_example(nrfx_all nrfx-all/main.c
  clock gpio gpiote grtc timer dppi uarte spim twim pwm saadc rramc watchdog
  reset retention
)

add_executable(m3_core_validation m3-core-validation/main.c)
nrfkit_example_firmware(m3_core_validation)
nrfkit_claim_resources(m3_core_validation OWNER validation RESOURCES
  timer21
)
target_link_libraries(m3_core_validation PRIVATE
  NrfKit::nrfx_clock NrfKit::nrfx_gpio NrfKit::nrfx_gpiote NrfKit::nrfx_grtc NrfKit::nrfx_timer NrfKit::nrfx_dppi NrfKit::nrfx_uarte NrfKit::nrfx_reset NrfKit::nrfx_retention
)


add_executable(m3_peripheral_validation m3-peripheral-validation/main.c)
nrfkit_example_firmware(m3_peripheral_validation)
target_link_libraries(m3_peripheral_validation PRIVATE
  NrfKit::nrfx_spim NrfKit::nrfx_twim NrfKit::nrfx_pwm NrfKit::nrfx_saadc NrfKit::nrfx_rramc NrfKit::nrfx_watchdog
)


add_executable(m3_power_validation m3-power-validation/main.c)
nrfkit_example_firmware(m3_power_validation)
target_link_libraries(m3_power_validation PRIVATE
  NrfKit::nrfx_clock NrfKit::nrfx_grtc NrfKit::nrfx_reset NrfKit::nrfx_retention
)


add_executable(m4_usb_validation m4-usb-validation/main.c)
nrfkit_example_firmware(m4_usb_validation)
nrfkit_claim_resources(m4_usb_validation OWNER usb_validation RESOURCES timer21)
nrfkit_example_usb(m4_usb_validation CLASSES hid)
target_link_libraries(m4_usb_validation PRIVATE
  NrfKit::nrfx_timer
)


add_executable(m8_combined_validation m4-usb-validation/main.c)
nrfkit_example_firmware(m8_combined_validation)
nrfkit_claim_resources(m8_combined_validation OWNER usb_validation RESOURCES timer21)
target_link_libraries(m8_combined_validation PRIVATE "NrfKit::sdc_multirole")
nrfkit_example_usb(m8_combined_validation MPSL CLASSES hid)
target_link_libraries(m8_combined_validation PRIVATE NrfKit::radio_timeslot)
target_link_libraries(m8_combined_validation PRIVATE
  NrfKit::nrfx_timer
)
target_compile_definitions(m8_combined_validation PRIVATE NRFKIT_M8_COMBINED=1)


add_executable(m5_radio_validation m5-radio-validation/main.c)
nrfkit_example_firmware(m5_radio_validation)
nrfkit_claim_resources(m5_radio_validation OWNER radio_validation RESOURCES
  dppi10.channel.0 timer10
)
target_link_libraries(m5_radio_validation PRIVATE NrfKit::radio_direct)


foreach(variant IN ITEMS multirole peripheral central)
  if(variant STREQUAL "multirole")
    set(target m6_sdc_validation)
  else()
    set(target "m6_sdc_${variant}_validation")
  endif()
  add_executable("${target}" m6-sdc-validation/main.c)
  nrfkit_example_firmware("${target}")
  target_link_libraries("${target}" PRIVATE "NrfKit::sdc_${variant}")
  target_link_libraries("${target}" PRIVATE
  NrfKit::nrfx_uarte
)

endforeach()

add_executable(m7_timeslot_retry m7-timeslot-retry/main.c)
nrfkit_example_firmware(m7_timeslot_retry)
target_link_libraries(m7_timeslot_retry PRIVATE "NrfKit::sdc_multirole")
target_link_libraries(m7_timeslot_retry PRIVATE NrfKit::radio_timeslot)


add_executable(m7_timeslot_validation m6-sdc-validation/main.c)
nrfkit_example_firmware(m7_timeslot_validation)
target_link_libraries(m7_timeslot_validation PRIVATE "NrfKit::sdc_multirole")
target_link_libraries(m7_timeslot_validation PRIVATE NrfKit::radio_timeslot)
target_link_libraries(m7_timeslot_validation PRIVATE NrfKit::rram)
target_link_libraries(m7_timeslot_validation PRIVATE
  NrfKit::nrfx_uarte
)
target_compile_definitions(m7_timeslot_validation PRIVATE NRFKIT_M7_TIMESLOT=1)


foreach(role IN ITEMS tx rx)
  set(target "m7_timeslot_radio_${role}")
  add_executable("${target}" m7-timeslot-radio-link/main.c)
  nrfkit_example_firmware("${target}")
  string(TOUPPER "${role}" role_upper)
  target_compile_definitions("${target}" PRIVATE
    "NRFKIT_M7_TIMESLOT_LINK_${role_upper}=1"
  )
  target_link_libraries("${target}" PRIVATE "NrfKit::sdc_multirole")
  target_link_libraries("${target}" PRIVATE NrfKit::radio_timeslot)

endforeach()

foreach(role IN ITEMS tx rx)
  set(target "m5_radio_${role}")
  add_executable("${target}" m5-radio-link/main.c)
  nrfkit_example_firmware("${target}")
  string(TOUPPER "${role}" role_upper)
  target_compile_definitions("${target}" PRIVATE "NRFKIT_M5_LINK_${role_upper}=1")
  target_link_libraries("${target}" PRIVATE NrfKit::radio_direct)

endforeach()

foreach(mode IN ITEMS bt_0_6 bt_0_4)
  foreach(role IN ITEMS tx rx)
    set(target "m7_radio_${role}_4m_${mode}")
    add_executable("${target}" m5-radio-link/main.c)
    nrfkit_example_firmware("${target}")
    string(TOUPPER "${role}" role_upper)
    target_compile_definitions("${target}" PRIVATE
      "NRFKIT_M5_LINK_${role_upper}=1" NRFKIT_M7_PHY_4MBIT=1)
    if(mode STREQUAL "bt_0_4")
      target_compile_definitions("${target}" PRIVATE NRFKIT_M7_4MBIT_BT_0_4=1)
    endif()
    target_link_libraries("${target}" PRIVATE NrfKit::radio_direct)

  endforeach()
endforeach()

foreach(role IN ITEMS tx rx)
  set(target "m5_radio_${role}_1m")
  add_executable("${target}" m5-radio-link/main.c)
  nrfkit_example_firmware("${target}")
  string(TOUPPER "${role}" role_upper)
  target_compile_definitions("${target}" PRIVATE
    "NRFKIT_M5_LINK_${role_upper}=1" NRFKIT_M5_PHY_1MBIT=1)
  target_link_libraries("${target}" PRIVATE NrfKit::radio_direct)

endforeach()

set(NRFKIT_BUILD_ID "development" CACHE STRING
  "Build identifier emitted by the hardware-validation firmware"
)
if(NOT NRFKIT_BUILD_ID MATCHES "^[A-Za-z0-9._-]+$")
  message(FATAL_ERROR "NRFKIT_BUILD_ID contains an unsafe character")
endif()
add_m1_example(hardware_validation hardware-validation/main.c)
target_compile_definitions(hardware_validation PRIVATE
  NRFKIT_BUILD_ID="${NRFKIT_BUILD_ID}"
)

add_executable(linker_overlap EXCLUDE_FROM_ALL linker-overlap/main.c)
nrfkit_example_firmware(linker_overlap)

option(NRFKIT_ENABLE_HARDWARE_TESTS
  "Register the guarded M2 and M3 real-board gates" OFF
)
if(NRFKIT_ENABLE_HARDWARE_TESTS)
  if(NOT NRFKIT_TOOL)
    get_filename_component(NRFKIT_TOOL
      "${CMAKE_CURRENT_LIST_DIR}/../tools/nrfkit" ABSOLUTE
    )
  endif()
  if(NOT NRFKIT_GDB)
    message(FATAL_ERROR "NRFKIT_GDB is required for hardware tests")
  endif()
  set(normal_token "NRFKIT_BOOT ${NRFKIT_BUILD_ID}")
  add_custom_command(TARGET hardware_validation POST_BUILD
    COMMAND "${NRFKIT_TOOL}" sdk manifest
      --build-dir "$<TARGET_FILE_DIR:hardware_validation>"
      --target hardware_validation
      --expected-token "${normal_token}"
    VERBATIM
  )
  add_custom_command(TARGET fault POST_BUILD
    COMMAND "${NRFKIT_TOOL}" sdk manifest
      --build-dir "$<TARGET_FILE_DIR:fault>"
      --target fault
      --expected-token NRFKIT_FAULT
    VERBATIM
  )
  foreach(m3_target IN ITEMS
      m3_core_validation m3_peripheral_validation m3_power_validation)
    if(m3_target STREQUAL "m3_core_validation")
      set(m3_token "NRFKIT_M3_CORE PASS")
    elseif(m3_target STREQUAL "m3_peripheral_validation")
      set(m3_token "NRFKIT_M3_PERIPHERALS PASS")
    else()
      set(m3_token "NRFKIT_M3_POWER PASS")
    endif()
    add_custom_command(TARGET "${m3_target}" POST_BUILD
      COMMAND "${NRFKIT_TOOL}" sdk manifest
        --build-dir "$<TARGET_FILE_DIR:${m3_target}>"
        --target "${m3_target}"
        --expected-token "${m3_token}"
      VERBATIM
    )
  endforeach()
  add_custom_command(TARGET m4_usb_validation POST_BUILD
    COMMAND "${NRFKIT_TOOL}" sdk manifest
      --build-dir "$<TARGET_FILE_DIR:m4_usb_validation>"
      --target m4_usb_validation
      --expected-token NRFKIT_M4_USB
    VERBATIM
  )
  add_custom_command(TARGET m5_radio_validation POST_BUILD
    COMMAND "${NRFKIT_TOOL}" sdk manifest
      --build-dir "$<TARGET_FILE_DIR:m5_radio_validation>"
      --target m5_radio_validation
      --expected-token NRFKIT_M5_RADIO
    VERBATIM
  )
  foreach(target IN ITEMS m6_sdc_validation
      m6_sdc_peripheral_validation m6_sdc_central_validation)
    add_custom_command(TARGET "${target}" POST_BUILD
      COMMAND "${NRFKIT_TOOL}" sdk manifest
        --build-dir "$<TARGET_FILE_DIR:${target}>"
        --target "${target}"
        --expected-token NRFKIT_M6_SDC
        --hci-h4-hwfc-1m
      VERBATIM
    )
  endforeach()
  foreach(role IN ITEMS tx rx)
    set(target "m5_radio_${role}")
    string(TOUPPER "${role}" role_upper)
    add_custom_command(TARGET "${target}" POST_BUILD
      COMMAND "${NRFKIT_TOOL}" sdk manifest
        --build-dir "$<TARGET_FILE_DIR:${target}>"
        --target "${target}"
        --expected-token "NRFKIT_M5_${role_upper} PASS"
      VERBATIM
    )
  endforeach()
  foreach(role IN ITEMS tx rx)
    set(target "m5_radio_${role}_1m")
    string(TOUPPER "${role}" role_upper)
    add_custom_command(TARGET "${target}" POST_BUILD
      COMMAND "${NRFKIT_TOOL}" sdk manifest
        --build-dir "$<TARGET_FILE_DIR:${target}>"
        --target "${target}"
        --expected-token "NRFKIT_M5_${role_upper} PASS"
      VERBATIM
    )
  endforeach()
  foreach(mode IN ITEMS bt_0_6 bt_0_4)
    foreach(role IN ITEMS tx rx)
      set(target "m7_radio_${role}_4m_${mode}")
      string(TOUPPER "${role}" role_upper)
      add_custom_command(TARGET "${target}" POST_BUILD
        COMMAND "${NRFKIT_TOOL}" sdk manifest
          --build-dir "$<TARGET_FILE_DIR:${target}>"
          --target "${target}"
          --expected-token "NRFKIT_M7_${role_upper} PASS"
        VERBATIM
      )
    endforeach()
  endforeach()
  foreach(role IN ITEMS tx rx)
    set(target "m7_timeslot_radio_${role}")
    string(TOUPPER "${role}" role_upper)
    add_custom_command(TARGET "${target}" POST_BUILD
      COMMAND "${NRFKIT_TOOL}" sdk manifest
        --build-dir "$<TARGET_FILE_DIR:${target}>"
        --target "${target}"
        --expected-token "NRFKIT_M7_TS_${role_upper} PASS"
      VERBATIM
    )
  endforeach()
  add_custom_command(TARGET m7_timeslot_retry POST_BUILD
    COMMAND "${NRFKIT_TOOL}" sdk manifest
      --build-dir "$<TARGET_FILE_DIR:m7_timeslot_retry>"
      --target m7_timeslot_retry
      --expected-token "NRFKIT_M7_RETRY PASS"
    VERBATIM
  )
  enable_testing()
  add_test(NAME m2_hardware_gate
    COMMAND "${NRFKIT_TOOL}" m2-gate
      --normal-manifest "$<TARGET_FILE_DIR:hardware_validation>/hardware_validation.device-manifest.json"
      --fault-manifest "$<TARGET_FILE_DIR:fault>/fault.device-manifest.json"
      --gdb "${NRFKIT_GDB}"
  )
  set_tests_properties(m2_hardware_gate PROPERTIES
    LABELS hardware
    RESOURCE_LOCK nrf54lm20dk
    TIMEOUT 2400
  )
  foreach(m3_case IN ITEMS core peripheral power)
    set(m3_target "m3_${m3_case}_validation")
    add_test(NAME "m3_hardware_${m3_case}"
      COMMAND "${NRFKIT_TOOL}" run
        --manifest "$<TARGET_FILE_DIR:${m3_target}>/${m3_target}.device-manifest.json"
    )
    set_tests_properties("m3_hardware_${m3_case}" PROPERTIES
      LABELS hardware
      RESOURCE_LOCK nrf54lm20dk
      TIMEOUT 180
    )
  endforeach()
  add_test(NAME m4_hardware_usb
    COMMAND "${NRFKIT_TOOL}" m4-usb-gate
      --manifest "$<TARGET_FILE_DIR:m4_usb_validation>/m4_usb_validation.device-manifest.json"
  )
  set_tests_properties(m4_hardware_usb PROPERTIES
    LABELS "hardware;root"
    RESOURCE_LOCK nrf54lm20dk
    TIMEOUT 600
  )
  add_test(NAME m5_hardware_radio_single
    COMMAND "${NRFKIT_TOOL}" run
      --manifest "$<TARGET_FILE_DIR:m5_radio_validation>/m5_radio_validation.device-manifest.json"
  )
  set_tests_properties(m5_hardware_radio_single PROPERTIES
    LABELS hardware
    RESOURCE_LOCK nrf54lm20dk
    TIMEOUT 180
  )
endif()
