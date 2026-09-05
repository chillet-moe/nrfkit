# SPDX-License-Identifier: BSD-3-Clause

include_guard(GLOBAL)

function(_nrfkit_generate_template name output)
  set(input "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../templates/${name}")
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${input}")
  file(READ "${input}" content)
  string(CONFIGURE "${content}" content @ONLY)
  file(GENERATE OUTPUT "${output}" CONTENT "${content}")
endfunction()

function(_nrfkit_configure_image_layout target linker_input layout_input out_linker out_layout)
  set(sdk_root "${NrfKit_ROOT}")
  if(linker_input)
    get_filename_component(linker_script "${linker_input}" ABSOLUTE
      BASE_DIR "${CMAKE_CURRENT_SOURCE_DIR}"
    )
    get_filename_component(image_layout "${layout_input}" ABSOLUTE
      BASE_DIR "${CMAKE_CURRENT_SOURCE_DIR}"
    )
    foreach(required IN ITEMS "${linker_script}" "${image_layout}")
      if(NOT EXISTS "${required}")
        message(FATAL_ERROR "nrfkit_configure_target: missing consumer layout input: ${required}")
      endif()
    endforeach()
    file(READ "${image_layout}" image_layout_content)
    string(JSON image_layout_schema ERROR_VARIABLE image_layout_error
      GET "${image_layout_content}" schema)
    if(image_layout_error OR NOT image_layout_schema STREQUAL "nrfkit-image-layout/v1")
      message(FATAL_ERROR
        "nrfkit_configure_target: IMAGE_LAYOUT must use schema nrfkit-image-layout/v1"
      )
    endif()
    foreach(field IN ITEMS target soc core configuration_regions_allowed)
      string(JSON image_layout_${field} ERROR_VARIABLE image_layout_error
        GET "${image_layout_content}" ${field})
      if(image_layout_error)
        message(FATAL_ERROR
          "nrfkit_configure_target: IMAGE_LAYOUT is missing required field '${field}'"
        )
      endif()
    endforeach()
    if(NOT image_layout_target STREQUAL "${target}" OR
        NOT image_layout_soc STREQUAL "nrf54lm20a" OR
        NOT image_layout_core STREQUAL "cpuapp" OR
        image_layout_configuration_regions_allowed)
      message(FATAL_ERROR
        "nrfkit_configure_target: IMAGE_LAYOUT must match target ${target}, describe nrf54lm20a/cpuapp, and forbid configuration regions"
      )
    endif()
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${image_layout}")
    foreach(region IN ITEMS ram rram)
      string(JSON ${region}_origin ERROR_VARIABLE region_error
        GET "${image_layout_content}" "${region}" origin)
      if(region_error AND region STREQUAL "rram")
        set(rram_origin "")
        continue()
      endif()
      string(JSON ${region}_length ERROR_VARIABLE length_error
        GET "${image_layout_content}" "${region}" length)
      if(region_error OR length_error OR
          NOT "${${region}_origin}" MATCHES "^[0-9]+$" OR
          NOT "${${region}_length}" MATCHES "^[1-9][0-9]*$")
        message(FATAL_ERROR "nrfkit: invalid ${region} layout bounds")
      endif()
      math(EXPR ${region}_end "${${region}_origin} + ${${region}_length}")
    endforeach()
    if(ram_origin LESS 536870912 OR ram_end GREATER 537133056)
      message(FATAL_ERROR "nrfkit: RAM layout exceeds the supported LM20 range")
    endif()
    if(NOT rram_origin STREQUAL "")
      if(rram_end GREATER 2084864)
        message(FATAL_ERROR "nrfkit: RRAM layout exceeds the supported LM20 range")
      endif()
      set(load_origin "${rram_origin}")
      set(load_end "${rram_end}")
    else()
      set(load_origin "${ram_origin}")
      set(load_end "${ram_end}")
    endif()
    set(contract "${CMAKE_CURRENT_BINARY_DIR}/nrfkit/${target}/image-contract.ld")
    configure_file("${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../templates/image-contract.ld.in"
      "${contract}" @ONLY)
    target_link_options("${target}" PRIVATE "-T${contract}")
    set_property(TARGET "${target}" APPEND PROPERTY LINK_DEPENDS "${contract}")
  else()
    set(linker_script "${sdk_root}/linker/layouts/nrf54lm20a-cpuapp-standalone.ld")
    set(image_layout "")
  endif()
  set(${out_linker} "${linker_script}" PARENT_SCOPE)
  set(${out_layout} "${image_layout}" PARENT_SCOPE)
endfunction()

function(_nrfkit_add_image_artifacts target)
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

  get_target_property(consumer_image_layout "${target}" NRFKIT_IMAGE_LAYOUT)
  if(consumer_image_layout)
    file(READ "${consumer_image_layout}" layout_content)
  else()
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
      "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../templates/standalone-layout.json.in")
    file(READ "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../templates/standalone-layout.json.in" layout_template)
    string(CONFIGURE "${layout_template}" layout_content @ONLY)
  endif()
  file(GENERATE
    OUTPUT "$<TARGET_FILE_DIR:${target}>/$<TARGET_FILE_BASE_NAME:${target}>.image-layout.json"
    CONTENT "${layout_content}"
  )
endfunction()
