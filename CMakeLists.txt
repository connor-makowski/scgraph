cmake_minimum_required(VERSION 3.15)

# -----------------------------
# Define The Project
# -----------------------------
project(scgraph LANGUAGES NONE)

# -----------------------------
# C++ detection
# -----------------------------
include(CheckLanguage)
check_language(CXX)

if(CMAKE_CXX_COMPILER)
    enable_language(CXX)
endif()

# -----------------------------
# If C++ is available, build extension
# -----------------------------
if(CMAKE_CXX_COMPILER_LOADED)

    message(STATUS "C++ compiler detected: Building compiled extension.")

    # -----------------------------
    # Set C++ standard
    # -----------------------------
    set(CMAKE_CXX_STANDARD 20)
    set(CMAKE_CXX_STANDARD_REQUIRED ON)

    # -----------------------------
    # OPTIMIZATION FLAGS
    # -----------------------------
    set(CMAKE_BUILD_TYPE Release)
    set(CMAKE_CXX_FLAGS_RELEASE "-O3 -march=native -DNDEBUG")

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
    )

    install(TARGETS cpp DESTINATION scgraph)

else()

    message(WARNING
        "No usable C++ compiler detected. "
        "Building pure Python version of scgraph. "
        "Performance will be reduced."
    )

endif()