# SPDX-License-Identifier: BSD-3-Clause

cmake_minimum_required(VERSION 3.25)

project(NrfCMakeSdk VERSION 0.0.0 LANGUAGES NONE)

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)

add_library(nrf_cmake_sdk_core INTERFACE)
add_library(NrfCMakeSdk::core ALIAS nrf_cmake_sdk_core)
set_target_properties(nrf_cmake_sdk_core PROPERTIES EXPORT_NAME core)
target_include_directories(nrf_cmake_sdk_core INTERFACE
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
)

install(TARGETS nrf_cmake_sdk_core EXPORT NrfCMakeSdkTargets)
install(DIRECTORY include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(DIRECTORY
  include
  boards
  linker
  runtime
  third_party
  DESTINATION ${CMAKE_INSTALL_DATADIR}/nrf-cmake-sdk
)
install(DIRECTORY cmake/toolchains
  DESTINATION ${CMAKE_INSTALL_DATADIR}/nrf-cmake-sdk/cmake
)
install(FILES cmake/modules/NrfSdkFirmware.cmake
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/NrfCMakeSdk
)
install(EXPORT NrfCMakeSdkTargets
  FILE NrfCMakeSdkTargets.cmake
  NAMESPACE NrfCMakeSdk::
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/NrfCMakeSdk
)

configure_package_config_file(
  cmake/NrfCMakeSdkConfig.cmake.in
  ${CMAKE_CURRENT_BINARY_DIR}/NrfCMakeSdkConfig.cmake
  INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/NrfCMakeSdk
)
write_basic_package_version_file(
  ${CMAKE_CURRENT_BINARY_DIR}/NrfCMakeSdkConfigVersion.cmake
  VERSION ${PROJECT_VERSION}
  COMPATIBILITY SameMajorVersion
)
install(FILES
  ${CMAKE_CURRENT_BINARY_DIR}/NrfCMakeSdkConfig.cmake
  ${CMAKE_CURRENT_BINARY_DIR}/NrfCMakeSdkConfigVersion.cmake
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/NrfCMakeSdk
)
