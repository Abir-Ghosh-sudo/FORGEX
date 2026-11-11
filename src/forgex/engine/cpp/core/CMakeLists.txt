add_library(forgex_core STATIC
    core.cpp
)

target_include_directories(forgex_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}
)

target_compile_features(forgex_core PUBLIC cxx_std_20)

set_target_properties(forgex_core PROPERTIES
    POSITION_INDEPENDENT_CODE ON
)

if(MSVC)
    target_compile_options(forgex_core PRIVATE
        /O2
        /W4
        /permissive-
    )
else()
    target_compile_options(forgex_core PRIVATE
        -O3
        -Wall
        -Wextra
        -Wpedantic
    )
endif()