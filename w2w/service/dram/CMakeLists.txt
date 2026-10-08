cmake_minimum_required(VERSION 3.18)
project(W2WDRAMBridge LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(W2W_RAMULATOR_COMMIT "72427a1bba3771564c4fb0e494ba02242fd1eaa7")
if(NOT RAMULATOR_SOURCE)
  message(FATAL_ERROR "Specify the pinned, built RAMULATOR_SOURCE")
endif()
execute_process(COMMAND git -C "${RAMULATOR_SOURCE}" rev-parse HEAD
                OUTPUT_VARIABLE actual_commit OUTPUT_STRIP_TRAILING_WHITESPACE
                COMMAND_ERROR_IS_FATAL ANY)
if(NOT actual_commit STREQUAL W2W_RAMULATOR_COMMIT)
  message(FATAL_ERROR "Ramulator source is not the registered revision")
endif()
find_package(Python 3.10 REQUIRED COMPONENTS Interpreter Development.Module)
add_subdirectory("${RAMULATOR_SOURCE}/ext/nanobind" nanobind EXCLUDE_FROM_ALL)
nanobind_add_module(_w2w_ramulator bridge.cpp)
target_include_directories(_w2w_ramulator PRIVATE
  "${RAMULATOR_SOURCE}/src" "${RAMULATOR_SOURCE}/ext/fmt/include")
target_link_libraries(_w2w_ramulator PRIVATE "${RAMULATOR_SOURCE}/libramulator.so")
target_compile_definitions(_w2w_ramulator PRIVATE
  W2W_RAMULATOR_COMMIT="${W2W_RAMULATOR_COMMIT}")
set_target_properties(_w2w_ramulator PROPERTIES BUILD_RPATH "${RAMULATOR_SOURCE}")
