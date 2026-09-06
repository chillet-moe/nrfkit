# SPDX-License-Identifier: BSD-3-Clause

cmake_minimum_required(VERSION 3.25)

include(cmake/modules/NrfKitVersion.cmake)
_nrfkit_read_version("${CMAKE_CURRENT_SOURCE_DIR}/include/nrfkit/version.h")
project(NrfKit VERSION "${NrfKit_VERSION}" LANGUAGES NONE)

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)
set(NrfKit_ROOT "${CMAKE_CURRENT_SOURCE_DIR}")
include(cmake/modules/NrfKitDependencies.cmake)

add_library(nrfkit_core INTERFACE)
add_library(NrfKit::core ALIAS nrfkit_core)
set_target_properties(nrfkit_core PROPERTIES EXPORT_NAME core)
target_include_directories(nrfkit_core INTERFACE
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
)

install(TARGETS nrfkit_core EXPORT NrfKitTargets)
install(DIRECTORY include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(DIRECTORY
  include
  src
  linker
  patches
  DESTINATION ${CMAKE_INSTALL_DATADIR}/nrfkit
)
set(nrfx_install_root "${CMAKE_INSTALL_DATADIR}/nrfkit/external/nrfx")
_nrfkit_read_selection(nrfx_selected_files)
foreach(relative IN LISTS nrfx_selected_files)
  get_filename_component(directory "${relative}" DIRECTORY)
  install(FILES "external/nrfx/${relative}"
    DESTINATION "${nrfx_install_root}/${directory}")
endforeach()

set(cmsis_install_root "${CMAKE_INSTALL_DATADIR}/nrfkit/external/cmsis")
_nrfkit_read_cmsis_selection(cmsis_selected_files)
foreach(relative IN LISTS cmsis_selected_files)
  get_filename_component(directory "${relative}" DIRECTORY)
  install(FILES "external/cmsis/${relative}"
    DESTINATION "${cmsis_install_root}/${directory}")
endforeach()

# Example-owned USB configurations are separate from the built-in port target.
install(DIRECTORY examples/common/
  DESTINATION ${CMAKE_INSTALL_DATADIR}/nrfkit/examples/common)

set(cherryusb_install_root "${CMAKE_INSTALL_DATADIR}/nrfkit/external/cherryusb")
install(FILES external/cherryusb/LICENSE
  DESTINATION "${cherryusb_install_root}"
)
install(DIRECTORY
  external/cherryusb/common
  external/cherryusb/core
  DESTINATION "${cherryusb_install_root}"
)
install(DIRECTORY external/cherryusb/port/dwc2
  DESTINATION "${cherryusb_install_root}/port"
)
install(DIRECTORY external/cherryusb/class/hid
  DESTINATION "${cherryusb_install_root}/class"
)
# Install exactly the same selected input set that consumer configure validates.
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/docs/provenance/sources.lock" source_lock)
string(JSON nrfxlib_files GET "${source_lock}" audited_sources sdk-nrfxlib-3.4.0 files)
string(JSON nrfxlib_file_count LENGTH "${nrfxlib_files}")
math(EXPR nrfxlib_last_file "${nrfxlib_file_count} - 1")
foreach(index RANGE 0 ${nrfxlib_last_file})
  string(JSON relative MEMBER "${nrfxlib_files}" ${index})
  get_filename_component(directory "${relative}" DIRECTORY)
  install(FILES "external/sdk-nrfxlib/${relative}"
    DESTINATION "${CMAKE_INSTALL_DATADIR}/nrfkit/external/sdk-nrfxlib/${directory}")
endforeach()
install(FILES docs/provenance/sources.lock docs/provenance/vendor-imports.lock
  DESTINATION ${CMAKE_INSTALL_DATADIR}/nrfkit/docs/provenance)
install(FILES README.md CHANGELOG.md LICENSE
  DESTINATION ${CMAKE_INSTALL_DATADIR}/doc/nrfkit)
install(DIRECTORY cmake/toolchains
  DESTINATION ${CMAKE_INSTALL_DATADIR}/nrfkit/cmake
)
install(FILES cmake/nrfx-selection.txt cmake/cmsis-selection.txt
  DESTINATION ${CMAKE_INSTALL_DATADIR}/nrfkit/cmake)
install(DIRECTORY cmake/modules
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/NrfKit
)
install(EXPORT NrfKitTargets
  FILE NrfKitTargets.cmake
  NAMESPACE NrfKit::
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/NrfKit
)

configure_package_config_file(
  cmake/NrfKitConfig.cmake.in
  ${CMAKE_CURRENT_BINARY_DIR}/NrfKitConfig.cmake
  INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/NrfKit
)
write_basic_package_version_file(
  ${CMAKE_CURRENT_BINARY_DIR}/NrfKitConfigVersion.cmake
  VERSION ${PROJECT_VERSION}
  COMPATIBILITY SameMajorVersion
)
install(FILES
  ${CMAKE_CURRENT_BINARY_DIR}/NrfKitConfig.cmake
  ${CMAKE_CURRENT_BINARY_DIR}/NrfKitConfigVersion.cmake
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/NrfKit
)

unset(nrfx_install_root)
unset(cmsis_install_root)
unset(cherryusb_install_root)

set(CPACK_GENERATOR TGZ)
set(CPACK_PACKAGE_NAME nrfkit)
set(CPACK_PACKAGE_VENDOR "nrfkit contributors")
set(CPACK_PACKAGE_VERSION "${NrfKit_VERSION_STRING}")
set(CPACK_PACKAGE_FILE_NAME "nrfkit-${NrfKit_VERSION_STRING}")
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY
  "Community bare-metal CMake SDK for nRF54LM20A")
set(CPACK_PACKAGE_CHECKSUM SHA256)
set(CPACK_RESOURCE_FILE_LICENSE "${CMAKE_CURRENT_SOURCE_DIR}/LICENSE")
set(CPACK_RESOURCE_FILE_README "${CMAKE_CURRENT_SOURCE_DIR}/README.md")
set(CPACK_INCLUDE_TOPLEVEL_DIRECTORY ON)
include(CPack)
