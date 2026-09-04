# SPDX-License-Identifier: BSD-3-Clause

cmake_minimum_required(VERSION 3.25)

project(NrfKit VERSION 0.0.0 LANGUAGES NONE)

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)

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
  boards
  linker
  patches
  radio
  runtime
  softdevice
  third_party
  usb
  DESTINATION ${CMAKE_INSTALL_DATADIR}/nrfkit
)
install(DIRECTORY external/nrfx/
  DESTINATION ${CMAKE_INSTALL_DATADIR}/nrfkit/external/nrfx
  PATTERN ".git" EXCLUDE
)
install(DIRECTORY external/cherryusb/
  DESTINATION ${CMAKE_INSTALL_DATADIR}/nrfkit/external/cherryusb
  PATTERN ".git" EXCLUDE
)
install(DIRECTORY cmake/toolchains
  DESTINATION ${CMAKE_INSTALL_DATADIR}/nrfkit/cmake
)
install(FILES cmake/modules/NrfKitFirmware.cmake
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
