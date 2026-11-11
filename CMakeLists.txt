
cmake_minimum_required(VERSION 3.24)

project(
    FORGEX
    VERSION 1.0.0
    DESCRIPTION "FORGEX Native AI Coding Engine"
    LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(CMAKE_POSITION_INDEPENDENT_CODE ON)

option(FORGEX_BUILD_PYTHON "Build Python native extension" ON)
option(FORGEX_BUILD_TESTS "Build native tests" OFF)
option(FORGEX_ENABLE_NATIVE_OPTIMIZATION "Enable native optimizations" ON)

if(FORGEX_BUILD_PYTHON)

    find_package(
        Python
        COMPONENTS Interpreter Development.Module
        REQUIRED
    )

    find_package(pybind11 CONFIG QUIET)

    if(NOT pybind11_FOUND)

        execute_process(
            COMMAND
                "${Python_EXECUTABLE}"
                -m pybind11
                --cmakedir
            OUTPUT_VARIABLE PYBIND11_CMAKE_DIR
            OUTPUT_STRIP_TRAILING_WHITESPACE
            RESULT_VARIABLE PYBIND11_RESULT
        )

        if(NOT PYBIND11_RESULT EQUAL 0)
            message(FATAL_ERROR
                "Could not locate pybind11. Install it using pip."
            )
        endif()

        find_package(
            pybind11
            CONFIG
            REQUIRED
            PATHS "${PYBIND11_CMAKE_DIR}"
            NO_DEFAULT_PATH
        )

    endif()

    message(STATUS "FORGEX Python: ${Python_EXECUTABLE}")
    message(STATUS "FORGEX pybind11: ${pybind11_DIR}")

endif()

add_subdirectory(
    src/forgex/engine/cpp
)
