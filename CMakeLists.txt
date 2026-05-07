cmake_minimum_required(VERSION 3.15)

# -----------------------------
# Define The Project
# -----------------------------
project(scgraph LANGUAGES NONE)

# -----------------------------
# Build Options
# -----------------------------
option(SKIP_CPP_BUILD "Skip C++ extension module building" OFF)

# -----------------------------
# C++ detection
# -----------------------------
include(CheckLanguage)
check_language(CXX)

if(CMAKE_CXX_COMPILER)
    enable_language(CXX)
endif()


if(SKIP_CPP_BUILD)

        message(STATUS 
            "C++ build skipped. Using pure python version. Performance will be reduced."
        )

elseif(NOT CMAKE_CXX_COMPILER_LOADED)

    message(WARNING
        "No usable C++ compiler detected. Using pure python version. Performance will be reduced."
    )

else()

    message(STATUS 
        "C++ compiler detected: Building compiled extension."
    )

    # -----------------------------
    # Set C++ standard
    # -----------------------------
    set(CMAKE_CXX_STANDARD 20)
    set(CMAKE_CXX_STANDARD_REQUIRED ON)

    # -----------------------------
    # OPTIMIZATION FLAGS
    # -----------------------------
    set(CMAKE_BUILD_TYPE Release)
    if(MSVC)
        set(CMAKE_CXX_FLAGS_RELEASE "/O2 /DNDEBUG")
    else()
        set(CMAKE_CXX_FLAGS_RELEASE "-O3 -march=native -DNDEBUG")
    endif()

    # -----------------------------
    # Find Packages
    # -----------------------------
    find_package(Python 3.10 COMPONENTS Interpreter Development REQUIRED)

    # -----------------------------
    # Add nanobind
    # -----------------------------
    find_package(nanobind CONFIG REQUIRED)

    # -----------------------------
    # Graph module
    # -----------------------------
    nanobind_add_module(cpp
        STABLE_ABI
        scgraph/cpp/bindings/graph_bindings.cpp
        scgraph/cpp/src/graph.cpp
        scgraph/cpp/src/graph_utils.cpp
        scgraph/cpp/src/contraction_hierarchies.cpp
        scgraph/cpp/src/transit_node_routing.cpp
    )


    install(TARGETS cpp DESTINATION scgraph)

endif()