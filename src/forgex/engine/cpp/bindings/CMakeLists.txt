
if(NOT FORGEX_BUILD_PYTHON)
    return()
endif()

if(NOT COMMAND pybind11_add_module)
    message(FATAL_ERROR "pybind11_add_module is unavailable.")
endif()

pybind11_add_module(
    _native
    MODULE
    bindings.cpp
)

target_link_libraries(
    _native
    PRIVATE
        forgex_core
        forgex_parser
        forgex_search
        forgex_indexing
)

target_compile_features(
    _native
    PRIVATE
        cxx_std_20
)

if(MSVC)
    target_compile_options(
        _native
        PRIVATE
            /W4
            /permissive-
    )
else()
    target_compile_options(
        _native
        PRIVATE
            -Wall
            -Wextra
            -Wpedantic
    )
endif()

install(
    TARGETS _native
    LIBRARY DESTINATION forgex
    RUNTIME DESTINATION forgex
)

message(STATUS "FORGEX: Native Python extension configured.")
