# SPDX-License-Identifier: BSD-3-Clause

include_guard(GLOBAL)

function(nrfkit_enable_usb_port target)
  _nrfkit_enable_usb("${target}" PORT_ONLY ${ARGN})
endfunction()

function(nrfkit_enable_usb_device target)
  _nrfkit_enable_usb("${target}" ${ARGN})
endfunction()

function(_nrfkit_enable_usb target)
  _nrfkit_require_open_target("${target}" nrfkit_enable_usb_device)

  cmake_parse_arguments(PARSE_ARGV 1 ARG "PORT_ONLY" "STACK;SOURCE_DIR"
    "CLASSES;IN_ENDPOINT_MAX_PACKET_SIZES"
  )
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
  if(NOT ARG_IN_ENDPOINT_MAX_PACKET_SIZES)
    # Preserve the validated M4 oracle allocation for EP1 bulk and EP2 HID.
    set(ARG_IN_ENDPOINT_MAX_PACKET_SIZES 512 256)
  endif()
  list(LENGTH ARG_IN_ENDPOINT_MAX_PACKET_SIZES in_endpoint_count)
  if(in_endpoint_count GREATER 15)
    message(FATAL_ERROR
      "nrfkit_enable_usb_device: at most 15 IN endpoint packet sizes are supported"
    )
  endif()
  set(tx_fifo_words 16)
  set(tx_fifo_total 16)
  foreach(packet_size IN LISTS ARG_IN_ENDPOINT_MAX_PACKET_SIZES)
    if(NOT packet_size MATCHES "^[1-9][0-9]*$" OR packet_size GREATER 1024)
      message(FATAL_ERROR
        "nrfkit_enable_usb_device: invalid IN endpoint max packet size '${packet_size}'"
      )
    endif()
    math(EXPR words "(${packet_size} + 3) / 4")
    if(words LESS 16)
      set(words 16)
    endif()
    list(APPEND tx_fifo_words "${words}")
    math(EXPR tx_fifo_total "${tx_fifo_total} + ${words}")
  endforeach()
  while(in_endpoint_count LESS 15)
    list(APPEND tx_fifo_words 0)
    math(EXPR in_endpoint_count "${in_endpoint_count} + 1")
  endwhile()
  math(EXPR configured_fifo_words "760 + ${tx_fifo_total}")
  if(configured_fifo_words GREATER 3040)
    message(FATAL_ERROR
      "nrfkit_enable_usb_device: RX/TX FIFO allocation exceeds the LM20 3040-word capacity"
    )
  endif()
  string(JOIN ", " tx_fifo_initializer ${tx_fifo_words})
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
  configure_file("${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../templates/usb_config.h.in"
    "${config_dir}/usb_config.h" @ONLY)
  target_include_directories("${target}" PRIVATE
    "${config_dir}"
    "${cherryusb}/common"
    "${cherryusb}/core"
    "${cherryusb}/port/dwc2"
  )
  target_sources("${target}" PRIVATE
    "${NrfKit_ROOT}/src/usb/nrf54l/usb_dc.c"
    "${NrfKit_ROOT}/src/usb/nrf54l/usb_glue_dwc2.c"
  )
  if(NOT ARG_PORT_ONLY)
    target_sources("${target}" PRIVATE "${cherryusb}/core/usbd_core.c")
  endif()
  if("hid" IN_LIST ARG_CLASSES)
    target_include_directories("${target}" PRIVATE "${cherryusb}/class/hid")
    if(NOT ARG_PORT_ONLY)
      target_sources("${target}" PRIVATE "${cherryusb}/class/hid/usbd_hid.c")
    endif()
  endif()
  set_target_properties("${target}" PROPERTIES
    NRFKIT_USB_DEVICE_STACK cherryusb
    NRFKIT_USB_DEVICE_SOURCE "${cherryusb}"
    NRFKIT_USB_DEVICE_CLASSES "${ARG_CLASSES}"
    NRFKIT_NRFX_HEADERS_REQUIRED TRUE
  )
endfunction()
