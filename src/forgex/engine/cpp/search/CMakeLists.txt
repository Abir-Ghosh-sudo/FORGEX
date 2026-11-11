add_library(forgex_search STATIC
    search.cpp
)

target_include_directories(forgex_search
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}
)

target_link_libraries(forgex_search
    PUBLIC
        forgex_core
)

target_compile_features(forgex_search PUBLIC cxx_std_20)

set_target_properties(forgex_search PROPERTIES
    POSITION_INDEPENDENT_CODE ON
)

if(MSVC)
    target_compile_options(forgex_search PRIVATE
        /O2
        /W4
        /permissive-
    )
else()
    target_compile_options(forgex_search PRIVATE
        -O3
        -Wall
        -Wextra
        -Wpedantic
    )
endif()