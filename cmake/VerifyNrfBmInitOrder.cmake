# SPDX-License-Identifier: BSD-3-Clause

if(NOT DEFINED NRFKIT_MAP_FILE OR NOT EXISTS "${NRFKIT_MAP_FILE}")
  message(FATAL_ERROR "nRF-BM initialization audit map is missing: ${NRFKIT_MAP_FILE}")
endif()

file(READ "${NRFKIT_MAP_FILE}" map_contents)
set(expected_entries
  "bm_port.c.obj:(.init_array.101)"
  "gpiote.c.obj:(.init_array.201)"
  "bm_timer.c.obj:(.init_array.202)"
  "nrf_sdh.c.obj:(.init_array.203)"
  "irq_connect.c.obj:(.init_array.204)"
)

set(previous_position -1)
foreach(entry IN LISTS expected_entries)
  string(FIND "${map_contents}" "${entry}" position)
  if(position EQUAL -1)
    message(FATAL_ERROR "nRF-BM initialization audit is missing ${entry}")
  endif()
  if(NOT previous_position EQUAL -1 AND position LESS_EQUAL previous_position)
    message(FATAL_ERROR "nRF-BM initialization order drifted at ${entry}")
  endif()
  set(previous_position "${position}")
endforeach()

string(FIND "${map_contents}" "CallSoftDeviceResetHandler" reset_handler_position)
if(reset_handler_position EQUAL -1)
  message(FATAL_ERROR "nRF-BM IRQ forwarding reset handler was removed from the image")
endif()

message(STATUS "Verified nRF-BM board/application initialization order")
