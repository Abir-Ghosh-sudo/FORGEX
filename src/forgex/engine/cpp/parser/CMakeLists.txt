add_library(forgex_parser STATIC
    parser.cpp
)

target_include_directories(forgex_parser
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}
)

target_link_libraries(forgex_parser
    PUBLIC
        forgex_core
)

target_compile_features(forgex_parser PUBLIC cxx_std_20)

set_target_properties(forgex_parser PROPERTIES
    POSITION_INDEPENDENT_CODE ON
)

if(MSVC)
    target_compile_options(forgex_parser PRIVATE /O2 /W4 /permissive-)
else()
    target_compile_options(forgex_parser PRIVATE
        -O3 -Wall -Wextra -Wpedantic
    )
endif()