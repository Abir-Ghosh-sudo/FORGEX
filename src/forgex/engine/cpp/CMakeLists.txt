
# FORGEX Native Engine Components

if(NOT TARGET forgex_core)

    add_subdirectory(core)

endif()

if(NOT TARGET forgex_parser)

    add_subdirectory(parser)

endif()

if(NOT TARGET forgex_search)

    add_subdirectory(search)

endif()

if(NOT TARGET forgex_indexing)

    add_subdirectory(indexing)

endif()

if(FORGEX_BUILD_PYTHON)

    add_subdirectory(bindings)

endif()

message(STATUS "FORGEX: Native engine components configured.")
