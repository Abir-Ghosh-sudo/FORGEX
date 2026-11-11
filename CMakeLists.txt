
cmake_minimum_required(VERSION 3.24)

project(
    FORGEX
    VERSION 1.0.0
    DESCRIPTION "FORGEX Native AI Coding Engine"
    LANGUAGES NONE
)

option(FORGEX_BUILD_PYTHON "Build Python native extension" ON)
option(FORGEX_BUILD_TESTS "Build native tests" OFF)
option(FORGEX_ENABLE_NATIVE_OPTIMIZATION "Enable native optimizations" ON)

include(CheckLanguage)
check_language(CXX)

if(CMAKE_CXX_COMPILER)
    enable_language(CXX)
    set(CMAKE_CXX_STANDARD 20)
    set(CMAKE_CXX_STANDARD_REQUIRED ON)
    set(CMAKE_CXX_EXTENSIONS OFF)
    set(CMAKE_POSITION_INDEPENDENT_CODE ON)
else()
    message(WARNING "No C++20 compiler found. Building pure-Python FORGEX without native extension.")
    set(FORGEX_BUILD_PYTHON OFF)
endif()

if(FORGEX_BUILD_PYTHON)
    find_package(
        Python
        COMPONENTS Interpreter Development.Module
        QUIET
    )

    if(Python_FOUND)
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

            if(PYBIND11_RESULT EQUAL 0 AND EXISTS "${PYBIND11_CMAKE_DIR}")
                find_package(
                    pybind11
                    CONFIG
                    QUIET
                    PATHS "${PYBIND11_CMAKE_DIR}"
                    NO_DEFAULT_PATH
                )
            endif()
        endif()

        if(pybind11_FOUND)
            message(STATUS "FORGEX Python: ${Python_EXECUTABLE}")
            message(STATUS "FORGEX pybind11: ${pybind11_DIR}")
            add_subdirectory(src/forgex/engine/cpp)
        else()
            message(WARNING "pybind11 not found. Skipping native extension build; using pure Python fallback.")
        endif()
    else()
        message(WARNING "Python development headers not found. Skipping native extension build; using pure Python fallback.")
    endif()
endif()
