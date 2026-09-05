# SPDX-License-Identifier: BSD-3-Clause

include_guard(GLOBAL)

set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR arm)
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)

set(NRF_LLVM_ROOT "" CACHE PATH "LLVM installation prefix")
set(NRF_GNU_ARM_CXX_ROOT "" CACHE PATH
  "Optional GNU Arm installation prefix supplying freestanding C++ headers")
find_program(CMAKE_C_COMPILER NAMES clang HINTS "${NRF_LLVM_ROOT}" PATH_SUFFIXES bin REQUIRED)
find_program(CMAKE_CXX_COMPILER NAMES clang++ HINTS "${NRF_LLVM_ROOT}" PATH_SUFFIXES bin REQUIRED)
find_program(CMAKE_ASM_COMPILER NAMES clang HINTS "${NRF_LLVM_ROOT}" PATH_SUFFIXES bin REQUIRED)
find_program(CMAKE_LINKER NAMES ld.lld HINTS "${NRF_LLVM_ROOT}" PATH_SUFFIXES bin REQUIRED)
find_program(CMAKE_OBJCOPY NAMES llvm-objcopy HINTS "${NRF_LLVM_ROOT}" PATH_SUFFIXES bin REQUIRED)
find_program(CMAKE_READELF NAMES llvm-readelf HINTS "${NRF_LLVM_ROOT}" PATH_SUFFIXES bin REQUIRED)
find_program(CMAKE_OBJDUMP NAMES llvm-objdump HINTS "${NRF_LLVM_ROOT}" PATH_SUFFIXES bin REQUIRED)

set(CMAKE_C_COMPILER_TARGET arm-none-eabi)
set(CMAKE_CXX_COMPILER_TARGET arm-none-eabi)
set(CMAKE_ASM_COMPILER_TARGET arm-none-eabi)

if(NRF_GNU_ARM_CXX_ROOT)
  set(_nrf_gnu_arm_sysroot "${NRF_GNU_ARM_CXX_ROOT}/arm-none-eabi")
  if(NOT IS_DIRECTORY "${_nrf_gnu_arm_sysroot}/include/c++")
    message(FATAL_ERROR
      "NRF_GNU_ARM_CXX_ROOT does not contain arm-none-eabi/include/c++: ${NRF_GNU_ARM_CXX_ROOT}"
    )
  endif()
  file(GLOB _nrf_gnu_arm_cxx_candidates LIST_DIRECTORIES TRUE
    "${_nrf_gnu_arm_sysroot}/include/c++/*"
  )
  set(_nrf_gnu_arm_cxx_versions "")
  foreach(candidate IN LISTS _nrf_gnu_arm_cxx_candidates)
    if(IS_DIRECTORY "${candidate}" AND
        EXISTS "${candidate}/arm-none-eabi/bits/c++config.h")
      list(APPEND _nrf_gnu_arm_cxx_versions "${candidate}")
    endif()
  endforeach()
  list(LENGTH _nrf_gnu_arm_cxx_versions _nrf_gnu_arm_cxx_version_count)
  if(NOT _nrf_gnu_arm_cxx_version_count EQUAL 1)
    message(FATAL_ERROR
      "NRF_GNU_ARM_CXX_ROOT must contain exactly one usable Arm C++ header version"
    )
  endif()
  list(GET _nrf_gnu_arm_cxx_versions 0 _nrf_gnu_arm_cxx_root)
  list(APPEND CMAKE_CXX_STANDARD_INCLUDE_DIRECTORIES
    "${_nrf_gnu_arm_cxx_root}"
    "${_nrf_gnu_arm_cxx_root}/arm-none-eabi"
    "${_nrf_gnu_arm_cxx_root}/backward"
  )
  string(APPEND CMAKE_CXX_FLAGS_INIT
    " --sysroot=\"${_nrf_gnu_arm_sysroot}\" -DNRFKIT_USE_GNU_ARM_CXX_HEADERS=1"
  )
  unset(_nrf_gnu_arm_cxx_candidates)
  unset(_nrf_gnu_arm_cxx_versions)
  unset(_nrf_gnu_arm_cxx_version_count)
  unset(_nrf_gnu_arm_cxx_root)
  unset(_nrf_gnu_arm_sysroot)
endif()
