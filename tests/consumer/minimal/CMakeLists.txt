# SPDX-License-Identifier: BSD-3-Clause

cmake_minimum_required(VERSION 3.25)

project(nrfkit_minimal_consumer LANGUAGES C)

find_package(NrfKit CONFIG REQUIRED)

add_executable(minimal_consumer main.c)
target_link_libraries(minimal_consumer PRIVATE NrfKit::core)
