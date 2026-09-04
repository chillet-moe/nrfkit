# SPDX-License-Identifier: BSD-3-Clause

cmake_minimum_required(VERSION 3.25)
project(nrfkit_m1_examples LANGUAGES C CXX ASM)

find_package(NrfKit CONFIG REQUIRED)

function(add_m1_example name source)
  add_executable("${name}" "${source}")
  nrfkit_configure_target("${name}"
    SOC nrf54lm20a
    CORE cpuapp
    BOARD nrf54lm20dk
    RUNTIME freestanding
  )
  if(ARGN)
    nrfkit_enable_nrfx("${name}" DRIVERS ${ARGN})
  endif()
  nrfkit_finalize_target("${name}")
endfunction()

add_m1_example(empty empty/main.c)
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
nrfkit_configure_target(m3_core_validation
  SOC nrf54lm20a CORE cpuapp BOARD nrf54lm20dk RUNTIME freestanding
)
nrfkit_claim_resources(m3_core_validation OWNER validation RESOURCES
  timer21
)
nrfkit_enable_nrfx(m3_core_validation DRIVERS
  clock gpio gpiote grtc timer dppi uarte reset retention
)
nrfkit_finalize_target(m3_core_validation)

add_executable(m3_peripheral_validation m3-peripheral-validation/main.c)
nrfkit_configure_target(m3_peripheral_validation
  SOC nrf54lm20a CORE cpuapp BOARD nrf54lm20dk RUNTIME freestanding
)
nrfkit_enable_nrfx(m3_peripheral_validation DRIVERS
  spim twim pwm saadc rramc watchdog
)
nrfkit_finalize_target(m3_peripheral_validation)

add_executable(m3_power_validation m3-power-validation/main.c)
nrfkit_configure_target(m3_power_validation
  SOC nrf54lm20a CORE cpuapp BOARD nrf54lm20dk RUNTIME freestanding
)
nrfkit_enable_nrfx(m3_power_validation DRIVERS
  clock grtc reset retention
)
nrfkit_finalize_target(m3_power_validation)

add_executable(m4_usb_validation m4-usb-validation/main.c)
nrfkit_configure_target(m4_usb_validation
  SOC nrf54lm20a CORE cpuapp BOARD nrf54lm20dk RUNTIME freestanding
)
nrfkit_claim_resources(m4_usb_validation OWNER usb_validation RESOURCES timer21)
nrfkit_enable_usb_device(m4_usb_validation STACK cherryusb CLASSES hid)
nrfkit_enable_nrfx(m4_usb_validation DRIVERS timer)
nrfkit_finalize_target(m4_usb_validation)

add_executable(m5_radio_validation m5-radio-validation/main.c)
nrfkit_configure_target(m5_radio_validation
  SOC nrf54lm20a CORE cpuapp BOARD nrf54lm20dk RUNTIME freestanding
)
nrfkit_claim_resources(m5_radio_validation OWNER radio_validation RESOURCES
  dppi10.channel.0 timer10
)
nrfkit_enable_radio(m5_radio_validation)
nrfkit_finalize_target(m5_radio_validation)

foreach(variant IN ITEMS multirole peripheral central)
  if(variant STREQUAL "multirole")
    set(target m6_sdc_validation)
  else()
    set(target "m6_sdc_${variant}_validation")
  endif()
  add_executable("${target}" m6-sdc-validation/main.c)
  nrfkit_configure_target("${target}"
    SOC nrf54lm20a CORE cpuapp BOARD nrf54lm20dk RUNTIME freestanding
  )
  nrfkit_enable_sdc("${target}" VARIANT "${variant}")
  nrfkit_enable_nrfx("${target}" DRIVERS uarte)
  nrfkit_finalize_target("${target}")
endforeach()

add_executable(m7_timeslot_validation m6-sdc-validation/main.c)
nrfkit_configure_target(m7_timeslot_validation
  SOC nrf54lm20a CORE cpuapp BOARD nrf54lm20dk RUNTIME freestanding
)
nrfkit_enable_sdc(m7_timeslot_validation VARIANT multirole)
nrfkit_enable_mpsl_timeslot(m7_timeslot_validation)
nrfkit_enable_nrfx(m7_timeslot_validation DRIVERS uarte)
target_compile_definitions(m7_timeslot_validation PRIVATE NRFKIT_M7_TIMESLOT=1)
nrfkit_finalize_target(m7_timeslot_validation)

foreach(role IN ITEMS tx rx)
  set(target "m5_radio_${role}")
  add_executable("${target}" m5-radio-link/main.c)
  nrfkit_configure_target("${target}"
    SOC nrf54lm20a CORE cpuapp BOARD nrf54lm20dk RUNTIME freestanding
  )
  string(TOUPPER "${role}" role_upper)
  target_compile_definitions("${target}" PRIVATE "NRFKIT_M5_LINK_${role_upper}=1")
  nrfkit_enable_radio("${target}")
  nrfkit_finalize_target("${target}")
endforeach()

foreach(mode IN ITEMS bt_0_6 bt_0_4)
  foreach(role IN ITEMS tx rx)
    set(target "m7_radio_${role}_4m_${mode}")
    add_executable("${target}" m5-radio-link/main.c)
    nrfkit_configure_target("${target}"
      SOC nrf54lm20a CORE cpuapp BOARD nrf54lm20dk RUNTIME freestanding
    )
    string(TOUPPER "${role}" role_upper)
    target_compile_definitions("${target}" PRIVATE
      "NRFKIT_M5_LINK_${role_upper}=1" NRFKIT_M7_PHY_4MBIT=1)
    if(mode STREQUAL "bt_0_4")
      target_compile_definitions("${target}" PRIVATE NRFKIT_M7_4MBIT_BT_0_4=1)
    endif()
    nrfkit_enable_radio("${target}")
    nrfkit_finalize_target("${target}")
  endforeach()
endforeach()

foreach(role IN ITEMS tx rx)
  set(target "m5_radio_${role}_1m")
  add_executable("${target}" m5-radio-link/main.c)
  nrfkit_configure_target("${target}"
    SOC nrf54lm20a CORE cpuapp BOARD nrf54lm20dk RUNTIME freestanding
  )
  string(TOUPPER "${role}" role_upper)
  target_compile_definitions("${target}" PRIVATE
    "NRFKIT_M5_LINK_${role_upper}=1" NRFKIT_M5_PHY_1MBIT=1)
  nrfkit_enable_radio("${target}")
  nrfkit_finalize_target("${target}")
endforeach()

if(NRF_SOFTDEVICE_ROOT AND NRF_OBERON_ROOT)
  if(NRF_BM_ROOT)
    # The S115 equivalence target obtains the version-locked sample main.c from
    # the audited nRF-BM input. No project-owned application handler is used.
    add_executable(m6_ble_official_baseline)
    nrfkit_configure_target(m6_ble_official_baseline
      SOC nrf54lm20a CORE cpuapp BOARD nrf54lm20dk RUNTIME freestanding)
    _nrfkit_enable_s115_baseline(m6_ble_official_baseline VERSION 10.0.1
      SOURCE_DIR "${NRF_SOFTDEVICE_ROOT}"
      OBERON_DIR "${NRF_OBERON_ROOT}"
      NRF_BM_DIR "${NRF_BM_ROOT}")
    nrfkit_finalize_target(m6_ble_official_baseline)
  endif()
endif()

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
nrfkit_configure_target(linker_overlap
  SOC nrf54lm20a
  CORE cpuapp
  BOARD nrf54lm20dk
  RUNTIME freestanding
)

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
  if(TARGET m6_ble_official_baseline)
    add_custom_command(TARGET m6_ble_official_baseline POST_BUILD
      COMMAND "${NRFKIT_TOOL}" sdk manifest
        --build-dir "$<TARGET_FILE_DIR:m6_ble_official_baseline>"
        --target m6_ble_official_baseline
        --expected-token "BLE HIDS Mouse sample initialized"
      VERBATIM
    )
  endif()
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
