// SPDX-License-Identifier: BSD-3-Clause

#include <nrf_cmake_sdk/version.h>

#if NRF_CMAKE_SDK_VERSION_MAJOR != 0
#error "unexpected nrf-cmake-sdk major version"
#endif

int main(void)
{
    return NRF_CMAKE_SDK_VERSION_MINOR;
}
