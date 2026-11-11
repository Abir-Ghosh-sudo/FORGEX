
add_library(forgex_indexing STATIC
    indexing.cpp
    index_store.cpp
)

target_include_directories(forgex_indexing
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}
)

target_link_libraries(forgex_indexing
    PUBLIC
        forgex_core
)

target_compile_features(forgex_indexing PUBLIC cxx_std_20)

set_target_properties(forgex_indexing PROPERTIES
    POSITION_INDEPENDENT_CODE ON
)

if(MSVC)
    target_compile_options(forgex_indexing PRIVATE
        /O2
        /W4
        /permissive-
    )
else()
    target_compile_options(forgex_indexing PRIVATE
        -O3
        -Wall
        -Wextra
        -Wpedantic
    )
endif()
