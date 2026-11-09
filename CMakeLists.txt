
cmake_minimum_required(VERSION 3.24)

project(
    FORGEXNative
    VERSION 1.0.0
    DESCRIPTION "FORGEX Native C++ Engine"
    LANGUAGES NONE
)

# Native C++ extension will be enabled when its binding source exists.
set(FORGEX_NATIVE_BINDING
    "${CMAKE_CURRENT_SOURCE_DIR}/native/cpp/bindings/module.cpp"
)

if(EXISTS "${FORGEX_NATIVE_BINDING}")

    enable_language(CXX)

    find_package(pybind11 CONFIG REQUIRED)

    pybind11_add_module(
        _native
        MODULE
        "${FORGEX_NATIVE_BINDING}"
    )

    target_include_directories(
        _native
        PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/native/cpp/include"
    )

    target_compile_features(
        _native
        PRIVATE
        cxx_std_20
    )

    install(
        TARGETS _native
        LIBRARY DESTINATION forgex/engine
        RUNTIME DESTINATION forgex/engine
    )

else()

    message(
        STATUS
        "FORGEX: Native C++ binding not created yet. Python package build will continue."
    )

endif()
