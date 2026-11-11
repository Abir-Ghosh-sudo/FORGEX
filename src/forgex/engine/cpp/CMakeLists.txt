cmake_minimum_required(VERSION 3.20)

project(
    forgex_engine
    VERSION 1.0.0
    DESCRIPTION "FORGEX native performance engine"
    LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(CMAKE_POSITION_INDEPENDENT_CODE ON)

option(FORGEX_BUILD_PYTHON "Build Python bindings" ON)
option(FORGEX_BUILD_TESTS "Build native tests" OFF)
option(FORGEX_ENABLE_NATIVE_OPTIMIZATION "Enable native optimizations" ON)

add_library(forgex_core STATIC
    src/core.cpp
    src/search.cpp
    src/indexer.cpp
)

target_include_directories(forgex_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

if(FORGEX_ENABLE_NATIVE_OPTIMIZATION)
    if(MSVC)
        target_compile_options(forgex_core PRIVATE /O2 /W4)
    else()
        target_compile_options(forgex_core PRIVATE -O3 -Wall -Wextra -Wpedantic)
    endif()
endif()

if(FORGEX_BUILD_PYTHON)
    find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)

    find_package(pybind11 CONFIG QUIET)

    if(NOT pybind11_FOUND)
        execute_process(
            COMMAND
                ${Python_EXECUTABLE} -m pybind11 --cmakedir
            OUTPUT_VARIABLE PYBIND11_CMAKE_DIR
            OUTPUT_STRIP_TRAILING_WHITESPACE
            RESULT_VARIABLE PYBIND11_RESULT
        )

        if(PYBIND11_RESULT EQUAL 0)
            list(APPEND CMAKE_PREFIX_PATH "${PYBIND11_CMAKE_DIR}")
            find_package(pybind11 CONFIG REQUIRED)
        else()
            message(FATAL_ERROR "pybind11 is required for Python bindings")
        endif()
    endif()

    pybind11_add_module(_native
        src/bindings.cpp
    )

    target_link_libraries(_native PRIVATE forgex_core)

    install(
        TARGETS _native
        LIBRARY DESTINATION forgex
        RUNTIME DESTINATION forgex
    )
endif()

if(FORGEX_BUILD_TESTS)
    enable_testing()

    add_executable(forgex_native_tests
        tests/test_core.cpp
    )

    target_link_libraries(
        forgex_native_tests
        PRIVATE forgex_core
    )

    add_test(
        NAME forgex_native_tests
        COMMAND forgex_native_tests
    )
endif()